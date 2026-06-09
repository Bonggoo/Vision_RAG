from fastapi import APIRouter, HTTPException, status, Response, Cookie
from pydantic import BaseModel
from typing import Optional
from app.services.auth_service import (
    verify_google_token, create_access_token, create_refresh_token, verify_refresh_token,
    set_refresh_cookie, delete_refresh_cookie
)

router = APIRouter(prefix="/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    credential: str  # Google이 발행한 ID Token JWT

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    name: str
    picture: str

class RefreshResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

@router.post("/google", response_model=LoginResponse)
async def google_login(payload: GoogleLoginRequest, response: Response):
    """
    구글 OAuth 로그인 & JWT 발급 엔드포인트
    1. 프론트엔드에서 전달받은 구글 ID Token 검증
    2. 검증 성공 시 백엔드 전용 access_token 발행 및 refresh_token을 HttpOnly 쿠키로 설정
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
    
    # 3. Refresh Token을 HttpOnly 보안 쿠키로 설정
    set_refresh_cookie(response, refresh_token)
    
    return LoginResponse(
        access_token=access_token,
        email=email,
        name=user_info["name"],
        picture=user_info["picture"]
    )

@router.post("/refresh", response_model=RefreshResponse)
async def refresh_tokens(response: Response, refresh_token: Optional[str] = Cookie(None)):
    """
    Cookie의 Refresh Token으로 새 Access Token 발급 및 Refresh Token 재설정
    """
    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="로그인 세션이 만료되었습니다. 다시 로그인해 주세요."
        )
        
    # 1. Refresh Token 검증 → email 추출
    email = verify_refresh_token(refresh_token)
    
    # 2. 새 토큰 쌍 발급
    new_access_token = create_access_token(data={"email": email})
    new_refresh_token = create_refresh_token(email)
    
    # 3. 새 Refresh Token을 쿠키로 재등록
    set_refresh_cookie(response, new_refresh_token)
    
    return RefreshResponse(
        access_token=new_access_token
    )

@router.post("/logout")
async def logout(response: Response):
    """
    로그아웃 시 브라우저의 Refresh Token 보안 쿠키 파기
    """
    delete_refresh_cookie(response)
    return {"message": "Successfully logged out"}
