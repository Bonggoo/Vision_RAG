"""
PDF 분석 작업 큐 서비스.

CLOUD_TASKS_QUEUE 설정 시 Google Cloud Tasks로 작업을 위임합니다.
미설정 시 asyncio.create_task()로 인프라 의존 없이 로컬 실행합니다.

Cloud Tasks 사용 시 Cloud Run 인스턴스 유실에도 재시도가 보장됩니다.
"""
import asyncio
import json
from app.config import settings
from app.utils.logger import logger


async def enqueue_analysis(
    document_id: str,
    filename: str,
    file_hash: str,
    owner_email: str,
) -> bool:
    """
    PDF 분석 작업을 큐에 등록합니다.
    CLOUD_TASKS_QUEUE 미설정: asyncio.create_task() 로컬 폴백
    CLOUD_TASKS_QUEUE 설정: Cloud Tasks HTTP 태스크 생성
    """
    if not settings.CLOUD_TASKS_QUEUE:
        _enqueue_local(document_id, filename, file_hash, owner_email)
        return True

    return await _enqueue_cloud_tasks(document_id, filename, file_hash, owner_email)


def _enqueue_local(
    document_id: str, filename: str, file_hash: str, owner_email: str
) -> None:
    """로컬 개발용: 현재 이벤트 루프에 태스크로 등록."""
    from app.routers.upload import _run_analysis_pipeline
    asyncio.create_task(
        _run_analysis_pipeline(document_id, filename, file_hash, owner_email)
    )
    logger.info(f"📌 [로컬] PDF 분석 태스크 등록: {document_id}")


async def _enqueue_cloud_tasks(
    document_id: str, filename: str, file_hash: str, owner_email: str
) -> bool:
    """Cloud Tasks HTTP 태스크 생성."""
    try:
        from google.cloud import tasks_v2

        client = tasks_v2.CloudTasksClient()

        payload = json.dumps({
            "document_id": document_id,
            "filename": filename,
            "file_hash": file_hash,
            "owner_email": owner_email,
        }).encode()

        headers = {"Content-Type": "application/json"}
        if settings.INTERNAL_TASK_SECRET:
            headers["X-Task-Secret"] = settings.INTERNAL_TASK_SECRET

        task = tasks_v2.Task(
            http_request=tasks_v2.HttpRequest(
                http_method=tasks_v2.HttpMethod.POST,
                url=f"{settings.CLOUD_RUN_URL.rstrip('/')}/internal/analyze",
                headers=headers,
                body=payload,
            )
        )

        await asyncio.to_thread(
            client.create_task,
            parent=settings.CLOUD_TASKS_QUEUE,
            task=task,
        )
        logger.info(f"✅ [Cloud Tasks] PDF 분석 태스크 등록: {document_id}")
        return True

    except Exception as e:
        logger.error(f"❌ [Cloud Tasks] 태스크 등록 실패: {e} — 로컬 폴백 실행")
        _enqueue_local(document_id, filename, file_hash, owner_email)
        return False
