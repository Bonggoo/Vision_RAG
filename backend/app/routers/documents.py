from fastapi import APIRouter, HTTPException
from typing import List, Dict, Any
from uuid import UUID
from app.schemas.response import DocumentListResponse
from datetime import datetime

router = APIRouter()

# 임시 더미 서비스 함수들 (나중에 pdf_service나 metadata_service로 이동)
def get_all_documents() -> List[Dict[str, Any]]:
    return []

def delete_document(document_id: UUID) -> bool:
    return False

@router.get("", response_model=DocumentListResponse)
async def list_documents():
    docs = get_all_documents()
    return {"documents": docs}

@router.delete("/{document_id}")
async def remove_document(document_id: UUID):
    success = delete_document(document_id)
    # 실제로는 성공 여부에 따라 분기
    return {"status": "deleted", "document_id": document_id}
