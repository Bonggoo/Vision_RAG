from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from app.services.auth_service import verify_google_token, create_access_token, get_allowed_users_list

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
    2. 사용자 이메일이 화이트리스트(ALLOWED_USERS)에 포함되어 있는지 체크
    3. 포함되어 있다면 백엔드 전용 access_token 발행
    """
    # 1. 구글 토큰 검증
    user_info = verify_google_token(payload.credential)
    email = user_info["email"]
    
    # 2. 화이트리스트 검사 (ALLOWED_USERS가 비어있지 않은 경우에만 통제)
    allowed_users = get_allowed_users_list()
    if allowed_users and (email not in allowed_users):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="접근 권한이 허가되지 않은 구글 계정입니다. 관리자(Bonggoo)에게 등록을 요청하세요."
        )
        
    # 3. 자체 JWT Access Token 발행
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
