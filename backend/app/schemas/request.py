from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional


class ChatHistoryItem(BaseModel):
    """이전 대화 항목."""
    role: str  # "user" | "assistant"
    content: str


class ChatRequest(BaseModel):
    """질의·응답 요청 스키마. document_id가 없으면 자동 선택합니다."""
    document_id: Optional[UUID] = None
    question: str = Field(..., alias="message")
    chat_history: Optional[List[ChatHistoryItem]] = None
    
    model_config = {"populate_by_name": True}


class TocRangeRequest(BaseModel):
    """스캔 PDF 목차 범위 지정 요청 스키마."""
    document_id: UUID
    toc_start_page: int
    toc_end_page: int

