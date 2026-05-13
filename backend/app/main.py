from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
import os

# 디렉토리 확인 및 생성
if not os.path.exists(settings.PDF_UPLOAD_DIR):
    os.makedirs(settings.PDF_UPLOAD_DIR)

app = FastAPI(title="Vision RAG API", version="1.0.0")

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
