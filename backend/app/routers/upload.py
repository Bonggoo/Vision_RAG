from fastapi import APIRouter, UploadFile, File, HTTPException
from app.schemas.response import UploadResponse
from app.schemas.request import TocRangeRequest
from app.services.pdf_service import process_document_upload, extract_pages_as_pdf
from app.services.agent_service import extract_toc_with_gemini
from app.services import metadata_service
from app.exceptions import DuplicateDocumentError, EmptyFileError
import fitz

router = APIRouter()


@router.post("", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    """PDF 파일을 업로드하고 목차(ToC)를 추출합니다."""
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="PDF 파일만 지원합니다.")
    
    try:
        result = await process_document_upload(file)
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


@router.post("/toc", response_model=UploadResponse)
async def extract_toc_with_range(request: TocRangeRequest):
    """
    스캔 PDF에 대해 사용자가 지정한 페이지 범위에서 ToC를 재추출합니다.
    status가 'toc_required'인 문서에 대해 호출됩니다.
    """
    doc_id = str(request.document_id)
    meta = metadata_service.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = metadata_service.get_document_path(doc_id)
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
        updated = metadata_service.update_document_metadata(doc_id, {
            "toc": toc,
            "status": "indexed"
        })
        
        return updated
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ToC 추출 실패: {str(e)}")
