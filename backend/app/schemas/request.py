from pydantic import BaseModel, Field
from uuid import UUID


class ChatRequest(BaseModel):
    """질의·응답 요청 스키마. 프론트엔드 호환을 위해 'message' alias도 지원합니다."""
    document_id: UUID
    question: str = Field(..., alias="message")
    
    model_config = {"populate_by_name": True}


class TocRangeRequest(BaseModel):
    """스캔 PDF 목차 범위 지정 요청 스키마."""
    document_id: UUID
    toc_start_page: int
    toc_end_page: int

