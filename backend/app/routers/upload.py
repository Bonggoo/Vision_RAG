from fastapi import APIRouter, UploadFile, File, HTTPException
from typing import Optional
from app.schemas.response import UploadResponse
from app.schemas.request import TocRangeRequest
from app.services.pdf_service import process_document_upload

router = APIRouter()

@router.post("", response_model=UploadResponse)
async def upload_document(file: UploadFile = File(...)):
    if not file.filename.lower().endswith('.pdf'):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    
    # process_document_upload는 파일 객체를 받아 저장하고 분석(ToC 등)을 수행합니다.
    try:
        result = await process_document_upload(file)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process PDF: {str(e)}")

@router.post("/toc", response_model=UploadResponse)
async def extract_toc_with_range(request: TocRangeRequest):
    # TODO: 사용자 지정 범위로 ToC 재추출 로직 연동
    pass
