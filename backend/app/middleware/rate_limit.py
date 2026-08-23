"""요청 속도 제한 (rate limiting) — 감사 항목 H-1.

인스턴스 로컬 메모리 기반 슬라이딩 윈도우다. Cloud Run 은 인스턴스마다 독립 카운터를
갖게 되므로 전역 정확도는 없지만, 이 제한의 목적이 '한 클라이언트의 반복 호출로
Gemini 과금이 폭주하거나 인스턴스 동시성(concurrency=8)이 고갈되는 것'을 막는
것이므로 인스턴스당 상한으로 충분하다. 전역 정확도가 필요해지면 카운터 저장소만
Memorystore(Redis) 로 바꾸면 된다.

식별자는 검증된 JWT 의 이메일을 우선 쓰고, 없으면 클라이언트 IP 로 떨어진다.
IP 는 X-Forwarded-For 첫 항목이라 위조 가능하므로(클라이언트가 보낸 XFF 뒤에
Cloud Run 이 실제 IP 를 덧붙인다) 이 제한은 보안 경계가 아니라 방어선 하나로 본다.
"""
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

import jwt
from fastapi import Request
from fastapi.responses import JSONResponse

from app.config import settings
from app.utils.logger import logger

# 버킷별 규칙: ((윈도우 초, 허용 횟수), ...)
# 짧은 윈도우로 순간 폭주를, 긴 윈도우로 지속 폭주를 막는다.
_RULES: Dict[str, Tuple[Tuple[int, int], ...]] = {
    # Gemini 호출이 물려 있어 1회가 가장 비싸다
    "chat": ((60, 20), (3600, 300)),
    # 업로드·재분류: PDF 변환/Vision 분석을 유발
    "upload": ((60, 10), (3600, 100)),
    # 로그인·갱신: 무차별 대입 완화
    "auth": ((60, 20), (3600, 200)),
    # 목록 조회 등 (사이드바 폴링을 막지 않을 만큼 넉넉히)
    "default": ((60, 120),),
}

# 이 프리픽스에 해당하는 경로만 제한한다. 나머지(정적 프론트 `/`, `/_next/*` 등)는
# 한 페이지 로드에 수십 건이 발생하므로 제한 대상이 아니다.
_API_PREFIXES = ("/api/", "/upload", "/documents", "/chat", "/conversations")

# 제한에서 제외: 헬스체크(주기 호출), 내부 콜백(자체 시크릿으로 이미 보호됨)
_EXEMPT_PREFIXES = ("/api/health", "/internal")

_MAX_TRACKED_KEYS = 10_000

_hits: Dict[str, Deque[float]] = {}
_lock = threading.Lock()


def _bucket_for(path: str) -> Optional[str]:
    """경로에 적용할 버킷 이름. 제한 대상이 아니면 None."""
    if path.startswith(_EXEMPT_PREFIXES):
        return None
    if not path.startswith(_API_PREFIXES):
        return None
    if path.startswith("/chat"):
        return "chat"
    if path.startswith("/upload") or path.endswith("/reclassify"):
        return "upload"
    if path.startswith("/api/auth"):
        return "auth"
    return "default"


def _client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _identity(request: Request) -> str:
    """제한 키. 검증된 JWT 이메일이 있으면 사용자 단위, 없으면 IP 단위."""
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        try:
            payload = jwt.decode(
                auth[7:], settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM]
            )
            email = (payload.get("email") or "").lower()
            if email:
                return f"user:{email}"
        except jwt.InvalidTokenError:
            # 위조·만료 토큰은 IP 로 떨어뜨린다 (임의 이메일로 키를 흩뿌리지 못하게)
            pass
    return f"ip:{_client_ip(request)}"


def _sweep_locked(now: float) -> None:
    """가장 긴 윈도우보다 오래된 키를 정리한다. _lock 을 잡은 채로 호출."""
    longest = max(w for rules in _RULES.values() for w, _ in rules)
    stale = [k for k, dq in _hits.items() if not dq or now - dq[-1] > longest]
    for k in stale:
        _hits.pop(k, None)


def _check(key: str, rules: Tuple[Tuple[int, int], ...]) -> Optional[int]:
    """허용이면 None, 초과면 재시도까지 남은 초(Retry-After)를 반환한다."""
    now = time.monotonic()
    longest = max(w for w, _ in rules)

    with _lock:
        if len(_hits) > _MAX_TRACKED_KEYS:
            _sweep_locked(now)

        dq = _hits.setdefault(key, deque())
        while dq and now - dq[0] > longest:
            dq.popleft()

        for window, limit in rules:
            count = sum(1 for ts in dq if now - ts <= window)
            if count >= limit:
                oldest_in_window = next(ts for ts in dq if now - ts <= window)
                return max(1, int(window - (now - oldest_in_window)) + 1)

        dq.append(now)
        return None


def reset() -> None:
    """테스트용 카운터 초기화."""
    with _lock:
        _hits.clear()


async def rate_limit_middleware(request: Request, call_next):
    if not settings.RATE_LIMIT_ENABLED:
        return await call_next(request)

    bucket = _bucket_for(request.url.path)
    if bucket is None:
        return await call_next(request)

    key = f"{bucket}|{_identity(request)}"
    retry_after = _check(key, _RULES[bucket])
    if retry_after is not None:
        logger.warning(
            f"⛔ [RateLimit] {request.method} {request.url.path} 차단 "
            f"(bucket={bucket}, key={key}, retry_after={retry_after}s)"
        )
        return JSONResponse(
            status_code=429,
            content={"detail": "요청이 너무 잦습니다. 잠시 후 다시 시도해 주세요."},
            headers={"Retry-After": str(retry_after)},
        )

    return await call_next(request)
