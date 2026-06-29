"""
Cloud Tasks → Cloud Run 내부 콜백 엔드포인트.
X-Task-Secret 헤더로 요청을 검증합니다.
"""
from fastapi import APIRouter, HTTPException, Header
from pydantic import BaseModel
from typing import Optional
from app.config import settings
from app.utils.logger import logger

router = APIRouter()


class AnalyzeTaskPayload(BaseModel):
    document_id: str
    filename: str
    file_hash: str
    owner_email: str


@router.post("/analyze")
async def internal_analyze(
    payload: AnalyzeTaskPayload,
    x_task_secret: Optional[str] = Header(None),
):
    """
    Cloud Tasks가 호출하는 PDF 분석 콜백.
    INTERNAL_TASK_SECRET이 설정된 경우 헤더 검증.
    """
    if settings.INTERNAL_TASK_SECRET and x_task_secret != settings.INTERNAL_TASK_SECRET:
        logger.warning(f"⛔ /internal/analyze 인증 실패 (document_id={payload.document_id})")
        raise HTTPException(status_code=401, detail="Unauthorized")

    logger.info(f"📥 [internal] Cloud Tasks 콜백 수신: {payload.document_id}")

    from app.routers.upload import _run_analysis_pipeline
    await _run_analysis_pipeline(
        payload.document_id,
        payload.filename,
        payload.file_hash,
        payload.owner_email,
    )

    return {"status": "ok", "document_id": payload.document_id}
