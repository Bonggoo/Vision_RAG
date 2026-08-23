import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional
from fastapi import Depends, HTTPException, status, Response
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.config import settings
from app.utils.logger import logger

# Bearer Token 추출 스키마 (보안)
security_recipient = HTTPBearer(auto_error=False)

def verify_google_token(credential: str) -> dict:
    """구글 ID 토큰 검증"""
    try:
        # settings.GOOGLE_CLIENT_ID가 비어 있으면 구글 로그인을 아예 막거나, 검증 단계에서 걸러냅니다.
        id_info = id_token.verify_oauth2_token(
            credential, 
            google_requests.Request(), 
            settings.GOOGLE_CLIENT_ID if settings.GOOGLE_CLIENT_ID else None
        )
        
        # 발행처 검증 (accounts.google.com)
        if id_info["iss"] not in ["accounts.google.com", "https://accounts.google.com"]:
            raise ValueError("잘못된 토큰 발행처(iss)입니다.")
            
        return {
            "email": id_info.get("email", "").lower(),
            "name": id_info.get("name", ""),
            "picture": id_info.get("picture", "")
        }
    except Exception as e:
        logger.error(f"구글 토큰 검증 실패: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="구글 로그인이 만료되었거나 올바르지 않은 토큰입니다."
        )

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """자체 JWT Access Token 생성"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire, "type": "access"})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def create_refresh_token(email: str) -> str:
    """JWT Refresh Token 생성 (email + 발급 시각)

    `iat_ms`(밀리초)는 서버 측 폐기 판정용이다. 표준 `iat`(초)를 쓰지 않는 이유는
    로그아웃 직후 재로그인이 같은 '초'에 일어나면 새 토큰까지 폐기 대상으로
    걸리기 때문이다. → app/services/token_revocation.py
    """
    from app.services.token_revocation import now_ms

    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode = {"email": email, "exp": expire, "type": "refresh", "iat_ms": now_ms()}
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_recipient)) -> dict:
    """
    현재 접속 유저 검증 의존성 (Dependencies)
    - 헤더에 Authorization: Bearer <JWT> 형태로 들어오는 백엔드 JWT를 검증
    - 구글 계정으로 정상 로그인한 사용자라면 누구나 접근 허용 (화이트리스트 제거)
    """
    # 로컬 개발 모드: JWT 토큰이 없고 구글 클라이언트 ID가 없는 로컬 스토리지 모드인 경우에만 더미 유저 허용
    if not credentials and not settings.GOOGLE_CLIENT_ID:
        if settings.USE_LOCAL_STORAGE:
            return {"email": "local-dev@visionrag.app", "name": "Dev User", "picture": ""}
        else:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="인증 헤더가 누락되었습니다."
            )

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 헤더가 누락되었습니다."
        )
        
    token = credentials.credentials
    try:
        # JWT 해독
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        
        # Refresh Token으로 API 접근 차단
        if payload.get("type") != "access":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Access Token이 아닙니다."
            )
        
        email = payload.get("email", "").lower()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT 토큰에 이메일 정보가 누락되었습니다."
            )
            
        # 구글 인증된 유저라면 접근 허용 (화이트리스트 제거됨)
        logger.info(f"유저 인증 성공: {email}")
            
        return {
            "email": email,
            "name": payload.get("name", ""),
            "picture": payload.get("picture", "")
        }
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="세션이 만료되었습니다. 다시 로그인해 주세요."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="올바르지 않은 세션 토큰입니다."
        )

def decode_refresh_token(refresh_token: str) -> dict:
    """Refresh Token을 검증(서명·만료·타입)하고 페이로드를 반환합니다."""
    try:
        payload = jwt.decode(refresh_token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        if payload.get("type") != "refresh":
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh Token이 아닙니다."
            )
        email = payload.get("email", "").lower()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Refresh Token에 이메일 정보가 누락되었습니다."
            )
        payload["email"] = email
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh Token이 만료되었습니다. 다시 로그인해 주세요."
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="올바르지 않은 Refresh Token입니다."
        )


def verify_refresh_token(refresh_token: str) -> str:
    """Refresh Token 검증 후 email 반환 (서버 측 폐기 검사는 하지 않음)"""
    return decode_refresh_token(refresh_token)["email"]


async def verify_refresh_token_async(refresh_token: str) -> str:
    """Refresh Token 검증 + 서버 측 폐기 검사 후 email 반환.

    로그아웃한 사용자의 (유출된) 리프레시 토큰이 만료 전까지 계속 통하던 구멍을
    막는다. 저장소 조회가 필요해 async 다. → 감사 항목 H-3
    """
    from app.services.token_revocation import is_revoked_async

    payload = decode_refresh_token(refresh_token)
    email = payload["email"]

    if await is_revoked_async(email, payload.get("iat_ms")):
        logger.warning(f"⛔ 폐기된 Refresh Token 사용 시도: {email}")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그아웃된 세션입니다. 다시 로그인해 주세요."
        )
    return email


def email_from_refresh_token_unverified(refresh_token: str) -> Optional[str]:
    """만료 여부와 무관하게 리프레시 토큰에서 email만 꺼낸다 (로그아웃 폐기용).

    로그아웃은 만료된 토큰으로도 호출될 수 있고, 그때도 폐기 시각은 올려두는 편이
    안전하다. 서명은 그대로 검증하므로 남의 계정을 폐기시킬 수는 없다.
    """
    try:
        payload = jwt.decode(
            refresh_token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"verify_exp": False},
        )
        if payload.get("type") != "refresh":
            return None
        return (payload.get("email") or "").lower() or None
    except jwt.InvalidTokenError:
        return None


def set_refresh_cookie(response: Response, refresh_token: str):
    """브라우저 쿠키에 Refresh Token 설정 (XSS 방어)

    통합 오리진(프론트+백엔드 same-origin) 구조이므로 SameSite=Lax로 충분하고,
    cross-site(None) 대비 iOS WebKit(ITP)의 third-party 쿠키 차단에 걸리지 않는다.
    secure는 프로덕션(HTTPS)에서만 True, 로컬(http)에서는 False.
    """
    is_local = settings.USE_LOCAL_STORAGE or not settings.GOOGLE_CLIENT_ID

    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=not is_local,
        samesite="lax",
        max_age=settings.REFRESH_TOKEN_EXPIRE_DAYS * 24 * 3600,
        path="/"
    )


def delete_refresh_cookie(response: Response):
    """브라우저 쿠키에서 Refresh Token 삭제 (로그아웃용)"""
    is_local = settings.USE_LOCAL_STORAGE or not settings.GOOGLE_CLIENT_ID

    response.delete_cookie(
        key="refresh_token",
        httponly=True,
        secure=not is_local,
        samesite="lax",
        path="/"
    )

