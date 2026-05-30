from fastapi import APIRouter, HTTPException, Depends
from fastapi.responses import FileResponse
from uuid import UUID
from typing import Optional
from pydantic import BaseModel
from app.schemas.response import DocumentListResponse
from app.services import metadata_service
from app.services.auth_service import get_current_user
import fitz
import os

router = APIRouter(dependencies=[Depends(get_current_user)])


class DocumentUpdateRequest(BaseModel):
    """문서 메타데이터 수정 요청."""
    filename: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None


@router.get("", response_model=DocumentListResponse)
async def list_documents():
    """업로드된 모든 문서 목록을 반환합니다."""
    docs = metadata_service.get_all_documents()
    return {"documents": docs}


@router.get("/{document_id}")
async def get_document_detail(document_id: UUID):
    """문서 상세 정보를 반환합니다."""
    doc_id = str(document_id)
    meta = metadata_service.get_document(doc_id)
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
async def update_document(document_id: UUID, request: DocumentUpdateRequest):
    """문서 메타데이터(파일명, 제조사, 모델 등)를 수정합니다."""
    doc_id = str(document_id)
    meta = metadata_service.get_document(doc_id)
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
    
    updated = metadata_service.update_document_metadata(doc_id, updates)
    return {
        "status": "updated", 
        "document_id": doc_id, 
        "filename": updated.get("filename"),
        "manufacturer": updated.get("manufacturer"),
        "model_series": updated.get("model_series"),
    }


@router.delete("/{document_id}")
async def remove_document(document_id: UUID):
    """문서를 삭제합니다 (PDF + 메타데이터)."""
    success = metadata_service.delete_document(str(document_id))
    if not success:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    return {"status": "deleted", "document_id": document_id}


@router.get("/{document_id}/toc")
async def get_document_toc(document_id: UUID):
    """문서의 ToC(목차)를 반환합니다."""
    doc_id = str(document_id)
    toc = metadata_service.get_document_toc(doc_id)
    if toc is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    return {"document_id": doc_id, "toc": toc, "toc_count": len(toc)}


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
        
        from app.services.agent_service import find_and_extract_toc
        enriched = find_and_extract_toc(doc, total_pages)
        doc.close()
        
        if not enriched:
            raise HTTPException(status_code=400, detail="목차를 찾을 수 없습니다.")
        
        old_count = len(meta.get("toc", []))
        metadata_service.update_document_metadata(doc_id, {
            "toc": enriched,
            "status": "indexed",
        })
        
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
async def download_document(document_id: UUID):
    """
    문서 PDF를 다운로드합니다.
    파일명 형식: 제조사_모델시리즈_문서유형.pdf
    """
    doc_id = str(document_id)
    meta = metadata_service.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    pdf_path = metadata_service.get_document_path(doc_id)
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
async def download_document_url(document_id: UUID):
    """
    문서 다운로드를 위한 URL을 발급합니다.
    로컬 모드인 경우 로컬 다운로드 API 경로를, GCS 모드인 경우 GCS Signed URL을 반환합니다.
    """
    doc_id = str(document_id)
    meta = metadata_service.get_document(doc_id)
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
    signed_url = metadata_service.get_document_signed_url(doc_id, download_name)
    
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


