"""
Agentic Search 파이프라인.

3단계 하이브리드 추론(텍스트 + PDF)을 활용하여 정확한 페이지를 탐색합니다.
Phase 0+1: 문서 선택 + ToC 기반 섹션 특정 (Flash-Lite)
Phase 2: 섹션 전체 텍스트 추출 → 정확한 타겟 페이지 특정 (Flash-Lite)
Phase 3: 타겟 페이지 미니 PDF 분석 → 답변 스트리밍 (Flash-Lite)
"""
import base64
import json
import re
import fitz  # PyMuPDF
from typing import AsyncGenerator
from app.services.metadata_service import get_document, get_document_path, get_all_documents, verify_document_owner
from app.services.agent_service import analyze_pages_with_vision, _create_flash_llm, _clean_json_response, _extract_text_content
from app.services.pdf_service import extract_pages_as_pdf, render_page_thumbnail
from app.utils.logger import logger
from langchain_core.messages import HumanMessage


# ─── C-1: 규칙 기반 빠른 분류 (LLM 호출 생략) ───
_TECHNICAL_PATTERNS = re.compile(
    r"(에러|알람|alarm|error|코드|code|파라미터|parameter|"
    r"서보|servo|모터|motor|PLC|plc|센서|sensor|드라이브|drive|"
    r"설정|세팅|배선|원점|조그|인버터|엔코더|토크|"
    r"매뉴얼|manual|사양|스펙|spec|트러블|trouble|"
    r"AL\.|Er\.|E\d|[A-Z]{2,}-[A-Z0-9])",
    re.IGNORECASE
)

_GREETING_PATTERNS = re.compile(
    r"^(안녕|하이|hello|hi|hey|감사|고마워|수고|반갑|잘가|bye)[\s하세요습니다!?.]*$",
    re.IGNORECASE
)


def _quick_classify(question: str) -> str | None:
    """규칙 기반 빠른 분류. 확실한 경우만 반환, 애매하면 None (→ LLM 판별)."""
    q = question.strip()
    if len(q) < 20 and _GREETING_PATTERNS.match(q):
        return "general"
    if _TECHNICAL_PATTERNS.search(q):
        return "technical"
    return None


def _generate_default_clarification_questions(question: str, documents: list[dict]) -> list[str]:
    """
    LLM이 보강 질문을 생성하지 못했을 때 기본 보강 질문을 생성합니다.
    사용자의 문서 목록에서 제조사/모델을 추출하여 구체적인 선택지를 만듭니다.
    """
    # 문서에서 고유한 제조사/모델 수집
    manufacturers = set()
    models = set()
    for d in documents:
        m = str(d.get("manufacturer", "")).strip()
        s = str(d.get("model_series", "")).strip()
        if m and m != "미상":
            manufacturers.add(m)
        if s and s != "미상":
            models.add(s)
    
    questions = []
    
    if manufacturers:
        manuf_list = ", ".join(list(manufacturers)[:5])
        questions.append(f"어떤 제조사의 장비인가요? (보유 매뉴얼: {manuf_list})")
    
    if models:
        model_list = ", ".join(list(models)[:5])
        questions.append(f"장비의 모델명을 알고 계신가요? (보유 매뉴얼: {model_list})")
    
    questions.append("알람이 표시된 장비 화면을 사진으로 찍어 첨부해 주시겠어요?")
    
    return questions[:3]


def _sse_event(event_type: str, **kwargs) -> str:
    """SSE 이벤트 문자열을 생성합니다."""
    data = {"type": event_type, **kwargs}
    return f"data: {json.dumps(data, ensure_ascii=False)}\n\n"


def _normalize_page(page_value) -> int:
    """
    ToC의 페이지 값을 정수로 정규화합니다.
    
    지원 형식:
    - int: 그대로 반환
    - "1-1" (챕터-페이지): 숫자만 추출 후 조합 (fallback: 마지막 숫자)
    - "32": 문자열 정수
    - 기타: 1 반환
    """
    if isinstance(page_value, int):
        return page_value
    if isinstance(page_value, float):
        return int(page_value)
    if isinstance(page_value, str):
        page_value = page_value.strip()
        # 순수 숫자
        if page_value.isdigit():
            return int(page_value)
        # "3-32" 형식: 하이픈 뒤 숫자 사용 (섹션 내 상대 페이지)
        import re
        match = re.match(r"(\d+)[^\d]+(\d+)", page_value)
        if match:
            return int(match.group(2))
    return 1


def _find_section_page_range(toc: list[dict], target_pages: list[int], total_pages: int) -> tuple[int, int]:
    """
    Phase 2 텍스트 검색 범위를 결정합니다.
    
    - start: target_pages 이전의 가장 가까운 ToC 항목 (섹션 시작점)
    - end: start + 49 (최대 50페이지 범위로 텍스트 탐색 오버헤드 최소화)
    
    ToC 하위 항목 경계에서 끊지 않습니다.
    """
    if not target_pages:
        return 1, min(50, total_pages)
        
    pages = sorted(set(_normalize_page(entry.get("page", 1)) for entry in toc))
    min_target = min(target_pages)
    
    # 섹션 시작: min_target 이하에서 가장 가까운 ToC 항목
    start = min_target
    for p in reversed(pages):
        if p <= min_target:
            start = p
            break
    
    # 섹션 끝: start로부터 최대 50페이지 (텍스트 탐색 오버헤드 차단)
    end = min(start + 49, total_pages)
    return start, end


async def _refine_pages_with_text(
    doc: fitz.Document,
    section_start: int,
    section_end: int,
    question: str,
) -> dict:
    """
    Phase 2: 섹션 내의 전체 텍스트를 추출하여 경량 LLM(Flash-Lite)에게 분석시키고,
    질문에 답변하기 위한 정확한 타겟 페이지를 추론합니다. (C-3: 비동기화)
    """
    llm = _create_flash_llm()
    logger.info(f"🔍 [Phase 2] 정밀 텍스트 탐색 시작: p.{section_start}~{section_end}")
    
    # 전달받은 section_start ~ section_end 전체 텍스트 추출 (최대 200페이지)

    scan_end = min(section_end, section_start + 199, doc.page_count)
    
    text_content = []
    for page_idx in range(section_start - 1, scan_end):
        text = doc[page_idx].get_text()
        text_content.append(f"--- PAGE {page_idx + 1} ---\n{text}\n")
    
    full_text = "\n".join(text_content)
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
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
    
    message = HumanMessage(content=prompt)
    
    try:
        # C-3: 비동기 호출로 이벤트 루프 블로킹 방지
        response = await llm.ainvoke([message])
        content = _clean_json_response(response.content)
        result = json.loads(content)
        
        # 페이지 정규화
        raw_pages = result.get("target_pages", [section_start])
        normalized = [_normalize_page(p) for p in raw_pages]
        
        # 범위 검증
        normalized = [p for p in normalized if section_start <= p <= scan_end]
        if not normalized:
            normalized = [section_start]
        
        result["target_pages"] = normalized[:3]
        return result
    except Exception as e:
        logger.error(f"❌ [Phase 2] Text Refine Error: {e}", exc_info=True)
        return {
            "reasoning": f"세부 텍스트 분석 실패, 섹션 시작 페이지로 폴백: {str(e)}",
            "target_pages": [section_start],
            "section_title": "알 수 없음"
        }



async def _select_document(
    question: str,
    documents: list[dict],
    chat_history: list[dict] | None = None,
    previous_reference: dict | None = None,
) -> dict:
    """
    1단계: 메타데이터만으로 문서 선택 + 일상대화 판별.
    ToC를 제외하여 토큰을 절약합니다 (~2,500 토큰).
    
    Returns:
        {
            "classification": "general" | "technical",
            "candidates": [
                {"document_id": "...", "confidence": 0.92, "reason": "..."},
                ...
            ],
            "reasoning": "..."
        }
    """
    logger.info(f"🔍 [Phase 1] 메타데이터 기반 문서 선택 시작 (질문: {question[:50]}...)")
    
    # 문서가 1개면 LLM 호출 없이 바로 반환
    if len(documents) == 1:
        return {
            "classification": "technical",
            "candidates": [
                {
                    "document_id": documents[0]["document_id"],
                    "confidence": 0.99,
                    "reason": "유일한 문서",
                }
            ],
            "reasoning": "문서가 1개이므로 해당 문서를 자동 선택합니다.",
        }
    
    llm = _create_flash_llm()
    
    # 각 문서의 메타데이터 요약 (ToC 제외하여 토큰 절약)
    doc_summaries = []
    for i, doc in enumerate(documents):
        doc_summaries.append(
            f"[문서 {i+1}]\n"
            f"  ID: {doc['document_id']}\n"
            f"  제목: {doc.get('filename', '알 수 없음')}\n"
            f"  제조사: {doc.get('manufacturer', '미상')}\n"
            f"  모델 시리즈: {doc.get('model_series', '미상')}\n"
            f"  문서 종류: {doc.get('document_type', '미상')}\n"
            f"  페이지 수: {doc.get('total_pages', 0)}"
        )
    
    docs_text = "\n\n".join(doc_summaries)
    
    # 대화 이력 맥락 구성
    context_section = ""
    if chat_history:
        recent = chat_history[-4:]
        pairs = []
        for item in recent:
            role_label = "사용자" if item["role"] == "user" else "AI"
            pairs.append(f"{role_label}: {item['content'][:200]}")
        context_section = "\n이전 대화 맥락:\n" + "\n".join(pairs) + "\n"
    
    # 이전 참조 문서 힌트
    previous_reference_section = ""
    if previous_reference:
        prev_name = previous_reference.get("document_name", "")
        prev_manuf = previous_reference.get("manufacturer", "")
        if prev_name:
            previous_reference_section = f"\n이전에 참조한 문서: {prev_name} (제조사: {prev_manuf})\n"
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.

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
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = json.loads(_clean_json_response(response.content))
        
        # classification 정규화
        classification = result.get("classification", "technical").lower().strip()
        result["classification"] = "general" if "general" in classification else "technical"
        
        if result["classification"] == "technical":
            # candidates 검증: 유효한 document_id만 남기기
            valid_ids = {d["document_id"] for d in documents}
            raw_candidates = result.get("candidates", [])
            validated = []
            for c in raw_candidates:
                if isinstance(c, dict) and c.get("document_id") in valid_ids:
                    validated.append({
                        "document_id": c["document_id"],
                        "confidence": float(c.get("confidence", 0.5)),
                        "reason": str(c.get("reason", "")),
                    })
            
            # 후보가 없으면 첫 번째 문서를 기본값으로
            if not validated:
                validated = [{"document_id": documents[0]["document_id"], "confidence": 0.5, "reason": "기본 선택"}]
            
            # confidence 내림차순 정렬
            validated.sort(key=lambda x: x["confidence"], reverse=True)
            result["candidates"] = validated
            
            # needs_clarification 및 suggested_questions 정규화
            result["needs_clarification"] = bool(result.get("needs_clarification", False))
            raw_questions = result.get("suggested_questions", [])
            if isinstance(raw_questions, list):
                result["suggested_questions"] = [str(q) for q in raw_questions[:5]]
            else:
                result["suggested_questions"] = []
        else:
            result["candidates"] = []
            result["needs_clarification"] = False
            result["suggested_questions"] = []
        
        logger.info(f"📊 [Phase 1] 문서 선택 결과: classification={result['classification']}, "
                    f"needs_clarification={result.get('needs_clarification')}, "
                    f"top_confidence={result['candidates'][0]['confidence'] if result['candidates'] else 'N/A'}, "
                    f"suggested_questions={len(result.get('suggested_questions', []))}개")
        
        return result
    except Exception as e:
        logger.error(f"❌ [Phase 1] Document Selection Error: {e}", exc_info=True)
        return {
            "classification": "technical",
            "candidates": [{"document_id": documents[0]["document_id"], "confidence": 0.5, "reason": f"오류 발생 기본 선택: {str(e)}"}],
            "reasoning": f"문서 선택 중 오류 발생: {str(e)}",
            "needs_clarification": False,
            "suggested_questions": [],
        }


async def _select_pages(
    question: str,
    toc: list[dict],
    total_pages: int,
    previous_reference: dict | None = None,
) -> dict:
    """
    2단계: 선택된 문서의 ToC 전체로 페이지 선택.
    ToC 잘림 없이 전체를 전달합니다.
    
    Returns:
        {
            "target_pages": [페이지 번호들],
            "section_title": "관련 섹션 제목",
            "toc_candidates": [{"title": "...", "page": N}, ...],
            "reasoning": "..."
        }
    """
    llm = _create_flash_llm()
    logger.info(f"🔍 [Phase 1-2] ToC 기반 페이지 선택 시작 (질문: {question[:50]}...)")
    
    # ToC 전체 전달 (잘림 없음)
    toc_text = json.dumps(toc, ensure_ascii=False)
    
    # 이전 참조 페이지 힌트
    previous_pages_section = ""
    if previous_reference:
        ref_pages = previous_reference.get("referenced_pages", [])
        if ref_pages:
            previous_pages_section = f"\n이전에 참조한 페이지: {ref_pages} (같은 맥락의 후속 질문일 수 있습니다)\n"
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
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
    
    try:
        response = await llm.ainvoke([HumanMessage(content=prompt)])
        result = json.loads(_clean_json_response(response.content))
        
        # target_pages 정규화
        raw_pages = result.get("target_pages", [1])
        result["target_pages"] = [_normalize_page(p) for p in raw_pages][:5]
        
        # toc_candidates 정규화
        raw_candidates = result.get("toc_candidates", [])
        normalized_candidates = []
        for cand in raw_candidates:
            if isinstance(cand, dict) and "title" in cand:
                normalized_candidates.append({
                    "title": str(cand["title"]),
                    "page": _normalize_page(cand.get("page", 1))
                })
        result["toc_candidates"] = normalized_candidates[:3]
        
        return result
    except Exception as e:
        logger.error(f"❌ [Phase 1-2] Page Selection Error: {e}", exc_info=True)
        return {
            "target_pages": [1],
            "section_title": "알 수 없음",
            "toc_candidates": [],
            "reasoning": f"페이지 추론 중 오류 발생: {str(e)}"
        }


async def run_agentic_pipeline(
    document_id: str | None,
    question: str,
    chat_history: list[dict] | None = None,
    image: str | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    previous_reference: dict | None = None,
) -> AsyncGenerator[str, None]:
    """
    Agentic Search 파이프라인을 실행합니다.
    
    3단계 하이브리드 구조:
    Phase 1: 메타데이터 기반 문서 선택 (Flash-Lite, ToC 제외)
    Phase 1-2: ToC 전체 기반 타겟 페이지 추론 (Flash-Lite, 텍스트)
    Phase 2: 섹션 전체 텍스트 분석 → 정확한 타겟 페이지 특정 (Flash-Lite, 텍스트)
    Phase 3: 타겟 페이지 미니 PDF 분석 → 답변 스트리밍 (Flash-Lite, PDF)
    """
    logger.info(f"🚀 [Pipeline] Agentic Search 파이프라인 작동 시작 (질문: '{question}')")
    

    
    # SSE 이벤트 수집 변수 (GCS 저장용)
    collected_answer = ""
    collected_reasoning = []
    collected_references = []
    selected_doc_filename = ""
    
    # 대화 저장 헬퍼 (모든 종료 경로에서 호출)
    def _save_conversation():
        """수집된 메시지를 GCS에 저장합니다."""
        if not (session_id and user_email and (collected_answer or collected_reasoning)):
            return
        try:
            from app.services.conversation_service import save_message
            user_msg = {
                "role": "user",
                "content": question,
                "image": image,
            }
            assistant_msg = {
                "role": "assistant",
                "content": collected_answer,
                "reasoning_steps": collected_reasoning,
                "reference_pages": [ref["page_number"] for ref in collected_references],
                "reference_document_id": str(document_id) if document_id else None,
                "reference_document_name": selected_doc_filename if document_id else None,

            }
            title_text = question[:25] + "..." if len(question) > 25 else question
            save_message(user_email, session_id, user_msg, assistant_msg, title=title_text)
        except Exception as e:
            logger.error(f"❌ [Pipeline] 대화 저장 실패 (무시): {e}")
    
    try:
        # ─── Step -1: 이미지 분석 및 질문/문서 매칭 보강 ───
        analyzed_meta = None
        if image:
            yield _sse_event("reasoning", content="📸 업로드하신 장비 이미지를 분석하고 있습니다...")
            collected_reasoning.append("📸 업로드하신 장비 이미지를 분석하고 있습니다...")
            try:
                from app.services.agent_service import analyze_device_image_with_gemini
                analyzed_meta = await analyze_device_image_with_gemini(image)
                
                if analyzed_meta and analyzed_meta.get("confidence", 0.0) >= 0.5:
                    manuf = analyzed_meta.get("manufacturer")
                    model = analyzed_meta.get("model_series")
                    err_code = analyzed_meta.get("error_code")
                    symptom = analyzed_meta.get("symptom")
                    
                    info_parts = []
                    if manuf: info_parts.append(f"제조사: {manuf}")
                    if model: info_parts.append(f"모델: {model}")
                    if err_code: info_parts.append(f"인식된 알람: {err_code}")
                    if symptom: info_parts.append(f"증상: {symptom}")
                    
                    reasoning_content = "🔍 이미지 인식 성공!\n- " + "\n- ".join(info_parts)
                    yield _sse_event("reasoning", content=reasoning_content)
                    collected_reasoning.append(reasoning_content)
                    
                    # 문서 매칭: document_id가 지정되지 않은 경우, 분석된 제조사/모델과 일치하는 문서 검색
                    if document_id is None:
                        all_docs = get_all_documents(owner_email=user_email)
                        matched_doc = None
                        
                        # 1순위: 제조사와 모델 모두 매칭되는 문서
                        if manuf and model:
                            for d in all_docs:
                                d_manuf = str(d.get("manufacturer", "")).upper()
                                d_model = str(d.get("model_series", "")).upper()
                                if manuf.upper() in d_manuf and model.upper() in d_model:
                                    matched_doc = d
                                    break
                                    
                        # 2순위: 모델명 매칭
                        if not matched_doc and model:
                            for d in all_docs:
                                d_model = str(d.get("model_series", "")).upper()
                                if model.upper() in d_model:
                                    matched_doc = d
                                    break
                                    
                        # 3순위: 제조사명 매칭
                        if not matched_doc and manuf:
                            for d in all_docs:
                                d_manuf = str(d.get("manufacturer", "")).upper()
                                if manuf.upper() in d_manuf:
                                    matched_doc = d
                                    break
                                    
                        if matched_doc:
                            document_id = matched_doc["document_id"]
                            reasoning_content = f"📂 분석 정보를 기반으로 매칭된 매뉴얼을 자동으로 선택했습니다:\n- 파일명: {matched_doc.get('filename')}"
                            yield _sse_event("reasoning", content=reasoning_content)
                            collected_reasoning.append(reasoning_content)
                    
                    # 질문 보강 (리라이팅)
                    rewritten_parts = []
                    if manuf: rewritten_parts.append(manuf)
                    if model: rewritten_parts.append(model)
                    if err_code: rewritten_parts.append(f"알람코드 {err_code}")
                    if symptom: rewritten_parts.append(symptom)
                    
                    if rewritten_parts:
                        # 사용자 질문이 비어있거나 너무 짧으면 알람 분석 질문으로 대체
                        if len(question.strip()) < 5:
                            question = f"{' '.join(rewritten_parts)} 원인과 조치 대처법"
                        else:
                            question = f"{' '.join(rewritten_parts)} 에러 상황: {question}"
                        
                        reasoning_content = f"⚙️ 질문 보강 완료: '{question}'"
                        yield _sse_event("reasoning", content=reasoning_content)
                        collected_reasoning.append(reasoning_content)
                else:
                    yield _sse_event("reasoning", content="⚠️ 이미지에서 명확한 장비 브랜드나 알람코드를 파악하지 못해 일반 RAG 모드로 계속합니다.")
                    collected_reasoning.append("⚠️ 이미지에서 명확한 장비 브랜드나 알람코드를 파악하지 못해 일반 RAG 모드로 계속합니다.")
            except Exception as e:
                logger.error(f"Error in image preprocessing: {e}")
                yield _sse_event("reasoning", content=f"⚠️ 이미지 분석 중 오류 발생, 일반 RAG 모드로 진행합니다. (오류: {e})")
                collected_reasoning.append(f"⚠️ 이미지 분석 중 오류 발생, 일반 RAG 모드로 진행합니다. (오류: {e})")

        # ─── C-1: 규칙 기반 빠른 분류 ───
        quick_result = _quick_classify(question)
        
        if quick_result == "general":
            # 명확한 인사말 → LLM 호출 없이 즉시 Early Exit
            reasoning_msg = "일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다..."
            yield _sse_event("reasoning", content=reasoning_msg)
            collected_reasoning.append(reasoning_msg)
            
            llm = _create_flash_llm()
            chat_prompt = f"""당신은 산업용 매뉴얼 분석 비서 'Vision RAG 에이전트'입니다.
사용자가 매뉴얼 검색과 관계없는 일반적인 인사나 일상적 대화를 건넸습니다.
친절하고 자연스럽게 인사하고, 매뉴얼 PDF를 업로드하여 질문하면 해당 매뉴얼(알람코드, 도면, 표 등)을 원본 레이아웃 그대로 분석하여 정확하게 답변할 수 있는 도구임을 알려주세요.

사용자 입력: "{question}"

친절하고 자연스럽게 한국어로 답변을 생성해 주세요.
"""
            try:
                response = await llm.ainvoke([HumanMessage(content=chat_prompt)])
                answer = _extract_text_content(response.content)
                yield _sse_event("answer", content=answer)
                collected_answer = answer
            except Exception as e:
                logger.error(f"Error in general chatbot response: {e}")
                fallback_ans = "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요? 매뉴얼 PDF를 업로드하신 뒤 관련 질문(예: 특정 에러 코드나 조치 방법)을 입력해 주시면 정확히 분석하여 답변해 드리겠습니다."
                yield _sse_event("answer", content=fallback_ans)
                collected_answer = fallback_ans
            
            _save_conversation()
            yield _sse_event("done")
            return
        
        # ─── 2단계 구조: 문서 선택 → 페이지 선택 ───

        # [Shortcut] document_id가 지정되지 않았고, 이전 참조 문서(previous_reference)가 있으며,
        # 사용자의 새 질문에 다른 제조사/모델 식별자가 없는 경우 맥락 유지
        if document_id is None:
            all_docs = get_all_documents(owner_email=user_email)
            if all_docs and previous_reference and previous_reference.get("document_id") and len(all_docs) > 1:
                prev_doc_id = str(previous_reference["document_id"])
                
                # 다른 문서들의 제조사/모델 식별자 수집
                other_identifiers = set()
                for d in all_docs:
                    if str(d["document_id"]) == prev_doc_id:
                        continue
                    m = str(d.get("manufacturer", "")).strip()
                    s = str(d.get("model_series", "")).strip()
                    if m and m != "미상":
                        for part in m.split():
                            if len(part) >= 2:
                                other_identifiers.add(part.upper())
                    if s and s != "미상":
                        for part in s.split():
                            if len(part) >= 2:
                                other_identifiers.add(part.upper())
                
                q_upper = question.upper()
                has_other_identifier = any(ident in q_upper for ident in other_identifiers) if other_identifiers else False
                
                if not has_other_identifier:
                    prev_doc = next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)
                    if prev_doc:
                        document_id = prev_doc_id
                        reasoning_content = f"🔄 이전 대화 맥락을 이어받아 '{prev_doc.get('filename')}' 문서에서 검색을 계속합니다."
                        yield _sse_event("reasoning", content=reasoning_content)
                        collected_reasoning.append(reasoning_content)

        if document_id is None:
            all_docs = get_all_documents(owner_email=user_email)
            
            if not all_docs:
                yield _sse_event("error", content="업로드된 문서가 없습니다. 먼저 PDF 매뉴얼을 업로드해 주세요.")
                _save_conversation()
                yield _sse_event("done")
                return
            
            if len(all_docs) == 1:
                yield _sse_event("reasoning", content=f"📄 '{all_docs[0].get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다...")
                collected_reasoning.append(f"📄 '{all_docs[0].get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다...")
            else:
                # ─── ToC 키워드 매칭 1차 필터링 ───
                # 질문의 키워드가 ToC에 포함된 문서만 우선 후보로 좁힘
                question_keywords = set(re.findall(r'[가-힣a-zA-Z0-9]{2,}', question.lower()))
                toc_matched_docs = []
                for d in all_docs:
                    toc_entries = d.get("toc", [])
                    toc_text = " ".join(
                        str(entry.get("title", "")).lower() for entry in toc_entries
                    ).lower()
                    match_count = sum(1 for kw in question_keywords if kw in toc_text)
                    if match_count > 0:
                        toc_matched_docs.append((d, match_count))
                
                if toc_matched_docs:
                    # 매칭 수 내림차순 정렬
                    toc_matched_docs.sort(key=lambda x: x[1], reverse=True)
                    filtered_docs = [d for d, _ in toc_matched_docs]
                    
                    # 이전 참조 문서가 있으면 필터링 후보군에 강제 포함 (소실 방지)
                    if previous_reference and previous_reference.get("document_id"):
                        prev_doc_id = str(previous_reference["document_id"])
                        if not any(str(d["document_id"]) == prev_doc_id for d in filtered_docs):
                            prev_doc = next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)
                            if prev_doc:
                                filtered_docs.append(prev_doc)
                                logger.info(f"🔎 [ToC 키워드 필터] 이전 참조 문서를 후보군에 강제 포함시켰습니다: {prev_doc.get('filename')}")
                    
                    logger.info(f"🔎 [ToC 키워드 필터] {len(all_docs)}개 → {len(filtered_docs)}개 문서로 필터링 (키워드: {question_keywords})")
                    reasoning_content = f"📚 {len(all_docs)}개 문서 중 목차 키워드 매칭으로 {len(filtered_docs)}개 후보를 좁혔습니다..."
                else:
                    filtered_docs = all_docs
                    reasoning_content = f"📚 {len(all_docs)}개 문서 중 적합한 문서와 페이지를 찾고 있습니다..."
                
                yield _sse_event("reasoning", content=reasoning_content)
                collected_reasoning.append(reasoning_content)
            
            # 1단계: 메타데이터로 문서 선택 (ToC 제외)
            # ToC 매칭 필터링된 문서가 있으면 그것을, 없으면 전체 문서를 LLM에 전달
            docs_for_selection = filtered_docs if len(all_docs) > 1 and toc_matched_docs else all_docs
            doc_result = await _select_document(question, docs_for_selection, chat_history, previous_reference)
            
            if doc_result["classification"] == "general":
                # LLM이 일상대화로 판단 → Early Exit
                reasoning_msg = "일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다..."
                yield _sse_event("reasoning", content=reasoning_msg)
                collected_reasoning.append(reasoning_msg)
                
                llm = _create_flash_llm()
                chat_prompt = f"""당신은 산업용 매뉴얼 분석 비서 'Vision RAG 에이전트'입니다.
사용자가 매뉴얼 검색과 관계없는 일반적인 인사나 일상적 대화를 건넸습니다.
친절하고 자연스럽게 인사하고, 매뉴얼 PDF를 업로드하여 질문하면 해당 매뉴얼(알람코드, 도면, 표 등)을 원본 레이아웃 그대로 분석하여 정확하게 답변할 수 있는 도구임을 알려주세요.

사용자 입력: "{question}"

친절하고 자연스럽게 한국어로 답변을 생성해 주세요.
"""
                try:
                    response = await llm.ainvoke([HumanMessage(content=chat_prompt)])
                    answer = _extract_text_content(response.content)
                    yield _sse_event("answer", content=answer)
                    collected_answer = answer
                except Exception as e:
                    logger.error(f"Error in general chatbot response: {e}")
                    fallback_ans = "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요?"
                    yield _sse_event("answer", content=fallback_ans)
                    collected_answer = fallback_ans
                
                _save_conversation()
                yield _sse_event("done")
                return
            
            # 되묻기 판단 — 3중 체크
            candidates = doc_result.get("candidates", [])
            if candidates:
                top = candidates[0]
                second = candidates[1] if len(candidates) > 1 else None
                
                # 체크 1: confidence 기반 (기존)
                confidence_unclear = (
                    top["confidence"] < 0.7 or
                    (second and top["confidence"] - second["confidence"] < 0.2)
                )
                
                # 체크 2: LLM이 직접 판단한 되묻기 필요 여부 (신규)
                llm_says_clarify = doc_result.get("needs_clarification", False)
                
                # 체크 3: 질문에 제조사/모델 키워드가 없는 경우 (신규)
                known_identifiers = set()
                for d in all_docs:
                    m = str(d.get("manufacturer", "")).strip()
                    s = str(d.get("model_series", "")).strip()
                    if m and m != "미상":
                        known_identifiers.add(m.upper())
                        # 제조사명의 주요 부분도 추가 (예: "Mitsubishi Electric" → "MITSUBISHI")
                        for part in m.split():
                            if len(part) >= 2:
                                known_identifiers.add(part.upper())
                    if s and s != "미상":
                        known_identifiers.add(s.upper())
                        for part in s.split():
                            if len(part) >= 2:
                                known_identifiers.add(part.upper())
                
                q_upper = question.upper()
                has_identifier = any(ident in q_upper for ident in known_identifiers) if known_identifiers else False
                no_identifier_in_question = not has_identifier and len(all_docs) > 1
                
                needs_clarification = confidence_unclear or llm_says_clarify or no_identifier_in_question
                
                logger.info(
                    f"🔍 [되묻기 판단] confidence_unclear={confidence_unclear}, "
                    f"llm_says_clarify={llm_says_clarify}, "
                    f"no_identifier={no_identifier_in_question}, "
                    f"→ needs_clarification={needs_clarification}"
                )
                
                if needs_clarification and len(candidates) > 1:
                    # 되묻기 이벤트 발행 — 문서 후보 + 보강 질문 동시 전달
                    clarification_candidates = []
                    for c in candidates[:5]:  # 최대 5개 선택지
                        doc_meta = next((d for d in all_docs if d["document_id"] == c["document_id"]), None)
                        if doc_meta:
                            clarification_candidates.append({
                                "document_id": c["document_id"],
                                "title": doc_meta.get("filename", "알 수 없음"),
                                "manufacturer": doc_meta.get("manufacturer", "미상"),
                                "model_series": doc_meta.get("model_series", "미상"),
                                "confidence": c["confidence"],
                            })
                    
                    # 보강 질문 가져오기 (LLM이 생성한 것)
                    suggested_questions = doc_result.get("suggested_questions", [])
                    
                    # LLM이 보강 질문을 생성하지 않았으면 기본 보강 질문 생성
                    if not suggested_questions:
                        suggested_questions = _generate_default_clarification_questions(question, all_docs)
                    
                    clarification_content = (
                        "질문을 좀 더 구체화하면 정확한 답변을 드릴 수 있어요. "
                        "아래에서 질문을 선택하거나, 해당 매뉴얼을 직접 선택해 주세요."
                    )
                    
                    yield _sse_event(
                        "clarification",
                        content=clarification_content,
                        candidates=clarification_candidates,
                        suggested_questions=suggested_questions,
                    )
                    _save_conversation()
                    yield _sse_event("done")
                    return
                
                document_id = top["document_id"]
            else:
                document_id = all_docs[0]["document_id"]
            
            # 2단계: 선택된 문서의 ToC 전체로 페이지 선택
            selected_doc = next((d for d in all_docs if d["document_id"] == document_id), all_docs[0])
            selected_doc_filename = selected_doc.get('filename', '')
            
            reasoning_content = f"📄 '{selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다..."
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
            
            toc = selected_doc.get("toc", [])
            total_pages = selected_doc.get("total_pages", 0)
            page_result = await _select_pages(question, toc, total_pages, previous_reference)
            
            coarse_pages = page_result.get("target_pages", [1])
            coarse_title = page_result.get("section_title", "")
            coarse_reasoning = page_result.get("reasoning", "")
            
            reasoning_content = f"📄 '{selected_doc_filename}' → '{coarse_title}' (p.{coarse_pages})\n{coarse_reasoning}"
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
            
        else:
            # document_id가 지정된 경우: _select_pages()만 실행
            meta = get_document(document_id, owner_email=user_email)
            if meta is None:
                yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {document_id}")
                _save_conversation()
                yield _sse_event("done")
                return
            
            toc = meta.get("toc", [])
            total_pages = meta.get("total_pages", 0)
            selected_doc_filename = meta.get('filename', '')
            
            reasoning_content = f"📄 '{selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다..."
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
            
            page_result = await _select_pages(question, toc, total_pages, previous_reference)
            coarse_pages = page_result.get("target_pages", [1])
            coarse_title = page_result.get("section_title", "")
            coarse_reasoning = page_result.get("reasoning", "")
            
            reasoning_content = f"📄 → '{coarse_title}' (p.{coarse_pages})\n{coarse_reasoning}"
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
            

        
        # ─── Step 1: 문서 검증 및 PDF 열기 ───
        meta = get_document(document_id)
        if meta is None:
            yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {document_id}")
            _save_conversation()
            yield _sse_event("done")
            return
        
        pdf_path = get_document_path(document_id)
        if pdf_path is None:
            yield _sse_event("error", content="PDF 파일을 찾을 수 없습니다.")
            _save_conversation()
            yield _sse_event("done")
            return
        
        toc = meta.get("toc", [])
        if not toc:
            yield _sse_event("error", content="목차(ToC)가 없는 문서입니다. 먼저 ToC를 추출해주세요.")
            _save_conversation()
            yield _sse_event("done")
            return
        
        try:
            doc = fitz.open(pdf_path)
            total_pages = doc.page_count
        except Exception as e:
            logger.error(f"❌ [Pipeline] PDF 파일 열기 실패 ({pdf_path}): {e}", exc_info=True)
            yield _sse_event("error", content=f"PDF 파일 열기 실패: {str(e)}")
            _save_conversation()
            yield _sse_event("done")
            return

        
        # 섹션 범위 계산 (ToC 기반으로 정확한 섹션 끝 찾기)
        section_start, section_end = _find_section_page_range(toc, coarse_pages, total_pages)
        section_size = section_end - section_start + 1
        
        # ─── Step 2: 텍스트 기반 정밀 탐색 (Phase 2) ───
        if section_size > 3:
            reasoning_content = f"[세부 탐색] '{coarse_title}' 섹션(p.{section_start}~{section_end})의 텍스트를 분석하여 정확한 페이지를 찾고 있습니다..."
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
            
            # C-3: 비동기 호출
            phase2_result = await _refine_pages_with_text(doc, section_start, section_end, question)
            target_pages = phase2_result.get("target_pages", coarse_pages)
            refined_title = phase2_result.get("section_title", coarse_title)
            refined_reasoning = phase2_result.get("reasoning", "")
            
            reasoning_content = f"[세부 탐색] '{refined_title}' → 타겟 페이지 {target_pages}\n{refined_reasoning}"
            yield _sse_event("reasoning", content=reasoning_content)
            collected_reasoning.append(reasoning_content)
        else:
            # 섹션이 작으면 Phase 1 결과를 그대로 사용
            target_pages = coarse_pages
        
        # ─── Step 4: 미니 PDF 추출 + 참조 이미지 생성 ───
        yield _sse_event("reasoning", content=f"페이지 {target_pages}에서 미니 PDF를 추출하고 있습니다...")
        collected_reasoning.append(f"페이지 {target_pages}에서 미니 PDF를 추출하고 있습니다...")
        
        try:
            # 중복 제거 및 유효 범위 정규화 (1-indexed -> 0-indexed)
            valid_pages = []
            for p in target_pages:
                norm = _normalize_page(p) - 1
                if 0 <= norm < total_pages and norm not in valid_pages:
                    valid_pages.append(norm)
            
            if not valid_pages:
                valid_pages = [0]
            
            # 💡 [버그 패치] 비연속적으로 멀리 떨어진 페이지(예: p.12, p.115)가 잡힐 경우, 
            # min~max 범위의 모든 중간 페이지가 다 삽입되어 PDF가 비정상적으로 비대해지는 현상을 해결합니다.
            # 필요한 페이지만 콕 집어서(sparse) 미니 PDF를 빌드합니다. (토큰 절약을 위해 RAG 타겟페이지만 포함)
            mini_doc = fitz.open()
            core_valid_pages = sorted(set([_normalize_page(p) - 1 for p in target_pages if 1 <= _normalize_page(p) <= total_pages]))
            if not core_valid_pages:
                core_valid_pages = [0]
            for page_idx in core_valid_pages:
                mini_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
            mini_pdf_bytes = mini_doc.tobytes()
            mini_doc.close()
            
            # RAG 코어 타겟과 ToC 후보 페이지 모두의 썸네일 이미지를 생성해서 프론트로 송출
            for page_idx in valid_pages:
                try:
                    png_bytes = render_page_thumbnail(doc, page_idx, dpi=150)
                    image_base64 = f"data:image/png;base64,{base64.b64encode(png_bytes).decode('utf-8')}"
                    page_num = page_idx + 1
                    yield _sse_event(
                        "reference",
                        page_number=page_num,
                        image_base64=image_base64,
                        document_id=str(document_id),
                        document_name=selected_doc_filename,
                    )
                    collected_references.append({"page_number": page_num})
                except Exception as e:
                    logger.error(f"❌ [Pipeline] Thumbnail generation error for page {page_idx}: {e}")
            
            doc.close()
            
        except Exception as e:
            doc.close()
            logger.error(f"❌ [Pipeline] PDF 처리 및 참조 이미지 생성 실패: {e}", exc_info=True)
            yield _sse_event("error", content=f"PDF 처리 중 오류: {str(e)}")
            _save_conversation()
            yield _sse_event("done")
            return

        
        # ─── Step 5: Vision LLM 분석 (스트리밍) + B-1 Fallback ───
        yield _sse_event("reasoning", content="Gemini Vision으로 페이지를 분석하고 있습니다...")
        collected_reasoning.append("Gemini Vision으로 페이지를 분석하고 있습니다...")
        
        try:
            async for chunk in analyze_pages_with_vision(mini_pdf_bytes, question, chat_history=chat_history):
                yield _sse_event("answer", content=chunk)
                collected_answer += chunk
        except Exception as e:
            logger.error(f"❌ [Pipeline] Vision 분석 3회 재시도 모두 실패: {e}", exc_info=True)
            
            # B-1 Fallback: Vision 실패 시 텍스트 기반 답변 생성
            yield _sse_event("reasoning", content="⚠️ Vision 분석이 실패하여 텍스트 기반으로 답변을 생성합니다...")
            collected_reasoning.append("⚠️ Vision 분석이 실패하여 텍스트 기반으로 답변을 생성합니다...")
            try:
                fallback_answer = await _generate_text_fallback(pdf_path, target_pages, question, chat_history)
                yield _sse_event("answer", content=fallback_answer)
                collected_answer += fallback_answer
            except Exception as fb_err:
                logger.error(f"❌ [Pipeline] 텍스트 Fallback도 실패: {fb_err}", exc_info=True)
                yield _sse_event("error", content=f"Vision 분석 및 텍스트 분석 모두 실패: {str(e)}")
        
        logger.info("🏁 [Pipeline] Agentic Search 파이프라인 처리 완료")
        
        _save_conversation()
        yield _sse_event("done")
    
    except GeneratorExit:
        logger.info("🛑 [Pipeline] 클라이언트 중단 요청 → 파이프라인 조기 종료")
        return
    except Exception as e:
        logger.error(f"❌ [Pipeline] 예상치 못한 오류: {e}", exc_info=True)
        yield _sse_event("error", content=f"시스템 오류: {str(e)}")
        _save_conversation()
        yield _sse_event("done")


async def _generate_text_fallback(
    pdf_path: str,
    target_pages: list[int],
    question: str,
    chat_history: list[dict] | None = None,
) -> str:
    """
    B-1 Fallback: Vision 분석 실패 시 텍스트를 추출하여 LLM으로 답변을 생성합니다.
    PyMuPDF로 타겟 페이지의 텍스트를 추출하고, Flash-Lite LLM에게 답변을 요청합니다.
    """
    doc = fitz.open(pdf_path)
    
    text_content = []
    for page_num in target_pages:
        if 1 <= page_num <= doc.page_count:
            text = doc[page_num - 1].get_text()
            text_content.append(f"--- PAGE {page_num} ---\n{text}\n")
    
    doc.close()
    full_text = "\n".join(text_content)
    
    if not full_text.strip():
        return "⚠️ 해당 페이지에서 텍스트를 추출할 수 없습니다. 스캔된 PDF이거나 이미지 기반 문서일 수 있습니다."
    
    # 대화 이력 구성
    context_section = ""
    if chat_history:
        recent = chat_history[-4:]
        pairs = [f"{'사용자' if m['role']=='user' else 'AI'}: {m['content'][:200]}" for m in recent]
        context_section = "\n이전 대화 맥락:\n" + "\n".join(pairs) + "\n"
    
    prompt = f"""당신은 산업용 매뉴얼 전문 분석가입니다.
아래는 매뉴얼에서 추출한 텍스트입니다. 이 텍스트를 분석하여 사용자의 질문에 정확하게 답변하세요.
{context_section}
질문: "{question}"

--- 매뉴얼 텍스트 시작 ---
{full_text[:8000]}
--- 매뉴얼 텍스트 끝 ---

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
    
    llm = _create_flash_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return _extract_text_content(response.content)
