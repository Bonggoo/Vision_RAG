from fastapi import APIRouter, HTTPException
from uuid import UUID
from app.schemas.response import DocumentListResponse
from app.services import metadata_service
import fitz

router = APIRouter()


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """업로드된 모든 문서 목록을 반환합니다."""
    docs = metadata_service.get_all_documents()
    return {"documents": docs}


@router.delete("/{document_id}")
async def remove_document(document_id: UUID):
    """문서를 삭제합니다 (PDF + 메타데이터)."""
    success = metadata_service.delete_document(str(document_id))
    if not success:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    return {"status": "deleted", "document_id": document_id}


@router.post("/{document_id}/reindex")
async def reindex_document(document_id: UUID):
    """기존 문서의 ToC를 Vision 기반으로 재보강합니다."""
    doc_id = str(document_id)
    meta = metadata_service.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = metadata_service.get_document_path(doc_id)
    if pdf_path is None:
        raise HTTPException(status_code=500, detail="PDF 파일을 찾을 수 없습니다.")
    
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        
        # 기존 ToC를 뼈대로 사용
        coarse_toc = meta.get("toc", [])
        if not coarse_toc:
            # 북마크에서 추출 시도
            from app.services.pdf_service import extract_toc
            coarse_toc = extract_toc(doc)
        
        if not coarse_toc:
            doc.close()
            raise HTTPException(status_code=400, detail="보강할 ToC 뼈대가 없습니다.")
        
        from app.services.agent_service import find_and_extract_toc
        enriched = find_and_extract_toc(doc, total_pages)
        doc.close()
        
        # 메타데이터 업데이트
        metadata_service.update_document_metadata(doc_id, {
            "toc": enriched,
            "status": "indexed",
        })
        
        return {
            "status": "reindexed",
            "document_id": doc_id,
            "toc_count_before": len(coarse_toc),
            "toc_count_after": len(enriched),
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"ToC 보강 실패: {str(e)}")
