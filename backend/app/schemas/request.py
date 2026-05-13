from pydantic import BaseModel
from uuid import UUID

class ChatRequest(BaseModel):
    document_id: UUID
    question: str

class TocRangeRequest(BaseModel):
    document_id: UUID
    toc_start_page: int
    toc_end_page: int
