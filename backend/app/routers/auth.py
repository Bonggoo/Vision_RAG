from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services.auth_service import (
    verify_google_token, create_access_token, create_refresh_token, verify_refresh_token
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    credential: str  # Google이 발행한 ID Token JWT

class LoginResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    email: str
    name: str
    picture: str

class RefreshRequest(BaseModel):
    refresh_token: str

class RefreshResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"

@router.post("/google", response_model=LoginResponse)
async def google_login(payload: GoogleLoginRequest):
    """
    구글 OAuth 로그인 & JWT 발급 엔드포인트
    1. 프론트엔드에서 전달받은 구글 ID Token 검증
    2. 검증 성공 시 백엔드 전용 access_token + refresh_token 발행 (누구나 접근 가능)
    """
    # 1. 구글 토큰 검증
    user_info = verify_google_token(payload.credential)
    email = user_info["email"]
    
    # 2. 자체 JWT Access Token + Refresh Token 발행
    access_token = create_access_token(
        data={
            "email": email,
            "name": user_info["name"],
            "picture": user_info["picture"]
        }
    )
    refresh_token = create_refresh_token(email)
    
    return LoginResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        email=email,
        name=user_info["name"],
        picture=user_info["picture"]
    )

@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(payload: RefreshRequest):
    """
    Refresh Token으로 새 Access Token + Refresh Token 발급
    - 클라이언트의 Access Token이 만료되었을 때 호출
    """
    # 1. Refresh Token 검증 → email 추출
    email = verify_refresh_token(payload.refresh_token)
    
    # 2. 새 토큰 쌍 발급
    new_access_token = create_access_token(data={"email": email})
    new_refresh_token = create_refresh_token(email)
    
    return RefreshResponse(
        access_token=new_access_token,
        refresh_token=new_refresh_token
    )
