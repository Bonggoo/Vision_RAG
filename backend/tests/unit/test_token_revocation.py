"""리프레시 토큰 서버 측 폐기 테스트 (감사 H-3)."""
import asyncio
import time

import jwt
import pytest
from fastapi import HTTPException

from app.config import settings
from app.services import auth_service, token_revocation


@pytest.fixture(autouse=True)
def _isolated_storage(tmp_path, monkeypatch):
    """폐기 상태를 테스트마다 빈 임시 디렉토리에 격리한다."""
    monkeypatch.setattr(settings, "PDF_UPLOAD_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(settings, "USE_LOCAL_STORAGE", True)
    yield


EMAIL = "user@example.com"


# ── 토큰 발급 ────────────────────────────────────────────────────────────────

def test_리프레시_토큰에_발급시각이_들어간다():
    token = auth_service.create_refresh_token(EMAIL)
    payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
    assert payload["type"] == "refresh"
    assert isinstance(payload["iat_ms"], int)
    assert payload["iat_ms"] > 0


# ── 폐기 판정 ────────────────────────────────────────────────────────────────

def test_폐기_기록이_없으면_통과():
    assert token_revocation.is_revoked(EMAIL, token_revocation.now_ms()) is False


def test_로그아웃하면_기존_토큰이_전부_죽는다():
    issued = token_revocation.now_ms()
    token_revocation.revoke_all_refresh_tokens(EMAIL)
    assert token_revocation.is_revoked(EMAIL, issued) is True


def test_폐기_이후_발급된_토큰은_살아있다():
    """로그아웃 직후 다시 로그인한 세션까지 막으면 안 된다."""
    token_revocation.revoke_all_refresh_tokens(EMAIL)
    time.sleep(0.005)  # iat_ms 가 폐기 시각보다 확실히 뒤가 되도록
    reissued = token_revocation.now_ms()
    assert token_revocation.is_revoked(EMAIL, reissued) is False


def test_다른_사용자는_영향받지_않는다():
    issued = token_revocation.now_ms()
    token_revocation.revoke_all_refresh_tokens("other@example.com")
    assert token_revocation.is_revoked(EMAIL, issued) is False


def test_iat가_없는_레거시_토큰은_폐기_대상으로_본다():
    """발급 시점을 알 수 없으니 안전한 쪽(폐기)으로 판정해야 한다."""
    token_revocation.revoke_all_refresh_tokens(EMAIL)
    assert token_revocation.is_revoked(EMAIL, None) is True


def test_폐기_기록이_없으면_레거시_토큰도_통과():
    """기능 도입 전 발급된 토큰이 배포 즉시 전부 끊기지 않아야 한다."""
    assert token_revocation.is_revoked(EMAIL, None) is False


def test_저장소_오류는_fail_open(monkeypatch):
    """저장소 장애로 전 사용자가 로그아웃되는 상황을 만들지 않는다."""
    def boom(*_a, **_k):
        raise RuntimeError("storage down")

    monkeypatch.setattr(token_revocation, "_read_state", lambda email: {})
    monkeypatch.setattr(token_revocation, "_write_state", boom)
    token_revocation.revoke_all_refresh_tokens(EMAIL)  # 예외가 새어나오면 로그아웃이 실패한다


def test_이메일이_경로를_벗어나지_못한다():
    safe = token_revocation._safe_email("../../etc/passwd")
    assert "/" not in safe
    assert ".." not in safe


# ── 검증 경로 통합 ───────────────────────────────────────────────────────────

def test_폐기된_토큰으로_갱신하면_401():
    # 레포 컨벤션에 맞춰 pytest-asyncio 없이 asyncio.run 으로 처리한다.
    token = auth_service.create_refresh_token(EMAIL)
    assert asyncio.run(auth_service.verify_refresh_token_async(token)) == EMAIL

    token_revocation.revoke_all_refresh_tokens(EMAIL)

    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_service.verify_refresh_token_async(token))
    assert exc.value.status_code == 401


def test_액세스_토큰은_리프레시로_통하지_않는다():
    access = auth_service.create_access_token({"email": EMAIL})
    with pytest.raises(HTTPException) as exc:
        asyncio.run(auth_service.verify_refresh_token_async(access))
    assert exc.value.status_code == 401


def test_만료된_토큰에서도_로그아웃용_이메일을_꺼낸다():
    """만료돼도 폐기 시각은 올려두는 편이 안전하다."""
    expired = jwt.encode(
        {"email": EMAIL, "type": "refresh", "exp": 1, "iat_ms": 1000},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    assert auth_service.email_from_refresh_token_unverified(expired) == EMAIL


def test_서명이_틀리면_남의_계정을_폐기시킬_수_없다():
    forged = jwt.encode({"email": EMAIL, "type": "refresh"}, "wrong-secret", algorithm="HS256")
    assert auth_service.email_from_refresh_token_unverified(forged) is None
