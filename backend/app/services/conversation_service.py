"""
대화 세션 관리 서비스 (GCS 연동, USE_LOCAL_STORAGE=True 시 로컬 파일 시스템 연동).

GCS 경로 구조: users/{owner_email}/conversations/{session_id}.json
로컬 경로 구조: {PDF_UPLOAD_DIR 상위}/conversations/{owner_email}/{session_id}.json
metadata_service의 GCS 버킷 싱글턴(_get_bucket)을 공유합니다.
"""
import os
import json
import asyncio
import threading
from datetime import datetime, timezone
from typing import Optional

from cachetools import TTLCache

from app.config import settings
from app.services.metadata_service import _get_bucket
from app.utils.logger import logger


# ── 사용자별 대화 목록 캐시 (TTL 60초, 최대 500명) — documents 목록 캐시와 동일 패턴 ──
_conversations_cache = TTLCache(maxsize=500, ttl=60)
_conv_cache_lock = threading.Lock()


def _invalidate_conversations_cache(user_email: str) -> None:
    """대화 생성/저장/삭제/제목변경 시 해당 사용자의 목록 캐시를 무효화합니다."""
    with _conv_cache_lock:
        _conversations_cache.pop(user_email.lower(), None)


# ── GCS 경로 헬퍼 ──

def _conversation_blob_path(user_email: str, session_id: str) -> str:
    """개별 대화 JSON의 GCS blob 경로를 생성합니다."""
    return f"users/{user_email}/conversations/{session_id}.json"


def _conversations_prefix(user_email: str) -> str:
    """사용자 대화 디렉토리의 GCS 프리픽스를 반환합니다."""
    return f"users/{user_email}/conversations/"


# ── 로컬 경로 헬퍼 (USE_LOCAL_STORAGE=True) ──

def _local_conversations_root() -> str:
    """PDF_UPLOAD_DIR과 나란한 로컬 대화 저장 루트 디렉토리."""
    base_dir = os.path.dirname(os.path.normpath(settings.PDF_UPLOAD_DIR)) or "."
    return os.path.join(base_dir, "conversations")


def _local_conversation_dir(user_email: str) -> str:
    return os.path.join(_local_conversations_root(), user_email.lower())


def _local_conversation_path(user_email: str, session_id: str) -> str:
    return os.path.join(_local_conversation_dir(user_email), f"{session_id}.json")


# ── 대화 CRUD ──

def create_conversation(user_email: str, session_id: str, title: str = "새로운 대화") -> dict:
    """빈 대화 JSON을 생성합니다 (로컬 또는 GCS)."""
    _invalidate_conversations_cache(user_email)
    now = datetime.now(timezone.utc).isoformat()

    conversation = {
        "session_id": session_id,
        "title": title,
        "created_at": now,
        "updated_at": now,
        "messages": [],
    }

    if settings.USE_LOCAL_STORAGE:
        path = _local_conversation_path(user_email, session_id)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(conversation, f, ensure_ascii=False)
    else:
        bucket = _get_bucket()
        blob = bucket.blob(_conversation_blob_path(user_email, session_id))
        blob.upload_from_string(
            json.dumps(conversation, ensure_ascii=False),
            content_type="application/json",
        )
    logger.info(f"✅ [Conversation] 대화 생성: {session_id} (user: {user_email})")
    return conversation


def get_conversations(user_email: str) -> list[dict]:
    """사용자의 대화 목록을 조회합니다 (최대 20개, 최신순). TTL 캐시(60초)로 반복 조회 시 I/O 생략."""
    cache_key = user_email.lower()
    with _conv_cache_lock:
        cached = _conversations_cache.get(cache_key)
    if cached is not None:
        return cached

    conversations: list[dict] = []

    if settings.USE_LOCAL_STORAGE:
        conv_dir = _local_conversation_dir(user_email)
        if os.path.isdir(conv_dir):
            for filename in os.listdir(conv_dir):
                if not filename.endswith(".json"):
                    continue
                path = os.path.join(conv_dir, filename)
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    conversations.append({
                        "session_id": data.get("session_id", ""),
                        "title": data.get("title", "제목 없음"),
                        "created_at": data.get("created_at", ""),
                        "updated_at": data.get("updated_at", ""),
                        "message_count": len(data.get("messages", [])),
                    })
                except Exception as e:
                    logger.warning(f"⚠️ [Conversation] 로컬 파싱 실패: {path} - {e}")
    else:
        bucket = _get_bucket()
        prefix = _conversations_prefix(user_email)
        blobs = list(bucket.list_blobs(prefix=prefix))
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
    result = conversations[:20]
    with _conv_cache_lock:
        _conversations_cache[cache_key] = result
    return result


def get_conversation(user_email: str, session_id: str) -> Optional[dict]:
    """단건 대화를 조회합니다 (메시지 포함)."""
    if settings.USE_LOCAL_STORAGE:
        path = _local_conversation_path(user_email, session_id)
        if not os.path.isfile(path):
            return None
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"❌ [Conversation] 로컬 조회 실패: {session_id} - {e}")
            return None

    bucket = _get_bucket()
    blob = bucket.blob(_conversation_blob_path(user_email, session_id))

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
    _invalidate_conversations_cache(user_email)
    now = datetime.now(timezone.utc).isoformat()
    local_path = _local_conversation_path(user_email, session_id) if settings.USE_LOCAL_STORAGE else None
    bucket = None if settings.USE_LOCAL_STORAGE else _get_bucket()
    blob = None if bucket is None else bucket.blob(_conversation_blob_path(user_email, session_id))

    try:
        # 기존 대화 로드 또는 새로 생성
        if settings.USE_LOCAL_STORAGE:
            if os.path.isfile(local_path):
                with open(local_path, "r", encoding="utf-8") as f:
                    conversation = json.load(f)
            else:
                conversation = {
                    "session_id": session_id,
                    "title": title or "새로운 대화",
                    "created_at": now,
                    "updated_at": now,
                    "messages": [],
                }
        elif blob.exists():
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

        # 저장 (로컬 또는 GCS)
        if settings.USE_LOCAL_STORAGE:
            os.makedirs(os.path.dirname(local_path), exist_ok=True)
            with open(local_path, "w", encoding="utf-8") as f:
                json.dump(conversation, f, ensure_ascii=False)
        else:
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
    _invalidate_conversations_cache(user_email)
    if settings.USE_LOCAL_STORAGE:
        path = _local_conversation_path(user_email, session_id)
        if not os.path.isfile(path):
            return False
        try:
            os.remove(path)
            logger.info(f"🗑️ [Conversation] 대화 삭제: {session_id}")
            return True
        except Exception as e:
            logger.error(f"❌ [Conversation] 삭제 실패: {session_id} - {e}")
            return False

    bucket = _get_bucket()
    blob = bucket.blob(_conversation_blob_path(user_email, session_id))

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
    _invalidate_conversations_cache(user_email)
    if settings.USE_LOCAL_STORAGE:
        path = _local_conversation_path(user_email, session_id)
        if not os.path.isfile(path):
            return False
        try:
            with open(path, "r", encoding="utf-8") as f:
                conversation = json.load(f)
            conversation["title"] = title
            conversation["updated_at"] = datetime.now(timezone.utc).isoformat()
            with open(path, "w", encoding="utf-8") as f:
                json.dump(conversation, f, ensure_ascii=False)
            logger.info(f"✏️ [Conversation] 제목 변경: {session_id} → {title}")
            return True
        except Exception as e:
            logger.error(f"❌ [Conversation] 제목 변경 실패: {session_id} - {e}")
            return False

    bucket = _get_bucket()
    blob = bucket.blob(_conversation_blob_path(user_email, session_id))

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


# ── Async wrappers (asyncio.to_thread) ──────────────────────────────────────

async def create_conversation_async(user_email: str, session_id: str, title: str = "새로운 대화") -> dict:
    return await asyncio.to_thread(create_conversation, user_email, session_id, title)

async def get_conversations_async(user_email: str) -> list[dict]:
    return await asyncio.to_thread(get_conversations, user_email)

async def get_conversation_async(user_email: str, session_id: str) -> Optional[dict]:
    return await asyncio.to_thread(get_conversation, user_email, session_id)

async def save_message_async(
    user_email: str,
    session_id: str,
    user_msg: dict,
    assistant_msg: dict,
    title: Optional[str] = None,
) -> bool:
    return await asyncio.to_thread(save_message, user_email, session_id, user_msg, assistant_msg, title)

async def delete_conversation_async(user_email: str, session_id: str) -> bool:
    return await asyncio.to_thread(delete_conversation, user_email, session_id)

async def rename_conversation_async(user_email: str, session_id: str, title: str) -> bool:
    return await asyncio.to_thread(rename_conversation, user_email, session_id, title)
