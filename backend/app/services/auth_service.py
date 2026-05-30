import jwt
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from google.oauth2 import id_token
from google.auth.transport import requests as google_requests

from app.config import settings

logger = logging.getLogger(__name__)

# Bearer Token 추출 스키마 (보안)
security_recipient = HTTPBearer(auto_error=False)

def get_allowed_users_list() -> List[str]:
    """쉼표로 구분된 화이트리스트 이메일 리스트 파싱"""
    if not settings.ALLOWED_USERS:
        return []
    return [email.strip().lower() for email in settings.ALLOWED_USERS.split(",") if email.strip()]

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
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt

def get_current_user(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security_recipient)) -> dict:
    """
    현재 접속 유저 검증 의존성 (Dependencies)
    - 헤더에 Authorization: Bearer <JWT> 형태로 들어오는 백엔드 JWT를 검증
    - 이메일이 화이트리스트(ALLOWED_USERS)에 있는지 실시간 확인
    """
    # 환경변수에 ALLOWED_USERS가 설정되지 않았거나 비어 있다면 인증 필터를 무시하고 개발 모드로 둡니다.
    # (개발 편의성 및 로컬 테스트 호환성 유지)
    if not settings.ALLOWED_USERS:
        return {"email": "local-dev@visionrag.app", "name": "Dev User", "picture": ""}

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="인증 헤더가 누락되었습니다."
        )
        
    token = credentials.credentials
    try:
        # JWT 해독
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        email = payload.get("email", "").lower()
        if not email:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="JWT 토큰에 이메일 정보가 누락되었습니다."
            )
            
        # 화이트리스트 검사
        allowed_users = get_allowed_users_list()
        if email not in allowed_users:
            logger.warning(f"비인가 유저 접속 차단 시도: {email}")
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="접근 권한이 허가되지 않은 이메일 계정입니다."
            )
            
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
