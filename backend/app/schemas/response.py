from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import List, Optional, Union

class TocItem(BaseModel):
    level: int
    title: str
    page: Union[int, str]

class SimilarDocument(BaseModel):
    """근접 중복으로 감지된 기존 문서 참조 (감지 전용, 비차단)."""
    document_id: str
    filename: str
    score: float          # ToC 지문 Jaccard 유사도 (0.0~1.0)
    reason: str           # "toc" | "metadata"

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
    source_format: Optional[str] = None  # 업로드 원본 확장자 (예: "pdf", "docx")
    similar_documents: List[SimilarDocument] = []

class DocumentInfo(BaseModel):
    document_id: UUID
    filename: str
    total_pages: int
    uploaded_at: datetime
    file_hash: Optional[str] = None
    manufacturer: Optional[str] = None
    model_series: Optional[str] = None
    doc_type: Optional[str] = None
    source_format: Optional[str] = None  # 업로드 원본 확장자 (예: "pdf", "docx")
    similar_documents: List[SimilarDocument] = []

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
    # GCS Signed URL 서명에 사용된 Content-Type. 브라우저는 PUT 시 이 값을
    # 헤더에 그대로 설정해야 서명 검증(403)을 통과합니다.
    content_type: Optional[str] = None


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

