from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.utils.logger import logger
import os
import time
import traceback

# 디렉토리 확인 및 생성
if not os.path.exists(settings.PDF_UPLOAD_DIR):
    os.makedirs(settings.PDF_UPLOAD_DIR)

app = FastAPI(title="Vision RAG API", version="1.0.0")

# API 로깅 및 전역 예외 처리 미들웨어
@app.middleware("http")
async def logging_and_exception_middleware(request: Request, call_next):
    start_time = time.time()
    method = request.method
    path = request.url.path
    query_params = request.url.query
    
    # 헬스체크 경로는 간소하게 로깅하거나 스킵 가능
    is_health_check = path == "/"
    
    if not is_health_check:
        logger.info(f"▶ [REQUEST] {method} {path} (Query: {query_params})")
        
    try:
        response = await call_next(request)
        process_time = (time.time() - start_time) * 1000
        
        if not is_health_check:
            logger.info(
                f"◀ [RESPONSE] {method} {path} - Status: {response.status_code} - Latency: {process_time:.2f}ms"
            )
        return response
    except Exception as exc:
        process_time = (time.time() - start_time) * 1000
        logger.error(
            f"❌ [ERROR] {method} {path} 실패 - Latency: {process_time:.2f}ms\n"
            f"예외 타입: {type(exc).__name__}\n"
            f"상세 내용: {str(exc)}\n"
            f"Stack Trace:\n{traceback.format_exc()}"
        )
        return JSONResponse(
            status_code=500,
            content={"detail": "서버 내부 오류가 발생했습니다. 로그를 확인해 주세요."}
        )

# CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {"message": "Vision RAG API Server is running"}

# 라우터 등록
from app.routers import upload, documents, chat
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])

