"""질문 분류 — LLM 호출 전 규칙 기반 선별."""
import re

# 기술 질의 신호: 알람/에러 코드, 장비 용어, 매뉴얼 관련 어휘
_TECHNICAL_PATTERNS = re.compile(
    r"(에러|알람|alarm|error|코드|code|파라미터|parameter|"
    r"서보|servo|모터|motor|PLC|plc|센서|sensor|드라이브|drive|"
    r"설정|세팅|배선|원점|조그|인버터|엔코더|토크|"
    r"매뉴얼|manual|사양|스펙|spec|트러블|trouble|"
    r"AL\.|Er\.|E\d|[A-Z]{2,}-[A-Z0-9])",
    re.IGNORECASE,
)

_GREETING_PATTERNS = re.compile(
    r"^(안녕|하이|hello|hi|hey|감사|고마워|수고|반갑|잘가|bye)[\s하세요습니다!?.]*$",
    re.IGNORECASE,
)

# 인사말로 단정할 수 있는 최대 길이. 이보다 길면 뒤에 실제 질문이 붙었을 가능성이 있다.
GREETING_MAX_LENGTH = 20


def quick_classify(question: str) -> str | None:
    """규칙 기반 빠른 분류.

    확실한 경우만 `"general"` / `"technical"` 을 반환하고,
    애매하면 `None` 을 반환해 LLM 판별에 맡깁니다.
    """
    q = question.strip()
    if len(q) < GREETING_MAX_LENGTH and _GREETING_PATTERNS.match(q):
        return "general"
    if _TECHNICAL_PATTERNS.search(q):
        return "technical"
    return None
