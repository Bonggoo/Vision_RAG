from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import List, Optional, Union

class TocItem(BaseModel):
    level: int
    title: str
    page: Union[int, str]

class UploadResponse(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    toc: List[TocItem]
    status: str  # "indexed" | "toc_required"
    file_hash: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None
    doc_type: Optional[str] = None

class DocumentInfo(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    uploaded_at: datetime
    file_hash: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None
    doc_type: Optional[str] = None

class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]

class StreamEvent(BaseModel):
    type: str  # "reasoning" | "reference" | "answer" | "error" | "done"
    content: Optional[str] = None
    page_number: Optional[int] = None
    image_base64: Optional[str] = None


class PreflightResponse(BaseModel):
    """업로드 사전 검증 응답 스키마."""
    status: str
    document_id: UUID
    upload_url: Optional[str] = None


class AnalyzeResponse(BaseModel):
    """비동기 분석 요청 응답 스키마."""
    status: str
    document_id: UUID
    message: str

