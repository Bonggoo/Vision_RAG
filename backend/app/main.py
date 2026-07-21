from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.utils.logger import logger
import os
import time
import traceback

# 💡 [버그 패치] 비연속(Sparse) PDF 생성 및 텍스트 탐색 오버헤드 패치 적용 완료

# 디렉토리 확인 및 생성
if not os.path.exists(settings.PDF_UPLOAD_DIR):
    os.makedirs(settings.PDF_UPLOAD_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. JWT_SECRET 기본값 위협 검증
    DEFAULT_SECRET = "vision-rag-jwt-secret-key-change-in-production-12345"
    if settings.JWT_SECRET == DEFAULT_SECRET and not settings.USE_LOCAL_STORAGE:
        logger.critical("❌ [보안 위협] 프로덕션 환경에서 하드코딩된 레거시 JWT_SECRET 키가 감지되었습니다. 서버 실행을 중단합니다.")
        import sys
        sys.exit("Critical Security Error: Please set a secure JWT_SECRET environment variable.")

    # 1-2. INTERNAL_TASK_SECRET 미설정 위협 검증 (fail-closed)
    # /internal/analyze는 --allow-unauthenticated로 인터넷에 노출되며, 이 시크릿이 유일한 관문.
    # 미설정 시 헤더 검증이 통째로 스킵되어 무인증 노출되므로 프로덕션 부팅을 차단한다.
    if not settings.INTERNAL_TASK_SECRET and not settings.USE_LOCAL_STORAGE:
        logger.critical("❌ [보안 위협] 프로덕션 환경에서 INTERNAL_TASK_SECRET이 비어 있습니다. /internal/analyze 무인증 노출을 방지하기 위해 서버 실행을 중단합니다.")
        import sys
        sys.exit("Critical Security Error: Please set the INTERNAL_TASK_SECRET environment variable.")

    # 1-3. GOOGLE_CLIENT_ID 미설정 위협 검증 (fail-closed)
    # 비어 있으면 verify_oauth2_token의 audience=None으로 aud 검증이 스킵되어,
    # 다른 OAuth 클라이언트용 구글 ID 토큰도 통과할 수 있다. 프로덕션 부팅을 차단한다.
    if not settings.GOOGLE_CLIENT_ID and not settings.USE_LOCAL_STORAGE:
        logger.critical("❌ [보안 위협] 프로덕션 환경에서 GOOGLE_CLIENT_ID가 비어 있습니다. OAuth audience 검증 우회를 방지하기 위해 서버 실행을 중단합니다.")
        import sys
        sys.exit("Critical Security Error: Please set the GOOGLE_CLIENT_ID environment variable.")

    # 2. 서버 기동 시 기존 레거시 제조사 정규화 마이그레이션 자동 수행 (부팅 지연 예방을 위해 백그라운드 태스크로 처리)
    try:
        import asyncio
        from app.services.metadata_service import migrate_legacy_manufacturers
        asyncio.create_task(asyncio.to_thread(migrate_legacy_manufacturers))
        logger.info("🔄 레거시 제조사 정규화 마이그레이션을 백그라운드에서 백그라운드 태스크로 실행 중...")
    except Exception as e:
        logger.error(f"❌ 시작 마이그레이션 비동기 실행 실패: {e}")

    yield


app = FastAPI(title="Vision RAG API", version="1.0.0", redirect_slashes=False, lifespan=lifespan)

# API 로깅 및 전역 예외 처리 미들웨어
@app.middleware("http")
async def logging_and_exception_middleware(request: Request, call_next):
    start_time = time.time()
    method = request.method
    path = request.url.path
    query_params = request.url.query
    
    # 헬스체크는 주기적으로 호출되므로 로그에서 제외한다.
    # (통합 오리진 전환으로 `/`는 정적 index를 서빙하고 헬스체크는 /api/health로 이동했다)
    is_health_check = path == "/api/health"
    
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
    expose_headers=["Content-Disposition"],
)

@app.get("/api/health")
async def healthz():
    """헬스체크. (루트 `/`는 정적 프론트가 서빙하므로 여기로 이동)

    주의: `/healthz`는 쓰지 말 것 — Cloud Run(Knative) 인프라가 이 경로를 자체
    내부 헬스체크용으로 예약해 컨테이너까지 도달하지 않고 가로챈다(실측 확인됨).
    """
    return {"message": "Vision RAG API Server is running"}

# 라우터 등록
from app.routers import upload, documents, chat, auth, conversations, internal
app.include_router(auth.router, prefix="/api", tags=["Auth"])
app.include_router(upload.router, prefix="/upload", tags=["Upload"])
app.include_router(documents.router, prefix="/documents", tags=["Documents"])
app.include_router(chat.router, prefix="/chat", tags=["Chat"])
app.include_router(conversations.router, prefix="/conversations", tags=["Conversations"])
app.include_router(internal.router, prefix="/internal", tags=["Internal"])

# ── 정적 프론트엔드 서빙 (통합 오리진) ─────────────────────────────────────
# 프론트엔드(Next.js) 정적 export 결과물을 같은 오리진에서 서빙한다.
# API 라우터를 먼저 등록했으므로 /api·/upload·/documents·/chat·/conversations·/internal 은
# API가 우선 매칭되고, 그 외 경로(/, /_next/*, /manifest.json 등)는 정적 파일로 폴백된다.
# `static/` 디렉토리는 CI 빌드 시 프론트 out/이 복사되어 생성됨. 로컬 dev(빌드 없음)에선
# 디렉토리가 없으므로 마운트를 건너뛰어 API 전용으로 동작한다.
_STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "static")
if os.path.isdir(_STATIC_DIR):
    from fastapi.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="spa")
    logger.info(f"🖥️ 정적 프론트엔드 서빙 활성화: {_STATIC_DIR}")
else:
    logger.info("ℹ️ static/ 디렉토리 없음 → API 전용 모드 (로컬 dev)")

