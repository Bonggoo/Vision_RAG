"""
질의·응답 스트리밍 라우터.

사용자 질문을 받아 Agentic Search 파이프라인을 실행하고
SSE(Server-Sent Events)로 결과를 스트리밍합니다.
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas.request import ChatRequest
from app.services.agentic_graph import run_agentic_pipeline
from app.services import metadata_service

router = APIRouter()


@router.post("/stream")
async def chat_stream(request: ChatRequest):
    """
    Agentic Search → Vision LLM 분석 후 SSE 스트리밍으로 응답합니다.
    
    SSE 이벤트 타입:
    - reasoning: AI 에이전트의 목차 탐색·추론 과정
    - reference: 타겟 페이지 썸네일 이미지 (Base64 PNG)
    - answer: 최종 답변 텍스트 (마크다운) 청크
    - error: 에러 발생 시
    - done: 스트리밍 종료 신호
    """
    doc_id = str(request.document_id)
    
    # 문서 존재 여부 사전 검증
    meta = metadata_service.get_document(doc_id)
    if meta is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 문서입니다.")
    
    return StreamingResponse(
        run_agentic_pipeline(doc_id, request.question),
        media_type="text/event-stream",
    )

