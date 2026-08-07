"""SSE(Server-Sent Events) 직렬화."""
import json


def sse_event(event_type: str, **kwargs) -> str:
    """SSE 이벤트 한 건을 `data: {...}\\n\\n` 형식 문자열로 만듭니다."""
    data = {"type": event_type, **kwargs}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"
