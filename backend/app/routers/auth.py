from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services.auth_service import verify_google_token, create_access_token

router = APIRouter(prefix="/auth", tags=["Authentication"])

class GoogleLoginRequest(BaseModel):
    credential: str  # Google이 발행한 ID Token JWT

class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    email: str
    name: str
    picture: str

@router.post("/google", response_model=LoginResponse)
async def google_login(payload: GoogleLoginRequest):
    """
    구글 OAuth 로그인 & JWT 발급 엔드포인트
    1. 프론트엔드에서 전달받은 구글 ID Token 검증
    2. 검증 성공 시 백엔드 전용 access_token 발행 (누구나 접근 가능)
    """
    # 1. 구글 토큰 검증
    user_info = verify_google_token(payload.credential)
    email = user_info["email"]
    
    # 2. 자체 JWT Access Token 발행
    access_token = create_access_token(
        data={
            "email": email,
            "name": user_info["name"],
            "picture": user_info["picture"]
        }
    )
    
    return LoginResponse(
        access_token=access_token,
        email=email,
        name=user_info["name"],
        picture=user_info["picture"]
    )
