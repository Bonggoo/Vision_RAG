from fastapi import APIRouter, HTTPException, Depends, BackgroundTasks, Request, Response
from fastapi.responses import FileResponse, JSONResponse
import hashlib
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.response import DocumentListResponse
from app.services import metadata_service
from app.services.auth_service import get_current_user
from app.utils.logger import logger
import fitz
import os
import asyncio

router = APIRouter(dependencies=[Depends(get_current_user)])


class DocumentUpdateRequest(BaseModel):
    """문서 메타데이터 수정 요청."""
    filename: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None


async def _reclassify_documents(doc_ids: list[str], owner_email: str = ""):
    """
    백그라운드에서 미분류 문서들을 Gemini Vision으로 일괄 재분류합니다.
    Rate limit 방지를 위해 문서 간 1.5초 딜레이를 둡니다.
    """
    from app.services.pdf_service import _extract_document_classification, extract_pages_as_pdf

    success_count = 0
    fail_count = 0

    for doc_id in doc_ids:
        try:
            meta = metadata_service.get_document(doc_id, owner_email=owner_email)
            if meta is None:
                continue

            pdf_path = metadata_service.get_document_path(doc_id, owner_email=owner_email)
            if not pdf_path or not os.path.exists(pdf_path):
                logger.warning(f"⚠️ [재분류] PDF 파일 없음: {doc_id}")
                fail_count += 1
                continue

            # Gemini Vision으로 재분류
            fallback = meta.get("original_filename", meta.get("filename", "unknown"))
            classification = await _extract_document_classification(pdf_path, fallback)

            updates = {}
            if classification.get("manufacturer"):
                updates["manufacturer"] = classification["manufacturer"]
            if classification.get("model_series"):
                updates["model_series"] = classification["model_series"]
            if classification.get("doc_type"):
                updates["doc_type"] = classification["doc_type"]
            if classification.get("title") and not meta.get("filename"):
                updates["filename"] = classification["title"]

            if updates:
                metadata_service.update_document_metadata(doc_id, updates, owner_email=owner_email)
                logger.info(f"✅ [재분류] 성공: {doc_id} → {updates}")
                success_count += 1
            else:
                logger.warning(f"⚠️ [재분류] 분류 결과 없음: {doc_id}")
                fail_count += 1

            # Rate limit 방지 딜레이
            await asyncio.sleep(1.5)

        except Exception as e:
            logger.error(f"❌ [재분류] 실패: {doc_id} - {e}")
            fail_count += 1
            await asyncio.sleep(1.0)

    logger.info(f"🏁 [재분류] 완료: 성공 {success_count}건, 실패 {fail_count}건")


@router.post("/reclassify")
async def reclassify_documents(background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """
    미분류(manufacturer/model_series가 없는) 문서들을 Gemini Vision으로 일괄 재분류합니다.
    백그라운드 태스크로 실행되어 즉시 202 응답을 반환합니다.
    """
    docs = metadata_service.get_all_documents(owner_email=current_user["email"])

    # 미분류 문서 필터링 (manufacturer 또는 model_series가 없는 문서)
    unclassified = [
        d["document_id"] for d in docs
        if (not d.get("manufacturer") or not d.get("model_series"))
        and d.get("status") not in ("analyzing", "error")
    ]

    if not unclassified:
        return {"status": "no_action", "message": "재분류할 미분류 문서가 없습니다.", "count": 0}

    background_tasks.add_task(_reclassify_documents, unclassified, owner_email=current_user["email"])

    return {
        "status": "started",
        "message": f"미분류 문서 {len(unclassified)}건의 재분류가 시작되었습니다. 완료까지 약 {len(unclassified) * 2}초 소요됩니다.",
        "count": len(unclassified),
    }


@router.get("")
async def list_documents(request: Request, current_user: dict = Depends(get_current_user)):
    """업로드된 모든 문서 목록을 반환합니다."""
    docs = metadata_service.get_all_documents(owner_email=current_user["email"])
    
    # ETag: 문서 ID + status + filename 해시
    etag_source = "|".join(
        f'{d.get("document_id","")},{d.get("status","")},{d.get("filename","")}'
        for d in docs
    )
    etag = f'"{hashlib.md5(etag_source.encode()).hexdigest()}"'

    # 304 Not Modified
    if request.headers.get("if-none-match") == etag:
        return Response(status_code=304)

    return JSONResponse(
        content={"documents": docs},
        headers={"ETag": etag}
    )


@router.get("/{document_id}")
async def get_document_detail(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """문서 상세 정보를 반환합니다."""
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    meta = metadata_service.get_document(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    # ToC 항목 수만 포함 (전체 ToC는 /toc 엔드포인트 사용)
    toc = meta.get("toc", [])
    return {
        "document_id": meta.get("document_id"),
        "filename": meta.get("filename"),
        "total_pages": meta.get("total_pages"),
        "status": meta.get("status"),
        "uploaded_at": meta.get("uploaded_at"),
        "toc_count": len(toc),
    }


@router.patch("/{document_id}")
async def update_document(document_id: UUID, request: DocumentUpdateRequest, current_user: dict = Depends(get_current_user)):
    """문서 메타데이터(파일명, 제조사, 모델 등)를 수정합니다."""
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    meta = metadata_service.get_document(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    updates = {}
    if request.filename is not None:
        name = request.filename.strip()
        if not name:
            raise HTTPException(status_code=400, detail="파일명은 비어있을 수 없습니다.")
        updates["filename"] = name
        
    if request.manufacturer is not None:
        mfg = request.manufacturer.strip()
        updates["manufacturer"] = mfg if mfg else None
        
    if request.model_series is not None:
        model = request.model_series.strip()
        updates["model_series"] = model if model else None
    
    if not updates:
        raise HTTPException(status_code=400, detail="변경할 항목이 없습니다.")
    
    updated = metadata_service.update_document_metadata(doc_id, updates, owner_email=current_user["email"])
    return {
        "status": "updated", 
        "document_id": doc_id, 
        "filename": updated.get("filename"),
        "manufacturer": updated.get("manufacturer"),
        "model_series": updated.get("model_series"),
    }


@router.delete("/{document_id}")
async def remove_document(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """문서를 삭제합니다 (PDF + 메타데이터)."""
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    success = metadata_service.delete_document(doc_id, owner_email=current_user["email"])
    if not success:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    return {"status": "deleted", "document_id": document_id}


@router.get("/{document_id}/toc")
async def get_document_toc(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """문서의 ToC(목차)를 반환합니다."""
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    toc = metadata_service.get_document_toc(doc_id)
    if toc is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    return {"document_id": doc_id, "toc": toc, "toc_count": len(toc)}


@router.post("/{document_id}/reindex")
async def reindex_document(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """기존 문서의 ToC를 Vision 기반으로 재보강합니다."""
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    meta = metadata_service.get_document(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = metadata_service.get_document_path(doc_id, owner_email=current_user["email"])
    if pdf_path is None:
        raise HTTPException(status_code=500, detail="PDF 파일을 찾을 수 없습니다.")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        
        from app.services.agent_service import find_and_extract_toc
        enriched = find_and_extract_toc(doc, total_pages)
        doc.close()
        
        if not enriched:
            raise HTTPException(status_code=400, detail="목차를 찾을 수 없습니다.")
        
        old_count = len(meta.get("toc", []))
        metadata_service.update_document_metadata(doc_id, {
            "toc": enriched,
            "status": "indexed",
        }, owner_email=current_user["email"])
        
        return {
            "status": "reindexed",
            "document_id": doc_id,
            "toc_count_before": old_count,
            "toc_count_after": len(enriched),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ToC 보강 실패: {str(e)}")


@router.get("/{document_id}/download")
async def download_document(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """
    문서 PDF를 다운로드합니다.
    파일명 형식: 제조사_모델시리즈_문서유형.pdf
    """
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    meta = metadata_service.get_document(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = metadata_service.get_document_path(doc_id, owner_email=current_user["email"])
    if pdf_path is None or not os.path.isfile(pdf_path):
        raise HTTPException(status_code=404, detail="PDF 파일을 찾을 수 없습니다.")
    
    # 다운로드 파일명 조합
    parts = filter(None, [
        meta.get("manufacturer"),
        meta.get("model_series"),
        meta.get("doc_type") or meta.get("filename")
    ])
    download_name = "_".join(parts) + ".pdf"
    
    # 특수문자 제거하여 안전한 파일명 생성
    import re
    download_name = re.sub(r'[\\/*?:"<>|]', "", download_name)
    
    from urllib.parse import quote
    encoded_filename = quote(download_name)
    # filename에는 안전한 ASCII fallback 값을 제공하고, 실제 한글명은 URL 인코딩된 filename*를 사용해 UnicodeEncodeError 방지
    headers = {
        "Content-Disposition": f"attachment; filename=\"document.pdf\"; filename*=UTF-8''{encoded_filename}"
    }
    
    return FileResponse(pdf_path, media_type="application/pdf", headers=headers)


@router.get("/{document_id}/download-url")
async def download_document_url(document_id: UUID, current_user: dict = Depends(get_current_user)):
    """
    문서 다운로드를 위한 URL을 발급합니다.
    로컬 모드인 경우 로컬 다운로드 API 경로를, GCS 모드인 경우 GCS Signed URL을 반환합니다.
    """
    doc_id = str(document_id)
    if not metadata_service.verify_document_owner(doc_id, current_user["email"]):
        raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    meta = metadata_service.get_document(doc_id, owner_email=current_user["email"])
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    # 다운로드 파일명 조합
    parts = filter(None, [
        meta.get("manufacturer"),
        meta.get("model_series"),
        meta.get("doc_type") or meta.get("filename")
    ])
    download_name = "_".join(parts) + ".pdf"
    
    # 특수문자 제거하여 안전한 파일명 생성
    import re
    download_name = re.sub(r'[\\/*?:"<>|]', "", download_name)
    
    # Signed URL 생성 시도
    signed_url = metadata_service.get_document_signed_url(doc_id, download_name, owner_email=current_user["email"])
    
    if signed_url:
        return {
            "mode": "gcs",
            "url": signed_url,
            "filename": download_name
        }
    else:
        # 로컬 스토리지 모드이거나 Signed URL 생성에 실패한 경우 로컬 다운로드 엔드포인트 반환
        return {
            "mode": "local",
            "url": f"/documents/{doc_id}/download",
            "filename": download_name
        }


