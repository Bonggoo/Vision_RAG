"""요청 속도 제한 미들웨어 단위 테스트 (감사 H-1)."""
import jwt
import pytest

from app.config import settings
from app.middleware import rate_limit


@pytest.fixture(autouse=True)
def _clean():
    rate_limit.reset()
    yield
    rate_limit.reset()


class _FakeClient:
    def __init__(self, host):
        self.host = host


class _FakeRequest:
    """미들웨어가 읽는 부분(headers/client)만 흉내낸다."""

    def __init__(self, headers=None, host="1.2.3.4"):
        self.headers = headers or {}
        self.client = _FakeClient(host)


# ── 버킷 분류 ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("path,expected", [
    ("/chat/stream", "chat"),
    ("/upload", "upload"),
    ("/upload/preflight", "upload"),
    ("/documents/reclassify", "upload"),
    ("/api/auth/google", "auth"),
    ("/api/auth/refresh", "auth"),
    ("/documents", "default"),
    ("/conversations/", "default"),
])
def test_버킷_분류(path, expected):
    assert rate_limit._bucket_for(path) == expected


@pytest.mark.parametrize("path", [
    "/api/health",           # 헬스체크는 주기 호출
    "/internal/analyze",     # 자체 시크릿으로 보호됨
    "/",                     # 정적 프론트
    "/_next/static/chunk.js",
    "/manifest.json",
])
def test_제한_대상이_아닌_경로(path):
    """정적 자산까지 세면 페이지 한 번 로드에 한도가 터진다."""
    assert rate_limit._bucket_for(path) is None


# ── 슬라이딩 윈도우 ──────────────────────────────────────────────────────────

def test_한도까지는_통과하고_초과하면_차단():
    rules = ((60, 3),)
    assert rate_limit._check("k", rules) is None
    assert rate_limit._check("k", rules) is None
    assert rate_limit._check("k", rules) is None

    retry_after = rate_limit._check("k", rules)
    assert retry_after is not None and retry_after > 0


def test_키가_다르면_카운터가_섞이지_않는다():
    rules = ((60, 1),)
    assert rate_limit._check("a", rules) is None
    assert rate_limit._check("b", rules) is None
    assert rate_limit._check("a", rules) is not None


def test_긴_윈도우도_함께_적용된다():
    """분당 한도에 안 걸려도 시간당 한도에는 걸려야 한다."""
    rules = ((60, 100), (3600, 2))
    assert rate_limit._check("k", rules) is None
    assert rate_limit._check("k", rules) is None
    assert rate_limit._check("k", rules) is not None


# ── 식별자 ───────────────────────────────────────────────────────────────────

def test_유효한_JWT는_사용자_단위로_식별된다():
    token = jwt.encode(
        {"email": "A@Example.com", "type": "access"},
        settings.JWT_SECRET,
        algorithm=settings.JWT_ALGORITHM,
    )
    req = _FakeRequest({"authorization": f"Bearer {token}"})
    assert rate_limit._identity(req) == "user:a@example.com"


def test_위조_토큰은_IP로_떨어진다():
    """서명 검증에 실패한 토큰의 이메일을 믿으면 키를 무한히 흩뿌려 제한을 우회할 수 있다."""
    forged = jwt.encode({"email": "x@y.com", "type": "access"}, "wrong-secret", algorithm="HS256")
    req = _FakeRequest({"authorization": f"Bearer {forged}"}, host="9.9.9.9")
    assert rate_limit._identity(req) == "ip:9.9.9.9"


def test_토큰이_없으면_XFF_첫_항목을_쓴다():
    req = _FakeRequest({"x-forwarded-for": "203.0.113.7, 10.0.0.1"}, host="10.0.0.1")
    assert rate_limit._identity(req) == "ip:203.0.113.7"


def test_같은_IP라도_사용자가_다르면_따로_센다():
    def tok(email):
        return jwt.encode(
            {"email": email, "type": "access"}, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM
        )

    a = _FakeRequest({"authorization": f"Bearer {tok('a@x.com')}"})
    b = _FakeRequest({"authorization": f"Bearer {tok('b@x.com')}"})
    assert rate_limit._identity(a) != rate_limit._identity(b)
