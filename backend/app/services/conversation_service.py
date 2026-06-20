"""
대화 세션 관리 서비스 (GCS 연동).

GCS 경로 구조: users/{owner_email}/conversations/{session_id}.json
metadata_service의 GCS 버킷 싱글턴(_get_bucket)을 공유합니다.
"""
import json
from datetime import datetime, timezone
from typing import Optional

from app.services.metadata_service import _get_bucket
from app.utils.logger import logger


# ── GCS 경로 헬퍼 ──

def _conversation_blob_path(user_email: str, session_id: str) -> str:
    """개별 대화 JSON의 GCS blob 경로를 생성합니다."""
    return f"users/{user_email}/conversations/{session_id}.json"


def _conversations_prefix(user_email: str) -> str:
    """사용자 대화 디렉토리의 GCS 프리픽스를 반환합니다."""
    return f"users/{user_email}/conversations/"


# ── 대화 CRUD ──

def create_conversation(user_email: str, session_id: str, title: str = "새로운 대화") -> dict:
    """GCS에 빈 대화 JSON을 생성합니다."""
    bucket = _get_bucket()
    blob_path = _conversation_blob_path(user_email, session_id)
    now = datetime.now(timezone.utc).isoformat()

    conversation = {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }

    blob = bucket.blob(blob_path)
    blob.upload_from_string(
        json.dumps(conversation, ensure_ascii=False),
        content_type="application/json",
    )
    logger.info(f"✅ [Conversation] 대화 생성: {session_id} (user: {user_email})")
    return conversation


def get_conversations(user_email: str) -> list[dict]:
    """사용자의 대화 목록을 조회합니다 (최대 20개, 최신순)."""
    bucket = _get_bucket()
    prefix = _conversations_prefix(user_email)
    blobs = list(bucket.list_blobs(prefix=prefix))

    conversations: list[dict] = []
    for blob in blobs:
        if not blob.name.endswith(".json"):
            continue
        try:
            data = json.loads(blob.download_as_text())
            conversations.append({
                "session_id": data.get("session_id", ""),
                "title": data.get("title", "제목 없음"),
                "created_at": data.get("created_at", ""),
                "updated_at": data.get("updated_at", ""),
                "message_count": len(data.get("messages", [])),
            })
        except Exception as e:
            logger.warning(f"⚠️ [Conversation] 파싱 실패: {blob.name} - {e}")

    # 최신순 정렬, 최대 20개
    conversations.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return conversations[:20]


def get_conversation(user_email: str, session_id: str) -> Optional[dict]:
    """단건 대화를 조회합니다 (메시지 포함)."""
    bucket = _get_bucket()
    blob_path = _conversation_blob_path(user_email, session_id)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return None

    try:
        return json.loads(blob.download_as_text())
    except Exception as e:
        logger.error(f"❌ [Conversation] 조회 실패: {session_id} - {e}")
        return None


def save_message(
    user_email: str,
    session_id: str,
    user_msg: dict,
    assistant_msg: dict,
    title: Optional[str] = None,
) -> bool:
    """user+assistant 메시지 쌍을 대화에 추가 저장합니다.

    done 이벤트 시 백엔드에서 자동 호출됩니다.
    세션이 없으면 자동 생성합니다.
    """
    bucket = _get_bucket()
    blob_path = _conversation_blob_path(user_email, session_id)
    blob = bucket.blob(blob_path)
    now = datetime.now(timezone.utc).isoformat()

    try:
        # 기존 대화 로드 또는 새로 생성
        if blob.exists():
            conversation = json.loads(blob.download_as_text())
        else:
            conversation = {
                "session_id": session_id,
                "title": title or "새로운 대화",
                "created_at": now,
                "updated_at": now,
                "messages": [],
            }

        # 타임스탬프 추가
        user_msg["timestamp"] = now
        assistant_msg["timestamp"] = now

        # 메시지 추가
        conversation["messages"].append(user_msg)
        conversation["messages"].append(assistant_msg)
        conversation["updated_at"] = now

        # 첫 메시지이고 제목이 있으면 업데이트
        if title and len(conversation["messages"]) <= 2:
            conversation["title"] = title

        # GCS에 저장
        blob.upload_from_string(
            json.dumps(conversation, ensure_ascii=False),
            content_type="application/json",
        )
        logger.info(
            f"✅ [Conversation] 메시지 저장 완료: {session_id} "
            f"(총 {len(conversation['messages'])}개)"
        )
        return True
    except Exception as e:
        logger.error(
            f"❌ [Conversation] 메시지 저장 실패: {session_id} - {e}",
            exc_info=True,
        )
        return False


def delete_conversation(user_email: str, session_id: str) -> bool:
    """대화를 삭제합니다."""
    bucket = _get_bucket()
    blob_path = _conversation_blob_path(user_email, session_id)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return False

    try:
        blob.delete()
        logger.info(f"🗑️ [Conversation] 대화 삭제: {session_id}")
        return True
    except Exception as e:
        logger.error(f"❌ [Conversation] 삭제 실패: {session_id} - {e}")
        return False


def rename_conversation(user_email: str, session_id: str, title: str) -> bool:
    """대화 제목을 변경합니다."""
    bucket = _get_bucket()
    blob_path = _conversation_blob_path(user_email, session_id)
    blob = bucket.blob(blob_path)

    if not blob.exists():
        return False

    try:
        conversation = json.loads(blob.download_as_text())
        conversation["title"] = title
        conversation["updated_at"] = datetime.now(timezone.utc).isoformat()

        blob.upload_from_string(
            json.dumps(conversation, ensure_ascii=False),
            content_type="application/json",
        )
        logger.info(f"✏️ [Conversation] 제목 변경: {session_id} → {title}")
        return True
    except Exception as e:
        logger.error(f"❌ [Conversation] 제목 변경 실패: {session_id} - {e}")
        return False
