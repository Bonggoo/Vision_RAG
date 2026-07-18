from pydantic import BaseModel, Field
from uuid import UUID
from typing import List, Optional


class ChatHistoryItem(BaseModel):
    """이전 대화 항목."""
    role: str  # "user" | "assistant"
    content: str


class PreviousReference(BaseModel):
    """이전 대화에서 참조한 문서 맥락 정보."""
    document_id: UUID
    document_name: Optional[str] = None
    manufacturer: Optional[str] = None
    referenced_pages: Optional[List[int]] = None


class ChatRequest(BaseModel):
    """질의·응답 요청 스키마. document_id가 없으면 자동 선택합니다."""
    document_id: Optional[UUID] = None
    question: str = Field(..., alias="message")
    chat_history: Optional[List[ChatHistoryItem]] = None
    image: Optional[str] = None  # Base64 이미지 데이터 URL (선택 사항)
    # UUID 강제: 로컬 스토리지 모드에서 session_id가 파일 경로에 들어가므로 경로 조작 문자열 차단
    session_id: Optional[UUID] = None  # 대화 GCS 저장용
    previous_reference: Optional[PreviousReference] = None  # 맥락 유지용
    
    model_config = {"populate_by_name": True}


class TocRangeRequest(BaseModel):
    """스캔 PDF 목차 범위 지정 요청 스키마."""
    document_id: UUID
    toc_start_page: int
    toc_end_page: int


class PreflightRequest(BaseModel):
    """업로드 사전 검증 요청 스키마."""
    file_hash: str
    file_size: int
    filename: str


class AnalyzeRequest(BaseModel):
    """비동기 분석 요청 스키마."""
    document_id: UUID
    filename: str
    file_hash: str


class CreateConversationRequest(BaseModel):
    """새 대화 세션 생성 요청 스키마."""
    title: str = "새로운 대화"


class RenameConversationRequest(BaseModel):
    """대화 제목 변경 요청 스키마."""
    title: str

