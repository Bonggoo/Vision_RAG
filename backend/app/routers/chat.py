from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
import asyncio
from app.schemas.request import ChatRequest
import json

router = APIRouter()

async def mock_agentic_search_stream(request: ChatRequest):
    """
    Agentic Search 및 Gemini Vision 응답을 Mocking하여 SSE 스트리밍으로 보냅니다.
    """
    yield "data: " + json.dumps({"type": "info", "message": f"'{request.document_id}' 문서를 분석 중입니다..."}) + "\n\n"
    await asyncio.sleep(1)
    
    yield "data: " + json.dumps({"type": "info", "message": "관련된 타겟 페이지(p.4, p.12)를 찾았습니다. 미니 PDF를 추출하여 Vision 분석을 시작합니다."}) + "\n\n"
    await asyncio.sleep(1.5)
    
    response_text = f"질문하신 '{request.message}'에 대한 답변입니다.\n\n해당 알람은 서보 앰프와의 통신 이상으로 발생합니다. 매뉴얼 12페이지의 '시스템 구성' 및 20페이지의 '배선 및 설치' 부분을 확인하여 케이블 연결 상태를 점검해 주세요."
    
    # 타이핑 이펙트를 위해 한 글자씩 스트리밍
    for i in range(len(response_text)):
        chunk = response_text[i]
        yield "data: " + json.dumps({"type": "chunk", "text": chunk}) + "\n\n"
        await asyncio.sleep(0.02)
        
    yield "data: " + json.dumps({"type": "done", "message": "Stream completed."}) + "\n\n"

@router.post("/stream")
async def chat_stream(request: ChatRequest):
    if not request.document_id or not request.message:
        raise HTTPException(status_code=400, detail="document_id and message are required.")
        
    return StreamingResponse(
        mock_agentic_search_stream(request),
        media_type="text/event-stream"
    )
