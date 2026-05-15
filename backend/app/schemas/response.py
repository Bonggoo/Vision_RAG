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

class DocumentInfo(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    uploaded_at: datetime

class DocumentListResponse(BaseModel):
    documents: List[DocumentInfo]

class StreamEvent(BaseModel):
    type: str  # "reasoning" | "reference" | "answer" | "error" | "done"
    content: Optional[str] = None
    page_number: Optional[int] = None
    image_base64: Optional[str] = None
