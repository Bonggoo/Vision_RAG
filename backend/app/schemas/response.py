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
    type: str  # "reasoning" | "reference" | "answer" | "error" | "done" | "clarification" | "toc_cards"
    content: Optional[str] = None
    page_number: Optional[int] = None
    image_base64: Optional[str] = None
    document_id: Optional[str] = None  # reference 이벤트에 문서 정보 추가
    document_name: Optional[str] = None
    candidates: Optional[List[dict]] = None  # clarification 이벤트용
    cards: Optional[List[dict]] = None  # toc_cards 이벤트용


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


class ConversationMessage(BaseModel):
    """대화 내 개별 메시지."""
    role: str
    content: str
    image: Optional[str] = None
    reasoning_steps: Optional[List[str]] = None
    reference_pages: Optional[List[int]] = None
    reference_document_id: Optional[str] = None
    reference_document_name: Optional[str] = None
    toc_cards: Optional[List[dict]] = None
    timestamp: Optional[str] = None


class ConversationInfo(BaseModel):
    """대화 목록 조회용 요약 정보."""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int


class ConversationDetail(BaseModel):
    """대화 상세 조회 응답 (메시지 포함)."""
    session_id: str
    title: str
    created_at: str
    updated_at: str
    messages: List[ConversationMessage]


class ConversationListResponse(BaseModel):
    """대화 목록 응답."""
    conversations: List[ConversationInfo]

