"""리프레시 토큰 서버 측 폐기 — 감사 항목 H-3.

리프레시 토큰은 stateless JWT 라 토큰 자체를 무효화할 수 없다. 대신 사용자별로
"이 시각 이전에 발급된 리프레시 토큰은 전부 무효"라는 폐기 시각을 서버에 저장하고,
검증할 때 토큰의 발급 시각(`iat_ms` 클레임)과 비교한다.

- 로그아웃 → 폐기 시각을 '지금'으로 올린다 → 유출된 토큰을 포함해 그 사용자의 모든
  리프레시 토큰이 즉시 죽는다. (이전에는 쿠키만 지워서 최대 30일 살아 있었다)
- jti 단위 denylist 와 달리 저장량이 사용자당 1건으로 고정돼 정리(GC)가 필요 없다.

저장 위치는 다른 서비스와 같은 규칙을 따른다.
  GCS  : users/{email}/auth_state.json
  로컬 : {PDF_UPLOAD_DIR 상위}/auth_state/{email}.json   (USE_LOCAL_STORAGE=True)

읽기는 `/auth/refresh` 에서만 일어나고 액세스 토큰 수명이 30분이라 사용자당
30분에 한 번 수준이다. 핫 패스가 아니므로 캐시를 두지 않는다 — 캐시 TTL 만큼
폐기가 늦게 반영되는 창을 만들지 않기 위해서다.
"""
import asyncio
import json
import os
import re
from datetime import datetime, timezone
from typing import Optional

from app.config import settings
from app.utils.logger import logger


def now_ms() -> int:
    """현재 시각(UTC) 밀리초. 토큰의 iat_ms 와 폐기 시각이 공유하는 단위."""
    return int(datetime.now(timezone.utc).timestamp() * 1000)


def _safe_email(email: str) -> str:
    """파일/blob 경로에 쓸 수 있게 이메일을 정규화한다 (경로 순회 방어).

    구분자를 없애는 것만으로도 순회는 막히지만, `..` 자체도 남기지 않는다.
    """
    safe = re.sub(r"[^a-z0-9._@+-]", "_", (email or "").lower())
    return safe.replace("..", "_")


def _blob_path(email: str) -> str:
    return f"users/{_safe_email(email)}/auth_state.json"


def _local_path(email: str) -> str:
    base_dir = os.path.dirname(os.path.normpath(settings.PDF_UPLOAD_DIR)) or "."
    return os.path.join(base_dir, "auth_state", f"{_safe_email(email)}.json")


def _read_state(email: str) -> dict:
    """저장된 인증 상태. 없거나 읽기 실패면 빈 dict."""
    try:
        if settings.USE_LOCAL_STORAGE:
            path = _local_path(email)
            if not os.path.isfile(path):
                return {}
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)

        from app.services.metadata_service import _get_bucket

        blob = _get_bucket().blob(_blob_path(email))
        if not blob.exists():
            return {}
        return json.loads(blob.download_as_text())
    except Exception as e:
        # fail-open: 저장소 장애로 전 사용자가 로그아웃되는 상황을 만들지 않는다.
        # (폐기 반영이 늦어질 뿐, 토큰 서명·만료 검증은 그대로 유효하다)
        logger.error(f"❌ [TokenRevocation] 인증 상태 읽기 실패 ({email}): {e}")
        return {}


def _write_state(email: str, state: dict) -> None:
    payload = json.dumps(state, ensure_ascii=False)
    if settings.USE_LOCAL_STORAGE:
        path = _local_path(email)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write(payload)
        return

    from app.services.metadata_service import _get_bucket

    blob = _get_bucket().blob(_blob_path(email))
    blob.upload_from_string(payload, content_type="application/json")


def get_revoked_before_ms(email: str) -> int:
    """이 시각(ms) '이하'에 발급된 리프레시 토큰은 폐기된 것으로 본다. 없으면 0."""
    return int(_read_state(email).get("refresh_revoked_before_ms") or 0)


def revoke_all_refresh_tokens(email: str) -> int:
    """해당 사용자의 기존 리프레시 토큰을 전부 폐기한다. 적용된 폐기 시각(ms) 반환."""
    ts = now_ms()
    try:
        state = _read_state(email)
        state["refresh_revoked_before_ms"] = ts
        state["revoked_at"] = datetime.now(timezone.utc).isoformat()
        _write_state(email, state)
        logger.info(f"🔒 [TokenRevocation] 리프레시 토큰 전체 폐기: {email}")
    except Exception as e:
        # 로그아웃 자체(쿠키 삭제)는 성공시켜야 하므로 삼키고 로그만 남긴다.
        logger.error(f"❌ [TokenRevocation] 폐기 기록 실패 ({email}): {e}")
    return ts


def is_revoked(email: str, issued_at_ms: Optional[int]) -> bool:
    """토큰의 발급 시각이 폐기 시각 이하이면 True.

    `iat_ms` 가 없는 토큰은 이 기능 도입 이전에 발급된 레거시 토큰이다.
    폐기 기록이 있는 사용자라면 발급 시점을 알 수 없으므로 안전 쪽(폐기)으로 본다.
    """
    revoked_before = get_revoked_before_ms(email)
    if revoked_before <= 0:
        return False
    if issued_at_ms is None:
        return True
    return issued_at_ms <= revoked_before


# ── Async wrappers (asyncio.to_thread) ──────────────────────────────────────

async def is_revoked_async(email: str, issued_at_ms: Optional[int]) -> bool:
    return await asyncio.to_thread(is_revoked, email, issued_at_ms)


async def revoke_all_refresh_tokens_async(email: str) -> int:
    return await asyncio.to_thread(revoke_all_refresh_tokens, email)
