from fastapi import APIRouter, UploadFile, File, HTTPException, Depends
from fastapi.responses import JSONResponse
from app.schemas.response import UploadResponse, PreflightResponse, AnalyzeResponse
from app.schemas.request import TocRangeRequest, PreflightRequest, AnalyzeRequest
from app.services.pdf_service import process_document_upload, extract_pages_as_pdf, _extract_document_classification, build_toc
from app.services.agent_service import extract_toc_with_gemini
from app.services import metadata_service
from app.services import dedup_service
from app.services.auth_service import get_current_user
from app.exceptions import DuplicateDocumentError, EmptyFileError
from app.config import settings
from app.utils.logger import logger
import fitz
import uuid
import os
from datetime import datetime, timezone

router = APIRouter()


@router.post("", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...), current_user: dict = Depends(get_current_user)):
    """PDF 파일을 업로드하고 목차(ToC)를 추출합니다."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF 파일만 지원합니다.")
    
    try:
        result = await process_document_upload(file, owner_email=current_user["email"])
        return result
    except DuplicateDocumentError as e:
        raise HTTPException(
            status_code=409,
            detail=f"이미 동일한 문서가 업로드되어 있습니다: '{e.existing_filename}'"
        )
    except EmptyFileError:
        raise HTTPException(
            status_code=400,
            detail="파일이 로컬에 저장되어 있지 않거나 손상되었습니다. 파일을 확인한 후 다시 시도해 주세요."
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF 처리 실패: {str(e)}")


@router.post("/preflight", response_model=PreflightResponse)
async def upload_preflight(request: PreflightRequest, current_user: dict = Depends(get_current_user)):
    """
    업로드 사전 검증: 중복 확인 및 GCS Signed URL 발급.
    로컬 모드(USE_LOCAL_STORAGE=True)일 경우 upload_url은 None을 반환하여
    프론트엔드가 기존 동기식 업로드로 fallback하도록 유도합니다.
    """
    # 1. 파일 크기 검증
    if request.file_size == 0:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다.")

    # 2. SHA-256 해시 중복 체크 (사용자 소유 문서 범위 내에서만)
    existing_docs = await metadata_service.get_all_documents_async(owner_email=current_user["email"])
    for doc_meta in existing_docs:
        if doc_meta.get("file_hash") == request.file_hash:
            raise HTTPException(
                status_code=409,
                detail=f"이미 등록된 문서입니다: {doc_meta.get('filename')}"
            )

    # 3. document_id 및 UUID 발급
    doc_id = uuid.uuid4()
    upload_url = None

    # 4. GCS Signed Upload URL 생성 (로컬 모드가 아닐 때만)
    if not settings.USE_LOCAL_STORAGE:
        try:
            blob_name = metadata_service.gcs_blob_path(current_user["email"], str(doc_id), "original.pdf")
            upload_url = await metadata_service.generate_gcs_signed_url_async(
                bucket_name=settings.GCS_BUCKET_NAME,
                blob_name=blob_name,
                method="PUT",
                expiration_minutes=15,
                content_type="application/pdf"
            )
            if upload_url:
                logger.info(f"🔑 GCS Signed Upload URL 발급 성공: {doc_id}")
            else:
                raise ValueError("Signed URL 생성 결과가 None입니다.")
        except Exception as e:
            logger.error(f"❌ GCS Signed URL 발급 중 오류 발생 (동기 Fallback 유도): {e}")
            # Signed URL 생성이 실패하더라도 프론트엔드가 동기식으로 업로드하도록 upload_url = None으로 진행합니다.
            upload_url = None

    return PreflightResponse(
        status="approved",
        document_id=doc_id,
        upload_url=upload_url
    )


async def _run_analysis_pipeline(document_id: str, filename: str, file_hash: str, owner_email: str = ""):
    """
    백그라운드에서 비동기로 실행되는 AI 분석 파이프라인.
    PyMuPDF의 PDF 파싱과 Gemini API 분석을 순차적으로 수행합니다.
    """
    logger.info(f"🚀 비동기 PDF 분석 파이프라인 시작: {document_id} ({filename})")
    try:
        # 1. 원본 PDF 경로 확보 (GCS 사용 시 /tmp에 자동 캐싱 다운로드됨)
        pdf_path = await metadata_service.get_document_path_async(document_id, owner_email=owner_email)
        if not pdf_path or not os.path.exists(pdf_path):
            raise FileNotFoundError(f"PDF 원본 파일을 찾을 수 없습니다: {document_id}")

        doc = fitz.open(pdf_path)
        total_pages = doc.page_count

        # 2. ToC 추출 전략 (Case A-1/A-2/B/C) — build_toc로 일원화
        toc, status = build_toc(doc, total_pages)

        doc.close()

        # 3. AI 기반 자동 분류 및 제목 추출
        classification = await _extract_document_classification(pdf_path, filename)

        # 4. 최종 메타데이터 병합 및 디렉토리 관리
        final_metadata = {
            "document_id": document_id,
            "filename": classification["title"],
            "original_filename": filename,
            "total_pages": total_pages,
            "toc": toc,
            "uploaded_at": datetime.now(timezone.utc).isoformat(),
            "status": status,
            "file_hash": file_hash,
            "manufacturer": classification.get("manufacturer"),
            "model_series": classification.get("model_series"),
            "doc_type": classification.get("doc_type"),
            "owner_email": owner_email,
        }

        # 4-1. 근접 중복 감지 (콘텐츠 지문 기반, 비차단·감지 전용).
        # 바이트 해시 사전검사를 통과한 재추출본 등 '사실상 같은 문서'를 찾아
        # 메타데이터에 실어두면 프론트가 '유사 문서 있음'을 사용자에게 안내할 수 있음.
        try:
            existing = await metadata_service.get_all_documents_async(owner_email=owner_email)
            final_metadata["similar_documents"] = dedup_service.find_similar_documents(final_metadata, existing)
            if final_metadata["similar_documents"]:
                logger.info(f"🔁 근접 중복 후보 감지: {document_id} ↔ {final_metadata['similar_documents']}")
        except Exception as dup_err:
            logger.warning(f"⚠️ 근접 중복 감지 건너뜀(비차단): {dup_err}")
            final_metadata["similar_documents"] = []

        # 5. 메타데이터 업데이트 (로컬 & GCS)
        await metadata_service.update_document_metadata_async(document_id, final_metadata, owner_email=owner_email)
        logger.info(f"✅ 비동기 PDF 분석 파이프라인 완료: {document_id}")

    except Exception as e:
        logger.error(f"❌ 비동기 PDF 분석 파이프라인 실패: {document_id} - {e}")
        try:
            await metadata_service.update_document_metadata_async(document_id, {
                "status": "error",
                "error_message": str(e)
            }, owner_email=owner_email)
        except Exception as update_err:
            logger.error(f"❌ 실패 메타데이터 업데이트 오류: {update_err}")


@router.post("/analyze", response_model=AnalyzeResponse)
async def trigger_analysis(request: AnalyzeRequest, current_user: dict = Depends(get_current_user)):
    """
    GCS 또는 로컬 스토리지에 업로드된 원본 PDF의 AI 분석을 비동기로 호출합니다.
    즉시 202 Accepted 응답을 보냅니다.
    """
    doc_id = str(request.document_id)

    # 1. 파일 존재 여부 선제적 검증
    if settings.USE_LOCAL_STORAGE:
        doc_dir = os.path.join(settings.PDF_UPLOAD_DIR, doc_id)
        pdf_path = os.path.join(doc_dir, "original.pdf")
        if not os.path.exists(pdf_path):
            raise HTTPException(status_code=404, detail="로컬에 원본 PDF 파일이 존재하지 않습니다.")
    else:
        try:
            from google.cloud import storage
            client = storage.Client()
            bucket = client.bucket(settings.GCS_BUCKET_NAME)
            blob_name = metadata_service.gcs_blob_path(current_user["email"], doc_id, "original.pdf")
            blob = bucket.blob(blob_name)
            if not blob.exists():
                raise HTTPException(status_code=404, detail="GCS에 원본 PDF 파일이 존재하지 않습니다.")
        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"GCS 연결 확인 실패: {e}")

    # 2. 임시 메타데이터 생성 ("status": "analyzing")
    initial_metadata = {
        "document_id": doc_id,
        "filename": request.filename,
        "original_filename": request.filename,
        "total_pages": 0,
        "toc": [],
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
        "status": "analyzing",
        "file_hash": request.file_hash,
        "manufacturer": None,
        "model_series": None,
        "doc_type": None,
        "owner_email": current_user["email"],
    }

    # metadata_service에는 신규 생성용이 따로 없으므로 update_document_metadata를 사용하되, 
    # update_document_metadata의 get_document가 로컬/GCS에 파일이 없을 시 None을 주기 때문에
    # 직접 metadata_service에 파일을 써줍니다. (혹은 metadata_service 내부 로직 차용)
    if not await metadata_service.create_document_metadata_async(doc_id, initial_metadata, current_user["email"]):
        raise HTTPException(status_code=500, detail="임시 메타데이터 생성 실패")

    # 3. 비동기 작업 등록 (Cloud Tasks 또는 로컬 폴백)
    from app.services.task_queue import enqueue_analysis
    await enqueue_analysis(doc_id, request.filename, request.file_hash, current_user["email"])

    return AnalyzeResponse(
        status="analyzing",
        document_id=request.document_id,
        message="AI 비동기 분석 작업이 큐에 성공적으로 등록되었습니다."
    )


@router.post("/toc", response_model=UploadResponse)
async def extract_toc_with_range(request: TocRangeRequest, current_user: dict = Depends(get_current_user)):
    """
    스캔 PDF에 대해 사용자가 지정한 페이지 범위에서 ToC를 재추출합니다.
    status가 'toc_required'인 문서에 대해 호출됩니다.
    """
    doc_id = str(request.document_id)
    
    # 소유권 검증
    if not await metadata_service.verify_document_owner_async(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    
    meta = await metadata_service.get_document_async(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = await metadata_service.get_document_path_async(doc_id, owner_email=current_user["email"])
    if pdf_path is None:
        raise HTTPException(status_code=500, detail="PDF 파일을 찾을 수 없습니다.")
    
    try:
        doc = fitz.open(pdf_path)
        
        # 페이지 번호 유효성 검사 (1-indexed → 0-indexed)
        start = max(0, request.toc_start_page - 1)
        end = min(doc.page_count - 1, request.toc_end_page - 1)
        
        if start > end:
            doc.close()
            raise HTTPException(status_code=400, detail="잘못된 페이지 범위입니다.")
        
        # 미니 PDF 추출 후 Gemini로 ToC 분석
        mini_pdf_bytes = extract_pages_as_pdf(doc, start, end)
        doc.close()
        
        toc = extract_toc_with_gemini(mini_pdf_bytes)
        
        # 메타데이터 업데이트
        updated = await metadata_service.update_document_metadata_async(doc_id, {
            "toc": toc,
            "status": "indexed"
        }, owner_email=current_user["email"])
        
        return updated
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ToC 추출 실패: {str(e)}")

