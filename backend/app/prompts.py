"""
LLM 프롬프트 모음.

agentic_graph.py 등에서 사용하는 프롬프트 템플릿을 한곳에 모아 둡니다.
각 함수는 f-string 변수 주입을 그대로 유지하여 동작 동일성을 보장합니다.
"""


def general_chat_prompt(question: str) -> str:
    """일상대화(general) 분기에서 사용하는 chat 프롬프트."""
    return f"""당신은 산업용 매뉴얼 분석 비서 'Vision RAG 에이전트'입니다.
사용자가 매뉴얼 검색과 관계없는 일반적인 인사나 일상적 대화를 건넸습니다.
친절하고 자연스럽게 인사하고, 매뉴얼 PDF를 업로드하여 질문하면 해당 매뉴얼(알람코드, 도면, 표 등)을 원본 레이아웃 그대로 분석하여 정확하게 답변할 수 있는 도구임을 알려주세요.

사용자 입력: "{question}"

친절하고 자연스럽게 한국어로 답변을 생성해 주세요.
"""


def refine_pages_prompt(question: str, full_text: str, section_start: int) -> str:
    """Phase 2: 섹션 텍스트 기반 정밀 페이지 탐색 프롬프트."""
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 전체 매뉴얼의 특정 섹션에 포함된 텍스트입니다.
이 텍스트를 꼼꼼히 읽고 검색하여, 아래 질문에 답하기 위해 참조해야 할 **정확한 절대 페이지 번호**를 찾으세요.

질문: "{question}"

--- 섹션 텍스트 시작 ---
{full_text}
--- 섹션 텍스트 끝 ---

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "reasoning": "텍스트를 검색/분석한 추론 과정을 한국어로 간략히 설명",
    "target_pages": [절대_페이지_번호1, 절대_페이지_번호2, ...],
    "section_title": "관련 내용이 포함된 가장 정확한 섹션 또는 표의 제목"
}}

⚠️ 중요 규칙:
- target_pages에는 본문 텍스트의 '--- PAGE X ---'에 표시된 페이지 번호(정수)를 사용하세요.
- 질문의 키워드(예: 에러 번호 2050, 알람 코드, 특정 부품명)가 정확히 일치하는 페이지를 찾으세요.
- 타겟 페이지는 최소 1개, 최대 3개로 설정합니다.
- 만약 제공된 텍스트 내에 관련 내용이 없다면, 원래 섹션 시작 페이지인 [{section_start}] 를 넣으세요.
"""


def select_document_prompt(docs_text: str, context_section: str, previous_reference_section: str, question: str) -> str:
    """Phase 1: 메타데이터 기반 문서 선택 + 일상대화 판별 프롬프트."""
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.

[Step 1] 사용자의 질문이 매뉴얼 검색이 필요한 기술적 질문인지 판별하세요.
- 인사말, 잡담, 감사 → "general"
- 매뉴얼에서 정보를 찾아야 하는 질문 → "technical"

[Step 2] "technical"인 경우, 아래 문서 목록에서 적합한 문서를 선택하세요.
각 문서에 confidence (0.0~1.0) 점수를 부여하세요.

[Step 3] 되묻기 판단: 아래 상황이면 needs_clarification을 true로 설정하세요.
- 질문에 구체적인 제조사명이나 장비 모델명이 없는 경우
- 여러 문서가 비슷한 수준으로 해당될 수 있는 경우
- 어떤 문서에서도 명확하게 해당 내용을 다루는지 확신하기 어려운 경우

[Step 4] needs_clarification이 true일 때, 사용자가 선택할 수 있는 보강 질문 3개를 생성하세요.
보강 질문은 질문을 구체화할 수 있도록 제조사, 모델, 장비 종류 등을 특정하는 질문이어야 합니다.

{docs_text}
{context_section}
{previous_reference_section}
사용자의 질문: "{question}"

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "classification": "general" 또는 "technical",
    "needs_clarification": true 또는 false,
    "candidates": [
        {{"document_id": "...", "confidence": 0.92, "reason": "제조사와 모델이 일치"}},
        {{"document_id": "...", "confidence": 0.35, "reason": "같은 제조사이나 다른 모델"}}
    ],
    "suggested_questions": [
        "어떤 제조사의 서보 드라이브인가요? (예: 미쓰비시, 야스카와)",
        "장비의 모델명을 알고 계신가요?",
        "알람이 표시된 화면을 사진으로 첨부해 주시겠어요?"
    ],
    "reasoning": "판별 및 추론 과정을 한국어로 간략히 설명"
}}

규칙:
- classification이 "general"이면 candidates와 suggested_questions는 빈 배열 []로 설정
- classification이 "technical"이면 모든 문서에 confidence 점수를 부여하여 candidates에 포함
- confidence는 0.0~1.0 범위로 설정 (높을수록 적합)
- candidates는 confidence 내림차순으로 정렬
- 질문에 제조사/모델 정보가 없고 적합한 문서가 불명확하면 반드시 needs_clarification을 true로
- needs_clarification이 true일 때만 suggested_questions를 생성 (3개), false이면 빈 배열 []
- suggested_questions는 사용자 문서 목록에 존재하는 제조사/모델을 구체적으로 언급하세요
- 만약 "이전에 참조한 문서" 정보가 제공되었고, 사용자의 질문이 짧거나 생략된 형태(예: "2050은?", "그럼 이건 어떻게 해?")로 이전 매뉴얼 맥락을 잇고 있다면, 이전 참조 문서의 confidence 점수를 가장 높게(예: 0.9 이상) 부여하세요.
- [장비 연관성 규칙] 알람코드나 에러코드가 포함된 질문일 경우, 산업 자동화 장비의 제어 계층을 반드시 고려하세요. 예를 들어 "서보 알람"이라고 해도 실제 알람은 서보앰프 자체가 아니라 상위 제어 장비(위치결정모듈, 모션컨트롤러, PLC 등)에서 발생시킨 코드일 수 있습니다. 마찬가지로 하위 장비(엔코더, 모터 등)의 문서도 관련될 수 있습니다. 이처럼 질문에 명시된 장비뿐 아니라, 해당 장비와 제어 관계에 있는 상위/하위 장비의 문서에도 적절한 confidence 점수(0.4 이상)를 부여하세요."""


def select_pages_prompt(toc_text: str, total_pages, previous_pages_section: str, question: str) -> str:
    """Phase 1-2: ToC 기반 타겟 페이지 선택 프롬프트."""
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 선택된 문서의 전체 목차(ToC)입니다:

{toc_text}

총 페이지 수: {total_pages}
{previous_pages_section}
사용자의 질문: "{question}"

이 목차를 분석하여 질문에 답하기 위해 참조해야 할 타겟 페이지를 추론하세요.

다음 JSON 형식으로만 응답하세요 (마크다운 코드블록 없이):
{{
    "target_pages": [시작페이지, ..., 끝페이지],
    "section_title": "관련 섹션의 제목",
    "toc_candidates": [
        {{"title": "질문과 연관성 높은 목차 제목 1", "page": 페이지번호}},
        {{"title": "질문과 연관성 높은 목차 제목 2", "page": 페이지번호}},
        {{"title": "질문과 연관성 높은 목차 제목 3", "page": 페이지번호}}
    ],
    "reasoning": "페이지 추론 과정을 한국어로 간략히 설명"
}}

규칙:
- 타겟 페이지는 최소 1개, 최대 5개로 제한합니다.
- 페이지 번호는 목차에 명시된 page 값을 기준으로 합니다.
- toc_candidates에는 질문 해결에 도움을 줄 수 있는 목차(ToC) 항목을 최대 3개까지 매칭하여 포함하세요.
- 연속된 페이지라면 사이 페이지도 포함합니다."""
