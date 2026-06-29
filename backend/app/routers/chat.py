"""
질의·응답 스트리밍 라우터.

사용자 질문을 받아 Agentic Search 파이프라인을 실행하고
SSE(Server-Sent Events)로 결과를 스트리밍합니다.
"""
import asyncio
import json
from fastapi import APIRouter, HTTPException, Request, Depends
from fastapi.responses import StreamingResponse
from app.schemas.request import ChatRequest
from app.services.agentic_graph import run_agentic_pipeline
from app.services import metadata_service
from app.services.auth_service import get_current_user
from app.utils.logger import logger

router = APIRouter()


async def _stream_with_disconnect_check(
    http_request: Request,
    generator,
):
    """
    SSE 스트리밍 중 클라이언트 연결 끊김을 감지하여
    파이프라인을 조기 종료하는 래퍼 제너레이터입니다.
    """
    try:
        async for chunk in generator:
            # 클라이언트 연결 끊김 감지
            if await http_request.is_disconnected():
                logger.info("🛑 [Stream] 클라이언트 연결 끊김 감지 → 파이프라인 중단")
                break
            yield chunk
    except asyncio.CancelledError:
        logger.info("🛑 [Stream] 요청 취소 감지 → 파이프라인 정리 중")
        raise
    except Exception as e:
        logger.error(f"❌ [Stream] 스트리밍 중 오류: {e}", exc_info=True)
        data = {"type": "error", "content": f"스트리밍 오류: {str(e)}"}
        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
        data = {"type": "done"}
        yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
    finally:
        # generator 정리 (aclose 호출)
        if hasattr(generator, 'aclose'):
            try:
                await generator.aclose()
            except Exception:
                pass


@router.post("/stream")
async def chat_stream(request: ChatRequest, http_request: Request, current_user: dict = Depends(get_current_user)):
    """
    Agentic Search → Vision LLM 분석 후 SSE 스트리밍으로 응답합니다.
    
    document_id가 없으면 질문 내용 기반으로 자동 선택합니다.
    
    SSE 이벤트 타입:
    - reasoning: AI 에이전트의 목차 탐색·추론 과정
    - reference: 타겟 페이지 썸네일 이미지 (Base64 PNG)
    - answer: 최종 답변 텍스트 (마크다운) 청크
    - error: 에러 발생 시
    - done: 스트리밍 종료 신호
    """
    doc_id = str(request.document_id) if request.document_id else None
    
    # document_id가 지정된 경우 사전 검증 + 소유권 확인
    if doc_id:
        meta = await metadata_service.get_document_async(doc_id, owner_email=current_user["email"])
        if meta is None:
            raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
        if not await metadata_service.verify_document_owner_async(doc_id, current_user["email"]):
            raise HTTPException(status_code=403, detail="해당 문서에 대한 접근 권한이 없습니다.")
    
    # 대화 이력을 딕셔너리 리스트로 변환
    history = []
    if request.chat_history:
        history = [{"role": h.role, "content": h.content} for h in request.chat_history]
    
    # previous_reference를 딕셔너리로 변환
    prev_ref = None
    if request.previous_reference:
        prev_ref = {
            "document_id": str(request.previous_reference.document_id),
            "document_name": request.previous_reference.document_name,
            "manufacturer": request.previous_reference.manufacturer,
            "referenced_pages": request.previous_reference.referenced_pages,
        }

    pipeline = run_agentic_pipeline(
        doc_id, request.question, chat_history=history, image=request.image,
        user_email=current_user["email"],
        session_id=request.session_id,
        previous_reference=prev_ref,
    )

    
    return StreamingResponse(
        _stream_with_disconnect_check(http_request, pipeline),
        media_type="text/event-stream",
    )
