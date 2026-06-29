"""
대화 세션 관리 라우터.

엔드포인트:
  POST   /              새 대화 세션 생성
  GET    /              대화 목록 조회
  GET    /{session_id}  단건 대화 조회 (메시지 포함)
  DELETE /{session_id}  대화 삭제
  PATCH  /{session_id}/rename  대화 제목 변경
"""
from fastapi import APIRouter, HTTPException, Depends
from uuid import uuid4

from app.services.auth_service import get_current_user
from app.services import conversation_service
from app.schemas.request import CreateConversationRequest, RenameConversationRequest

router = APIRouter()


@router.post("/")
async def create_conversation(
    request: CreateConversationRequest,
    current_user: dict = Depends(get_current_user),
):
    """새 대화 세션을 생성합니다."""
    session_id = str(uuid4())
    result = await conversation_service.create_conversation_async(
        user_email=current_user["email"],
        session_id=session_id,
        title=request.title,
    )
    return result


@router.get("/")
async def list_conversations(current_user: dict = Depends(get_current_user)):
    """사용자의 대화 목록을 조회합니다 (최대 20개, 최신순)."""
    conversations = await conversation_service.get_conversations_async(current_user["email"])
    return {"conversations": conversations}


@router.get("/{session_id}")
async def get_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """단건 대화를 조회합니다 (메시지 포함)."""
    result = await conversation_service.get_conversation_async(current_user["email"], session_id)
    if result is None:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return result


@router.delete("/{session_id}")
async def delete_conversation(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """대화를 삭제합니다."""
    success = await conversation_service.delete_conversation_async(current_user["email"], session_id)
    if not success:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return {"status": "deleted", "session_id": session_id}


@router.patch("/{session_id}/rename")
async def rename_conversation(
    session_id: str,
    request: RenameConversationRequest,
    current_user: dict = Depends(get_current_user),
):
    """대화 제목을 변경합니다."""
    success = await conversation_service.rename_conversation_async(
        current_user["email"], session_id, request.title
    )
    if not success:
        raise HTTPException(status_code=404, detail="대화를 찾을 수 없습니다.")
    return {"status": "renamed", "session_id": session_id, "title": request.title}
