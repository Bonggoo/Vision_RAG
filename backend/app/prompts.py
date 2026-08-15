"""
LLM 프롬프트 모음.

app/services/agentic/ 파이프라인이 사용하는 프롬프트 템플릿을 한곳에 모아 둡니다.
각 함수는 f-string 변수 주입을 그대로 유지하여 동작 동일성을 보장합니다.
"""


# ─── 대화 이력 블록 ──────────────────────────────────────────────────────────
# 프롬프트에 실을 최근 메시지 수와 메시지당 최대 길이.
# 프론트엔드가 보내는 양(6개 메시지 × 300자)과 맞춰 둔다 — 더 크게 잡아도
# 받을 이력이 없고, 더 작게 잡으면 이미 받은 맥락을 스스로 버리게 된다.
RECENT_HISTORY_MESSAGES = 6
HISTORY_MESSAGE_CHARS = 300


def chat_context_section(
    chat_history: list[dict] | None,
    max_messages: int = RECENT_HISTORY_MESSAGES,
    max_chars: int = HISTORY_MESSAGE_CHARS,
) -> str:
    """최근 대화 이력을 프롬프트 블록으로 만듭니다 (없으면 빈 문자열).

    문서 선택·페이지 선택·Vision·텍스트폴백이 모두 이 함수를 쓴다.
    이전에는 같은 절단 규칙이 두 벌로 복붙돼 턴 수·글자 수가 서로 달랐다.
    """
    if not chat_history:
        return ""
    lines = [
        f"{'사용자' if item['role'] == 'user' else 'AI'}: {item['content'][:max_chars]}"
        for item in chat_history[-max_messages:]
    ]
    return "\n이전 대화 맥락:\n" + "\n".join(lines) + "\n"


def general_chat_prompt(question: str) -> str:
    """일상대화(general) 분기에서 사용하는 chat 프롬프트."""
    return f"""당신은 산업용 매뉴얼 분석 비서 'Vision RAG 에이전트'입니다.
사용자가 매뉴얼 검색과 관계없는 일반적인 인사나 일상적 대화를 건넸습니다.
친절하고 자연스럽게 인사하고, 매뉴얼 PDF를 업로드하여 질문하면 해당 매뉴얼(알람코드, 도면, 표 등)을 원본 레이아웃 그대로 분석하여 정확하게 답변할 수 있는 도구임을 알려주세요.

사용자 입력: "{question}"

친절하고 자연스럽게 한국어로 답변을 생성해 주세요.
"""


def refine_pages_prompt(question: str, full_text: str, section_start: int) -> str:
    """Phase 2: 섹션 텍스트 기반 정밀 페이지 탐색 프롬프트.

    ⚠️ 변수 순서 주의: 섹션 본문(최대 50페이지, 실측 약 39,000토큰)이 질문보다
    먼저 와야 합니다. 파이프라인에서 가장 큰 입력이라 같은 섹션에 후속 질문이
    이어질 때 캐시 효과가 가장 큽니다. 질문을 앞에 두면 프리픽스가 매 턴 달라져
    본문 전체가 캐시 대상에서 빠집니다.
    """
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 전체 매뉴얼의 특정 섹션에 포함된 텍스트입니다.
이 텍스트를 꼼꼼히 읽고 검색하여, 텍스트 뒤에 제시되는 질문에 답하기 위해 참조해야 할 **정확한 절대 페이지 번호**를 찾으세요.

--- 섹션 텍스트 시작 ---
{full_text}
--- 섹션 텍스트 끝 ---

질문: "{question}"

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


def select_document_prompt(
    docs_text: str,
    toc_evidence_section: str,
    context_section: str,
    previous_reference_section: str,
    question: str,
) -> str:
    """Phase 1: 메타데이터 기반 문서 선택 + 일상대화 판별 프롬프트.

    ⚠️ 변수 순서 주의: 질문과 무관하게 고정된 문서 목록(docs_text)이 먼저 오고,
    질문마다 달라지는 요소(ToC 증거·대화 맥락·이전 참조·질문)가 뒤따릅니다.
    ToC 증거를 문서 목록 안에 섞으면 목록 전체가 매 질문 달라져 캐시가 깨집니다.
    """
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

[Step 4] needs_clarification이 true일 때, 사용자가 탭 한 번으로 그대로 전송할 수 있는 "구체화된 질문" 3개를 생성하세요.
- 반드시 사용자 입장에서 작성된 질문이어야 합니다. AI가 사용자에게 묻는 문장은 금지입니다 (예: "제조사가 어디인가요?", "모델명을 알려주실 수 있나요?" ❌)
- 사용자의 원래 질문 의도와 표현을 유지한 채, 후보 문서의 제조사/모델명을 덧붙여 재작성하세요 (예: 원 질문이 "통신 에러 타임아웃 해결법"이면 → "미쓰비시 MELSEC-Q 통신 에러 타임아웃 해결법" ✅)
- 각 질문은 서로 다른 후보 문서를 향하도록 작성하세요
- 질문에 이미 들어있는 제조사/모델명을 중복해서 붙이지 마세요. 후보들이 같은 제조사/모델이라 그것만으로 구분이 안 되면, 문서 제목의 구분 요소(예: 기본편/응용편, 시리얼/Ethernet)를 활용해 재작성하세요 (예: "Q 시리즈 Ethernet 모듈 통신 에러" → "Q 시리즈 Ethernet 모듈 기본편 기준 통신 에러 타임아웃 해결법")
- ⚠️ 예외: 사용자의 질문이 아래 문서 목록에 **없는** 제조사·장비 이름을 가리키는 것으로 보이면(예: 목록에 없는 브랜드의 매뉴얼을 찾는 질문), suggested_questions를 빈 배열 []로 두세요. 없는 이름 앞에 다른 제조사를 덧붙이면 실존하지 않는 매뉴얼이 있는 것처럼 보입니다 (예: "○○ 매뉴얼" → "미쓰비시 MELSEC-Q 시리즈 ○○ 매뉴얼" ❌). 이때 candidates의 confidence도 실제 관련도대로 낮게 부여하세요.

{docs_text}
{toc_evidence_section}{context_section}
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
        "<후보1의 제조사/모델> + 위 '사용자의 질문'을 그대로 살린 재작성 질문",
        "<후보2의 제조사/모델> + 위 '사용자의 질문'을 그대로 살린 재작성 질문",
        "<후보3의 제조사/모델> + 위 '사용자의 질문'을 그대로 살린 재작성 질문"
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
- suggested_questions는 사용자 문서 목록에 실제로 존재하는 제조사/모델을 구체적으로 언급한, "사용자가 그대로 전송할 수 있는" 재작성 질문이어야 합니다 (Step 4 참고)
- ⚠️ suggested_questions의 주제는 반드시 위 "사용자의 질문"에서 가져오세요. 위 JSON 예시나 Step 4 예시에 등장하는 주제(통신 에러, 타임아웃 등)를 그대로 베끼지 마세요. 사용자가 묻지 않은 주제를 제안하면 오답입니다. 예: 사용자의 질문이 "서보 2051 알람 설명"이면 → "<제조사/모델> 서보 2051 알람 설명" 형태여야 합니다
- suggested_questions의 각 항목은 사용자의 질문에 있던 핵심어(에러/알람 번호, 증상, 부품명)를 반드시 그대로 포함해야 합니다
- 질문이 문서 목록에 없는 제조사·장비를 가리키면 suggested_questions는 빈 배열 []로 두세요 (Step 4의 예외 참고). 억지로 3개를 채우지 마세요
- 만약 "이전에 참조한 문서" 정보가 제공되었고, 사용자의 질문이 짧거나 생략된 형태(예: "2050은?", "그럼 이건 어떻게 해?")로 이전 매뉴얼 맥락을 잇고 있다면, 이전 참조 문서의 confidence 점수를 가장 높게(예: 0.9 이상) 부여하세요.
- [장비 연관성 규칙] 알람코드나 에러코드가 포함된 질문일 경우, 산업 자동화 장비의 제어 계층을 반드시 고려하세요. 예를 들어 "서보 알람"이라고 해도 실제 알람은 서보앰프 자체가 아니라 상위 제어 장비(위치결정모듈, 모션컨트롤러, PLC 등)에서 발생시킨 코드일 수 있습니다. 마찬가지로 하위 장비(엔코더, 모터 등)의 문서도 관련될 수 있습니다. 이처럼 질문에 명시된 장비뿐 아니라, 해당 장비와 제어 관계에 있는 상위/하위 장비의 문서에도 적절한 confidence 점수(0.4 이상)를 부여하세요."""


def select_pages_prompt(
    toc_text: str,
    total_pages,
    previous_pages_section: str,
    question: str,
) -> str:
    """Phase 1-2: ToC 기반 타겟 페이지 선택 프롬프트.

    ⚠️ 변수 순서 주의: 큰 ToC(수만 토큰)가 반드시 맨 앞에 와야 합니다.
    같은 문서에 연속 질문할 때 Gemini 암묵적 캐시가 ToC 구간에 걸려
    입력 토큰의 대부분이 할인됩니다(실측 89%). 가변 요소(맥락·질문)를
    ToC 앞으로 옮기면 프리픽스가 매 턴 달라져 캐시가 통째로 깨집니다.
    """
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


def vision_source_section(document_name: str, breadcrumb: str, pages: list[int]) -> str:
    """Vision 프롬프트에 넣을 '이 페이지가 어디서 왔는지' 블록을 만듭니다.

    문서명·ToC 계층·원문 페이지 번호를 모델에 알려 주어, 답변이 출처를 정확히
    밝히고 첨부 페이지 밖의 내용을 지어내지 않게 하는 것이 목적입니다.
    재료가 하나도 없으면 빈 문자열을 반환해 프롬프트에서 통째로 빠집니다.
    """
    parts = [part for part in (document_name.strip(), breadcrumb.strip()) if part]
    location = " > ".join(parts)
    page_text = ", ".join(f"p.{p}" for p in pages)

    if not location and not page_text:
        return ""

    lines = ["\n[첨부 페이지 출처]"]
    if location:
        lines.append(f"- 위치: {location}")
    if page_text:
        lines.append(f"- 원문 페이지: {page_text}")
    return "\n".join(lines) + "\n"


def vision_answer_prompt(source_section: str, context_section: str, question: str) -> str:
    """Phase 3: 미니 PDF 를 첨부해 최종 답변을 생성하는 Vision 프롬프트."""
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.
첨부된 PDF 페이지를 분석하여 아래 질문에 정확하게 답변하세요.
{source_section}{context_section}
질문: "{question}"

답변 형식 (마크다운):
## 답변 요약
(핵심 답변을 1-2문장으로)

### 상세 내용
(매뉴얼 내용을 기반으로 상세하게)

### 조치 방법 (해당 시)
1. 단계별 조치 방법
2. ...

> 참고: 해당 정보는 매뉴얼의 첨부 페이지에서 확인된 내용입니다.

규칙:
- 시각적 정보(표, 도면, 다이어그램)가 있다면 해당 내용을 텍스트로 설명해 주세요.
- 매뉴얼에 없는 내용은 추측하지 마세요.
- [첨부 페이지 출처]가 주어졌다면, 근거를 인용할 때 해당 원문 페이지 번호를 함께 밝히세요.
- 한국어로 답변하세요.
"""


def vision_history_section(chat_history: list[dict] | None) -> str:
    """Vision 프롬프트의 이전 대화 맥락 블록. 이력이 없으면 빈 문자열.

    절단 규칙은 chat_context_section 과 공유하고, 후속 질문 처리 지시만 덧붙입니다.
    """
    context = chat_context_section(chat_history)
    if not context:
        return ""
    return context + "위 대화를 참고하여, 사용자의 후속 질문에 자연스럽게 답변하세요.\n"


def text_fallback_prompt(context_section: str, question: str, full_text: str) -> str:
    """Vision 분석 실패 시 텍스트만으로 답변을 생성하는 폴백 프롬프트.

    ⚠️ 변수 순서 주의: 본문이 가변 요소(대화 맥락·질문)보다 먼저 와야
    같은 페이지에 재질문할 때 캐시 프리픽스가 유지됩니다.
    """
    return f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 매뉴얼에서 추출한 텍스트입니다. 이 텍스트를 분석하여 텍스트 뒤에 제시되는 사용자의 질문에 정확하게 답변하세요.

--- 매뉴얼 텍스트 시작 ---
{full_text}
--- 매뉴얼 텍스트 끝 ---
{context_section}
질문: "{question}"

답변 형식 (마크다운):
## 답변 요약
(핵심 답변을 1-2문장으로)

### 상세 내용
(매뉴얼 내용을 기반으로 상세하게)

### 조치 방법 (해당 시)
1. 단계별 조치 방법
2. ...

> ⚠️ 참고: 이 답변은 텍스트 기반 분석입니다. 표/도면 등 시각적 정보는 포함되지 않았습니다.

규칙:
- 매뉴얼에 없는 내용은 추측하지 마세요.
- 한국어로 답변하세요.
"""
