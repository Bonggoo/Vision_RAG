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
from app.services.metadata_service import (
    get_document, get_document_path, get_all_documents,
    get_document_async, get_document_path_async, get_all_documents_async,
)
from app.services.agent_service import analyze_pages_with_vision, _create_flash_llm, _clean_json_response, _extract_text_content
from app.services.pdf_service import render_page_thumbnail, normalize_manufacturer
from app.prompts import general_chat_prompt, refine_pages_prompt, select_document_prompt, select_pages_prompt
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

    주의: 이 문장들은 프론트에서 탭하면 '사용자 메시지'로 그대로 전송됩니다.
    따라서 AI가 사용자에게 묻는 문장("제조사가 어디인가요?")이 아니라,
    원 질문에 후보 문서의 제조사/모델을 덧붙여 재작성한 '사용자 입장의 질문'
    이어야 합니다. 예: "통신 에러 해결법" → "MITSUBISHI MELSEC-Q 통신 에러 해결법"

    질문에 이미 들어있는 제조사(별칭 포함)/모델은 다시 붙이지 않으며
    ("미쓰비시 Q 시리즈..." 질문에 "MITSUBISHI Q 시리즈"를 중복 부착 방지),
    덧붙일 정보가 없는 후보는 건너뜁니다. 전부 건너뛰면 빈 리스트를 반환해
    프론트가 추천 질문 섹션을 숨기고 문서 선택 카드만 노출하게 합니다.
    """
    q_lower = question.lower()
    q_manufacturer = normalize_manufacturer(question)  # 질문에 이미 언급된 제조사 (별칭 흡수)
    questions = []
    seen_prefixes = set()
    for d in documents:
        m = str(d.get("manufacturer", "")).strip()
        s = str(d.get("model_series", "")).strip()
        parts = []
        if m and m != "미상" and normalize_manufacturer(m) != q_manufacturer:
            parts.append(m)
        if s and s != "미상" and s.lower() not in q_lower:
            parts.append(s)
        if not parts:
            continue  # 이 후보로는 질문에 더할 정보가 없음
        prefix = " ".join(parts)
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        questions.append(f"{prefix} {question}")
        if len(questions) >= 3:
            break
    return questions


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


# ToC가 없는 문서에서 전체 페이지를 그대로 Vision 분석할 수 있는 최대 페이지 수.
# 이미지 업로드(1페이지)나 짧은 일반 문서(회의록·점검표 등)가 여기에 해당합니다.
SMALL_DOC_FULL_SCAN_PAGES = 5


def _resolve_target_pages_without_toc(total_pages: int) -> list[int] | None:
    """
    ToC 없는 문서의 전체 페이지 폴백을 계산합니다.
    소형 문서면 전체 페이지 목록(1-indexed)을, 대형이면 None(기존 에러 유지)을 반환합니다.
    """
    if 0 < total_pages <= SMALL_DOC_FULL_SCAN_PAGES:
        return list(range(1, total_pages + 1))
    return None


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

    prompt = refine_pages_prompt(question, full_text, section_start)

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
    toc_evidence: dict | None = None,
) -> dict:
    """
    1단계: 메타데이터만으로 문서 선택 + 일상대화 판별.
    ToC 전체는 제외하여 토큰을 절약하되(~2,500 토큰), toc_evidence로 전달된
    "질문 키워드와 겹친 ToC 제목"만 해당 문서에 한 줄 표기합니다 — 'SMATV'처럼
    문서 제목에는 없고 목차에만 있는 단서로 문서를 골라야 하는 질문 대응.

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

    # 각 문서의 메타데이터 요약 (ToC 전체는 제외하여 토큰 절약,
    # 질문 키워드와 겹친 ToC 제목만 근거로 표기)
    doc_summaries = []
    for i, doc in enumerate(documents):
        summary = (
            f"[문서 {i+1}]\n"
            f"  ID: {doc['document_id']}\n"
            f"  제목: {doc.get('filename', '알 수 없음')}\n"
            f"  제조사: {doc.get('manufacturer', '미상')}\n"
            f"  모델 시리즈: {doc.get('model_series', '미상')}\n"
            f"  문서 종류: {doc.get('document_type', '미상')}\n"
            f"  페이지 수: {doc.get('total_pages', 0)}"
        )
        matched_titles = (toc_evidence or {}).get(str(doc.get("document_id", "")))
        if matched_titles:
            summary += f"\n  ★ 질문 키워드와 일치하는 목차 항목: {', '.join(matched_titles)}"
        doc_summaries.append(summary)

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

    prompt = select_document_prompt(docs_text, context_section, previous_reference_section, question)

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

    prompt = select_pages_prompt(toc_text, total_pages, previous_pages_section, question)

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


class _PipelineContext:
    """
    파이프라인 전역 상태와 SSE 수집/대화 저장을 캡슐화합니다.

    각 stage는 이 컨텍스트를 공유하며 SSE 이벤트를 yield합니다.
    early exit가 필요한 stage는 `yield await ctx.finish()` 후 `return`하고,
    orchestrator가 `ctx.done`을 확인해 파이프라인을 종료합니다.
    """

    def __init__(self, document_id, question, chat_history, image, user_email, session_id, previous_reference):
        self.document_id = document_id
        self.question = question
        self.chat_history = chat_history
        self.image = image
        self.user_email = user_email
        self.session_id = session_id
        self.previous_reference = previous_reference
        # SSE 수집 상태 (GCS 저장용)
        self.collected_answer = ""
        self.collected_reasoning = []
        self.collected_references = []
        self.selected_doc_filename = ""
        # 종료 신호 (early exit를 orchestrator에 전달)
        self.done = False
        # stage 간 공유되는 1차 페이지 선택 산출물
        self.coarse_pages = [1]
        self.coarse_title = ""

    def reasoning(self, content: str) -> str:
        """reasoning 이벤트를 만들고 수집 목록에 추가합니다. `yield ctx.reasoning(...)`로 사용."""
        self.collected_reasoning.append(content)
        return _sse_event("reasoning", content=content)

    def add_answer(self, content: str) -> str:
        """answer 이벤트를 만들고 누적합니다. `yield ctx.add_answer(...)`로 사용."""
        self.collected_answer += content
        return _sse_event("answer", content=content)

    async def save_conversation(self):
        """수집된 메시지를 GCS에 저장합니다 (모든 종료 경로에서 호출)."""
        if not (self.session_id and self.user_email and (self.collected_answer or self.collected_reasoning)):
            return
        try:
            from app.services.conversation_service import save_message_async
            user_msg = {
                "role": "user",
                "content": self.question,
                "image": self.image,
            }
            assistant_msg = {
                "role": "assistant",
                "content": self.collected_answer,
                "reasoning_steps": self.collected_reasoning,
                "reference_pages": [ref["page_number"] for ref in self.collected_references],
                "reference_document_id": str(self.document_id) if self.document_id else None,
                "reference_document_name": self.selected_doc_filename if self.document_id else None,
            }
            title_text = self.question[:25] + "..." if len(self.question) > 25 else self.question
            await save_message_async(self.user_email, self.session_id, user_msg, assistant_msg, title=title_text)
        except Exception as e:
            logger.error(f"❌ [Pipeline] 대화 저장 실패 (무시): {e}")

    async def finish(self) -> str:
        """종료 처리: 대화 저장 + done 이벤트 생성 + done 플래그 설정."""
        await self.save_conversation()
        self.done = True
        return _sse_event("done")


async def _generate_general_answer(ctx: "_PipelineContext", fallback_ans: str):
    """일상대화 답변을 LLM으로 생성합니다. 실패 시 전달된 fallback 메시지를 사용합니다."""
    llm = _create_flash_llm()
    chat_prompt = general_chat_prompt(ctx.question)
    try:
        response = await llm.ainvoke([HumanMessage(content=chat_prompt)])
        answer = _extract_text_content(response.content)
        yield ctx.add_answer(answer)
    except Exception as e:
        logger.error(f"Error in general chatbot response: {e}")
        yield ctx.add_answer(fallback_ans)


async def _stage_image_analysis(ctx: "_PipelineContext"):
    """Step -1: 업로드된 장비 이미지를 분석하여 document_id를 보강하고 질문을 리라이팅합니다."""
    if not ctx.image:
        return

    yield ctx.reasoning("📸 업로드하신 장비 이미지를 분석하고 있습니다...")
    try:
        from app.services.agent_service import analyze_device_image_with_gemini
        analyzed_meta = await analyze_device_image_with_gemini(ctx.image)

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

            yield ctx.reasoning("🔍 이미지 인식 성공!\n- " + "\n- ".join(info_parts))

            # 문서 매칭: document_id가 지정되지 않은 경우, 분석된 제조사/모델과 일치하는 문서 검색
            if ctx.document_id is None:
                all_docs = await get_all_documents_async(owner_email=ctx.user_email)
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
                    ctx.document_id = matched_doc["document_id"]
                    yield ctx.reasoning(f"📂 분석 정보를 기반으로 매칭된 매뉴얼을 자동으로 선택했습니다:\n- 파일명: {matched_doc.get('filename')}")

            # 질문 보강 (리라이팅)
            rewritten_parts = []
            if manuf: rewritten_parts.append(manuf)
            if model: rewritten_parts.append(model)
            if err_code: rewritten_parts.append(f"알람코드 {err_code}")
            if symptom: rewritten_parts.append(symptom)

            if rewritten_parts:
                # 사용자 질문이 비어있거나 너무 짧으면 알람 분석 질문으로 대체
                if len(ctx.question.strip()) < 5:
                    ctx.question = f"{' '.join(rewritten_parts)} 원인과 조치 대처법"
                else:
                    ctx.question = f"{' '.join(rewritten_parts)} 에러 상황: {ctx.question}"

                yield ctx.reasoning(f"⚙️ 질문 보강 완료: '{ctx.question}'")
        else:
            yield ctx.reasoning("⚠️ 이미지에서 명확한 장비 브랜드나 알람코드를 파악하지 못해 일반 RAG 모드로 계속합니다.")
    except Exception as e:
        logger.error(f"Error in image preprocessing: {e}")
        yield ctx.reasoning(f"⚠️ 이미지 분석 중 오류 발생, 일반 RAG 모드로 진행합니다. (오류: {e})")


async def _stage_quick_general(ctx: "_PipelineContext"):
    """C-1: 규칙 기반 빠른 분류가 명확한 일상대화로 판단하면 즉시 답변 후 종료합니다."""
    if _quick_classify(ctx.question) != "general":
        return

    yield ctx.reasoning("일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다...")
    async for ev in _generate_general_answer(
        ctx,
        "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요? 매뉴얼 PDF를 업로드하신 뒤 관련 질문(예: 특정 에러 코드나 조치 방법)을 입력해 주시면 정확히 분석하여 답변해 드리겠습니다.",
    ):
        yield ev
    yield await ctx.finish()


_MODEL_CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/\-]{1,}")


def _extract_model_codes(text: str) -> set[str]:
    """텍스트에서 모델번호처럼 보이는 토큰(영문+숫자 혼합, 3자 이상)만 추출합니다.

    예: 'F388A', 'L7NH', 'QD74MH', 'LS-R900', 'CZ-V20'.
    순수 숫자('4800'), 알파벳만('CV'), 알람코드처럼 점으로 끊기는 것('AL.20'),
    2자 이하('2D')는 제외해 오탐을 줄입니다. 한글 조사는 정규식 문자군 밖이라
    자동으로 경계가 잘립니다(예: 'F388A를' → 'F388A').

    질문에 명시된 모델번호를 문서 메타데이터와 '정확 일치'로 대조해 강하게
    가중하기 위한 신호입니다 — F388A 질문이 F381 매뉴얼로 새는 것을 막습니다.
    """
    codes = set()
    for tok in _MODEL_CODE_RE.findall(text or ""):
        if len(tok) < 3:
            continue
        if any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok):
            codes.add(tok.casefold())
    return codes


# ─── 1차 문서 필터 (키워드 매칭) ─────────────────────────────────────────────

# 주요 산업 도메인 동의어 매핑 (한글 키워드가 들어왔을 때 영문 ToC와 매칭 지원)
_SYNONYMS = {
    "위치결정": ["positioning"],
    "알람": ["alarm", "error", "warning", "err", "al"],
    "에러": ["error", "err", "alarm"],
    "경고": ["warning", "warn"],
    "모듈": ["module"],
    "서보": ["servo"],
    "설명서": ["manual"],
    "매뉴얼": ["manual"],
}

# 한글 조사 목록 — 긴 것부터 시도해 최장 일치를 제거
_JOSA = sorted([
    "은", "는", "이", "가", "을", "를", "의", "에", "도", "만",
    "와", "과", "랑", "로", "으로", "에서", "에게", "한테",
    "보다", "부터", "까지", "처럼", "같이", "마다", "조차", "마저", "밖에",
    "이나", "이란", "에는", "에도", "와의", "과의",
    "로는", "로도", "으로는", "으로도", "만으로", "에서는", "에서도",
], key=len, reverse=True)


def _strip_josa(token: str) -> str:
    """한글 토큰 끝의 조사를 떼어낸 어근을 반환합니다 (뗄 게 없으면 원본).

    형태소 분석기 의존성 없이 최장 일치 접미사 제거로 근사합니다.
    어근이 2자 미만으로 남으면('차이'→'차'처럼 파괴되면) 떼지 않습니다.
    매칭이 substring 방식이므로 어근은 조사 붙은 원형이 매칭되는 모든 곳에
    + 그 이상을 매칭합니다 — 원형을 어근으로 '대체'해도 recall 손실이 없습니다.
    (예: '색상의'→'색상', '설정값을'→'설정값', '차이만으로'→'차이')
    """
    if not token or not ("가" <= token[-1] <= "힣"):
        return token
    for josa in _JOSA:
        if token.endswith(josa) and len(token) - len(josa) >= 2:
            return token[: -len(josa)]
    return token


def _filter_documents_by_keywords(question: str, all_docs: list[dict]) -> tuple[list[dict], str, dict]:
    """질문 키워드로 문서 후보를 좁히는 1차 필터.

    반환: (후보 문서 리스트, mode, toc_evidence)
      mode = "filtered"       — 증거가 충분해 후보를 좁혔음 (점수 내림차순 정렬)
             "fallback_weak"  — 매칭이 전부 미약(ToC 우연 매칭 1~2건)해 필터를
                                신뢰하지 않고 전체 문서를 반환
             "fallback_none"  — 매칭된 문서가 없어 전체 문서를 반환
      toc_evidence = {document_id: [질문 키워드와 겹친 ToC 제목, ...]}
             — 변별 키워드가 ToC 제목에서 발견된 문서만 담김. 점수로 뭉개지 않고
               문서 선택 LLM에게 그대로 전달해, 'SMATV'처럼 문서 제목에는 없고
               목차에만 있는 단서로도 올바른 문서를 고를 수 있게 하는 근거 자료.
               (점수만 넘기던 기존 구조에서는 이 발견이 전달 과정에서 증발했음)

    설계 (질문 품질 평가 107문항 실측에서 실패 8건이 전부 '정답 문서가 필터에서
    0점 탈락'한 recall 문제였던 것을 근거로 함):
      1. 조사 스트리핑 — 어절 토큰의 조사 때문에 '색상의'가 ToC의 '색상'과
         매칭되지 않던 진짜 매칭 실패를 해소.
      2. DF 컷 — 보유 문서의 1/3 이상에 등장하는 키워드('설정' 등 범용어)는
         변별력이 없으므로 점수에서 제외. ToC가 방대한 문서가 범용어 우연
         매칭으로 후보를 독식하던 문제를 해소. 코퍼스 기준 즉석 계산이라
         사용자마다 자가 적응.
      3. 확신 게이트 — 최고점이 META_WEIGHT 미만(파일명/제조사/모델 직접 매칭
         전무)이면 필터가 정답을 놓쳤을 가능성이 커서 전체 문서로 폴백.
         배제형 필터에서 0점 정답 문서는 이후 어떤 단계로도 복구 불가하므로,
         약한 증거로는 배제하지 않는다.
    """
    META_WEIGHT, TOC_WEIGHT, MODEL_WEIGHT = 3, 1, 12

    raw_keywords = set(re.findall(r"[가-힣a-zA-Z0-9]{2,}", question.lower()))
    keywords = {_strip_josa(kw) for kw in raw_keywords}

    extended_keywords = set(keywords)
    for kw in keywords:
        for kor_key, eng_vals in _SYNONYMS.items():
            if kor_key in kw:
                extended_keywords.update(eng_vals)

    question_model_codes = _extract_model_codes(question)

    # 문서별 검색 텍스트 사전 구성 (파일명/제조사/모델 = meta, ToC 제목 = toc).
    # 파일명·모델 직접 매칭이 ToC 언급보다 훨씬 강한 관련도 신호이므로
    # 가중치를 다르게 둡니다.
    doc_texts = []
    for d in all_docs:
        meta_text = " ".join([
            str(d.get("filename") or ""),
            str(d.get("manufacturer") or ""),
            str(d.get("model_series") or ""),
        ]).lower()
        toc_text = " ".join(
            str(entry.get("title") or "") for entry in (d.get("toc") or [])
        ).lower()
        doc_texts.append(
            (d, meta_text, meta_text.replace(" ", ""), toc_text, toc_text.replace(" ", ""))
        )

    def _hit(kw: str, mt: str, mns: str, tt: str, tns: str) -> str | None:
        kwl = kw.lower()
        kwns = kwl.replace(" ", "")
        if kwl in mt or kwns in mns:
            return "meta"
        if kwl in tt or kwns in tns:
            return "toc"
        return None

    # DF 컷: 코퍼스의 1/3 초과 문서에 매칭되는 키워드는 변별력 없음 → 제외
    max_df = max(1, len(all_docs) // 3)
    discriminative = set()
    kw_df: dict[str, int] = {}
    for kw in extended_keywords:
        df = sum(1 for (_, mt, mns, tt, tns) in doc_texts if _hit(kw, mt, mns, tt, tns))
        kw_df[kw] = df
        if 0 < df <= max_df:
            discriminative.add(kw)

    # 증거(쪽지)용 키워드는 한층 더 엄격하게: 극소수 문서에만 등장하는 단어만.
    # '명령'·'있는'처럼 DF컷(1/3)은 통과하지만 10여 개 문서에 흔한 준범용어가
    # 잡음 쪽지를 남발하는 것을 방지 — 'SMATV'(1개 문서)급 단서만 전달한다.
    evidence_max_df = max(3, len(all_docs) // 10)
    evidence_kws = {kw for kw in discriminative if kw_df[kw] <= evidence_max_df}

    MAX_EVIDENCE_TITLES = 8  # 문서당 프롬프트에 전달할 매칭 ToC 제목 상한

    scored = []
    toc_evidence: dict[str, list[str]] = {}
    for (d, mt, mns, tt, tns) in doc_texts:
        score = 0
        toc_hit_kws = []
        for kw in discriminative:
            where = _hit(kw, mt, mns, tt, tns)
            if where == "meta":
                score += META_WEIGHT
            elif where == "toc":
                score += TOC_WEIGHT
                if kw in evidence_kws:
                    toc_hit_kws.append(kw)

        # ToC에서 발견된 변별 키워드는 어느 제목에서 나왔는지까지 수집.
        # (범용어는 discriminative 단계에서 이미 걸러졌으므로 쪽지가 남발되지 않음)
        if toc_hit_kws:
            titles = []
            for entry in (d.get("toc") or []):
                title = str(entry.get("title") or "")
                tl = title.lower()
                tl_ns = tl.replace(" ", "")
                if any(kw.lower() in tl or kw.lower().replace(" ", "") in tl_ns for kw in toc_hit_kws):
                    titles.append(title[:60])
                    if len(titles) >= MAX_EVIDENCE_TITLES:
                        break
            if titles:
                toc_evidence[str(d.get("document_id", ""))] = titles

        # 명시 모델번호 정확 일치 → 강한 가중 (예: 'F388A' 질문 → 'F388A' 매뉴얼)
        if question_model_codes:
            matched_codes = question_model_codes & _extract_model_codes(mt)
            if matched_codes:
                score += MODEL_WEIGHT * len(matched_codes)

        if score > 0:
            scored.append((d, score))

    if not scored:
        return list(all_docs), "fallback_none", toc_evidence

    scored.sort(key=lambda x: x[1], reverse=True)
    if scored[0][1] < META_WEIGHT:
        return list(all_docs), "fallback_weak", toc_evidence

    return [d for d, _ in scored], "filtered", toc_evidence


async def _stage_resolve_document(ctx: "_PipelineContext"):
    """
    문서 선택(또는 맥락 유지)과 ToC 기반 1차 페이지 선택을 수행합니다.
    결과는 ctx.document_id / ctx.selected_doc_filename / ctx.coarse_pages / ctx.coarse_title에 저장됩니다.
    early exit(문서 없음 / 일상대화 / 되묻기 / 문서 미발견) 시 ctx.finish()를 yield합니다.
    """
    # [Shortcut] document_id가 지정되지 않았고, 이전 참조 문서(previous_reference)가 있으며,
    # 사용자의 새 질문에 다른 제조사/모델 식별자가 없는 경우 맥락 유지
    if ctx.document_id is None:
        all_docs = await get_all_documents_async(owner_email=ctx.user_email)
        if all_docs and ctx.previous_reference and ctx.previous_reference.get("document_id") and len(all_docs) > 1:
            prev_doc_id = str(ctx.previous_reference["document_id"])

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

            q_upper = ctx.question.upper()
            has_other_identifier = any(ident in q_upper for ident in other_identifiers) if other_identifiers else False

            if not has_other_identifier:
                prev_doc = next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)
                if prev_doc:
                    ctx.document_id = prev_doc_id
                    yield ctx.reasoning(f"🔄 이전 대화 맥락을 이어받아 '{prev_doc.get('filename')}' 문서에서 검색을 계속합니다.")

    if ctx.document_id is None:
        all_docs = await get_all_documents_async(owner_email=ctx.user_email)

        if not all_docs:
            yield _sse_event("error", content="업로드된 문서가 없습니다. 먼저 PDF 매뉴얼을 업로드해 주세요.")
            yield await ctx.finish()
            return

        filtered_docs = all_docs
        filter_mode = "fallback_none"
        toc_evidence: dict = {}

        if len(all_docs) == 1:
            yield ctx.reasoning(f"📄 '{all_docs[0].get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다...")
        else:
            # ─── 1차 필터링 (메타데이터 및 ToC 키워드 매칭) ───
            # 조사 스트리핑 + DF 컷 + 확신 게이트는 _filter_documents_by_keywords 참고
            filtered_docs, filter_mode, toc_evidence = _filter_documents_by_keywords(ctx.question, all_docs)

            if filter_mode == "filtered":
                # 이전 참조 문서가 있으면 필터링 후보군에 강제 포함 (소실 방지)
                if ctx.previous_reference and ctx.previous_reference.get("document_id"):
                    prev_doc_id = str(ctx.previous_reference["document_id"])
                    if not any(str(d["document_id"]) == prev_doc_id for d in filtered_docs):
                        prev_doc = next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)
                        if prev_doc:
                            filtered_docs.append(prev_doc)
                            logger.info(f"🔎 [ToC 키워드 필터] 이전 참조 문서를 후보군에 강제 포함시켰습니다: {prev_doc.get('filename')}")

                logger.info(f"🔎 [ToC 키워드 필터] {len(all_docs)}개 → {len(filtered_docs)}개 문서로 필터링")
                reasoning_content = f"📚 {len(all_docs)}개 문서 중 목차 키워드 매칭으로 {len(filtered_docs)}개 후보를 좁혔습니다..."
            else:
                # 매칭 없음 또는 증거 미약 → 필터를 신뢰하지 않고 전체 문서를 LLM에 전달
                logger.info(f"🔎 [ToC 키워드 필터] {filter_mode} → 전체 {len(all_docs)}개 문서를 LLM에 전달")
                reasoning_content = f"📚 {len(all_docs)}개 문서 중 적합한 문서와 페이지를 찾고 있습니다..."

            yield ctx.reasoning(reasoning_content)

        # 1단계: 메타데이터로 문서 선택 (ToC 전체 제외, 매칭된 ToC 제목만 근거로 첨부)
        # 필터가 확신할 때만 좁힌 후보를, 아니면 전체 문서를 LLM에 전달
        docs_for_selection = filtered_docs if len(all_docs) > 1 and filter_mode == "filtered" else all_docs
        doc_result = await _select_document(
            ctx.question, docs_for_selection, ctx.chat_history, ctx.previous_reference,
            toc_evidence=toc_evidence,
        )

        if doc_result["classification"] == "general":
            # LLM이 일상대화로 판단 → Early Exit
            yield ctx.reasoning("일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다...")
            async for ev in _generate_general_answer(ctx, "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요?"):
                yield ev
            yield await ctx.finish()
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

            q_upper = ctx.question.upper()
            has_identifier = any(ident in q_upper for ident in known_identifiers) if known_identifiers else False
            no_identifier_in_question = not has_identifier and len(all_docs) > 1

            needs_clarification = confidence_unclear or llm_says_clarify or no_identifier_in_question

            logger.info(
                f"🔍 [되묻기 판단] confidence_unclear={confidence_unclear}, "
                f"llm_says_clarify={llm_says_clarify}, "
                f"no_identifier={no_identifier_in_question}, "
                f"→ needs_clarification={needs_clarification}"
            )

            # 되묻기 후보 메뉴 구성: LLM 후보 + ToC 관련도 상위 문서로 보강.
            # LLM이 후보를 1개만 반환해도, 질문에 식별자가 없으면(no_identifier)
            # 관련 문서들을 함께 제시해 사용자가 올바른 매뉴얼을 고르게 합니다.
            # (기존 버그: 후보가 1개면 needs_clarification여도 되묻기를 건너뛰고
            #  그 단일 후보로 확신에 찬 오답을 냈음)
            clarification_candidates = []
            seen_ids = set()

            def _add_candidate(doc_meta, confidence):
                if doc_meta and doc_meta["document_id"] not in seen_ids:
                    seen_ids.add(doc_meta["document_id"])
                    clarification_candidates.append({
                        "document_id": doc_meta["document_id"],
                        "title": doc_meta.get("filename", "알 수 없음"),
                        "manufacturer": doc_meta.get("manufacturer", "미상"),
                        "model_series": doc_meta.get("model_series", "미상"),
                        "confidence": confidence,
                    })

            for c in candidates[:5]:  # LLM 후보 우선
                doc_meta = next((d for d in all_docs if d["document_id"] == c["document_id"]), None)
                _add_candidate(doc_meta, c["confidence"])

            # 후보가 2개 미만이면 관련도 상위 문서로 보강 (최대 5개)
            if len(clarification_candidates) < 2:
                for d in docs_for_selection:
                    if len(clarification_candidates) >= 5:
                        break
                    _add_candidate(d, 0.0)

            # 되묻기 조건: 불명확 판단 + 제시할 후보가 2개 이상일 때만.
            # (관련 문서가 실제로 1개뿐이면 모호함이 없으므로 그대로 답변)
            if needs_clarification and len(clarification_candidates) >= 2:
                # 보강 질문 가져오기 (LLM이 생성한 것)
                suggested_questions = doc_result.get("suggested_questions", [])

                # LLM이 보강 질문을 생성하지 않았으면 기본 보강 질문 생성
                # (화면에 함께 뜨는 후보 문서 기준으로 재작성 질문을 만들어 일관성 유지)
                if not suggested_questions:
                    suggested_questions = _generate_default_clarification_questions(
                        ctx.question, clarification_candidates)

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
                yield await ctx.finish()
                return

            ctx.document_id = top["document_id"]
        else:
            ctx.document_id = all_docs[0]["document_id"]

        # 2단계: 선택된 문서의 ToC 전체로 페이지 선택
        selected_doc = next((d for d in all_docs if d["document_id"] == ctx.document_id), all_docs[0])
        ctx.selected_doc_filename = selected_doc.get('filename', '')

        yield ctx.reasoning(f"📄 '{ctx.selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다...")

        toc = selected_doc.get("toc", [])
        total_pages = selected_doc.get("total_pages", 0)
        page_result = await _select_pages(ctx.question, toc, total_pages, ctx.previous_reference)

        ctx.coarse_pages = page_result.get("target_pages", [1])
        ctx.coarse_title = page_result.get("section_title", "")
        coarse_reasoning = page_result.get("reasoning", "")

        yield ctx.reasoning(f"📄 '{ctx.selected_doc_filename}' → '{ctx.coarse_title}' (p.{ctx.coarse_pages})\n{coarse_reasoning}")

    else:
        # document_id가 지정된 경우: _select_pages()만 실행
        meta = await get_document_async(ctx.document_id, owner_email=ctx.user_email)
        if meta is None:
            yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {ctx.document_id}")
            yield await ctx.finish()
            return

        toc = meta.get("toc", [])
        total_pages = meta.get("total_pages", 0)
        ctx.selected_doc_filename = meta.get('filename', '')

        yield ctx.reasoning(f"📄 '{ctx.selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다...")

        page_result = await _select_pages(ctx.question, toc, total_pages, ctx.previous_reference)
        ctx.coarse_pages = page_result.get("target_pages", [1])
        ctx.coarse_title = page_result.get("section_title", "")
        coarse_reasoning = page_result.get("reasoning", "")

        yield ctx.reasoning(f"📄 → '{ctx.coarse_title}' (p.{ctx.coarse_pages})\n{coarse_reasoning}")


async def _stage_answer(ctx: "_PipelineContext"):
    """
    Step 1~5: 문서 검증 → PDF 열기 → Phase 2 정밀 탐색 → 미니 PDF/참조 이미지 → Vision 답변.
    모든 종료 경로에서 ctx.finish()를 yield합니다.
    """
    # ─── Step 1: 문서 검증 및 PDF 열기 ───
    meta = await get_document_async(ctx.document_id, owner_email=ctx.user_email)
    if meta is None:
        yield _sse_event("error", content=f"문서를 찾을 수 없습니다: {ctx.document_id}")
        yield await ctx.finish()
        return

    pdf_path = await get_document_path_async(ctx.document_id, owner_email=ctx.user_email)
    if pdf_path is None:
        yield _sse_event("error", content="PDF 파일을 찾을 수 없습니다.")
        yield await ctx.finish()
        return

    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
    except Exception as e:
        logger.error(f"❌ [Pipeline] PDF 파일 열기 실패 ({pdf_path}): {e}", exc_info=True)
        yield _sse_event("error", content=f"PDF 파일 열기 실패: {str(e)}")
        yield await ctx.finish()
        return

    toc = meta.get("toc", [])
    small_doc_pages = None
    if not toc:
        # 소형 문서(이미지·짧은 일반문서)는 ToC 없이 전체 페이지를 Vision으로 분석
        small_doc_pages = _resolve_target_pages_without_toc(total_pages)
        if small_doc_pages is None:
            doc.close()
            yield _sse_event("error", content="목차(ToC)가 없는 문서입니다. 먼저 ToC를 추출해주세요.")
            yield await ctx.finish()
            return

    # 섹션 범위 계산 (ToC 기반으로 정확한 섹션 끝 찾기)
    section_start, section_end = _find_section_page_range(toc, ctx.coarse_pages, total_pages)
    section_size = section_end - section_start + 1

    # ─── Step 2: 텍스트 기반 정밀 탐색 (Phase 2) ───
    if small_doc_pages is not None:
        # ToC 없는 소형 문서: 페이지 선택 단계를 건너뛰고 전체 페이지를 분석
        target_pages = small_doc_pages
        yield ctx.reasoning(f"[전체 분석] 목차 없는 소형 문서({total_pages}페이지)로 판단되어 전체 페이지를 분석합니다.")
    elif section_size > 3:
        yield ctx.reasoning(f"[세부 탐색] '{ctx.coarse_title}' 섹션(p.{section_start}~{section_end})의 텍스트를 분석하여 정확한 페이지를 찾고 있습니다...")

        # C-3: 비동기 호출
        phase2_result = await _refine_pages_with_text(doc, section_start, section_end, ctx.question)
        target_pages = phase2_result.get("target_pages", ctx.coarse_pages)
        refined_title = phase2_result.get("section_title", ctx.coarse_title)
        refined_reasoning = phase2_result.get("reasoning", "")

        yield ctx.reasoning(f"[세부 탐색] '{refined_title}' → 타겟 페이지 {target_pages}\n{refined_reasoning}")
    else:
        # 섹션이 작으면 Phase 1 결과를 그대로 사용
        target_pages = ctx.coarse_pages

    # ─── Step 4: 미니 PDF 추출 + 참조 이미지 생성 ───
    yield ctx.reasoning(f"페이지 {target_pages}에서 미니 PDF를 추출하고 있습니다...")

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
                    document_id=str(ctx.document_id),
                    document_name=ctx.selected_doc_filename,
                )
                ctx.collected_references.append({"page_number": page_num})
            except Exception as e:
                logger.error(f"❌ [Pipeline] Thumbnail generation error for page {page_idx}: {e}")

        doc.close()

    except Exception as e:
        doc.close()
        logger.error(f"❌ [Pipeline] PDF 처리 및 참조 이미지 생성 실패: {e}", exc_info=True)
        yield _sse_event("error", content=f"PDF 처리 중 오류: {str(e)}")
        yield await ctx.finish()
        return

    # ─── Step 5: Vision LLM 분석 (스트리밍) + B-1 Fallback ───
    yield ctx.reasoning("Gemini Vision으로 페이지를 분석하고 있습니다...")

    try:
        async for chunk in analyze_pages_with_vision(mini_pdf_bytes, ctx.question, chat_history=ctx.chat_history):
            yield ctx.add_answer(chunk)
    except Exception as e:
        logger.error(f"❌ [Pipeline] Vision 분석 3회 재시도 모두 실패: {e}", exc_info=True)

        # B-1 Fallback: Vision 실패 시 텍스트 기반 답변 생성
        yield ctx.reasoning("⚠️ Vision 분석이 실패하여 텍스트 기반으로 답변을 생성합니다...")
        try:
            fallback_answer = await _generate_text_fallback(pdf_path, target_pages, ctx.question, ctx.chat_history)
            yield ctx.add_answer(fallback_answer)
        except Exception as fb_err:
            logger.error(f"❌ [Pipeline] 텍스트 Fallback도 실패: {fb_err}", exc_info=True)
            yield _sse_event("error", content=f"Vision 분석 및 텍스트 분석 모두 실패: {str(e)}")

    logger.info("🏁 [Pipeline] Agentic Search 파이프라인 처리 완료")
    yield await ctx.finish()


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
    Agentic Search 파이프라인을 실행합니다 (stage orchestrator).

    3단계 하이브리드 구조:
    Phase 1: 메타데이터 기반 문서 선택 (Flash-Lite, ToC 제외)
    Phase 1-2: ToC 전체 기반 타겟 페이지 추론 (Flash-Lite, 텍스트)
    Phase 2: 섹션 전체 텍스트 분석 → 정확한 타겟 페이지 특정 (Flash-Lite, 텍스트)
    Phase 3: 타겟 페이지 미니 PDF 분석 → 답변 스트리밍 (Flash-Lite, PDF)
    """
    logger.info(f"🚀 [Pipeline] Agentic Search 파이프라인 작동 시작 (질문: '{question}')")

    ctx = _PipelineContext(
        document_id=document_id,
        question=question,
        chat_history=chat_history,
        image=image,
        user_email=user_email,
        session_id=session_id,
        previous_reference=previous_reference,
    )

    try:
        # Step -1: 이미지 분석 (있을 때만, document_id/question 보강)
        async for ev in _stage_image_analysis(ctx):
            yield ev

        # C-1: 규칙 기반 빠른 일상대화 판별 → Early Exit
        async for ev in _stage_quick_general(ctx):
            yield ev
        if ctx.done:
            return

        # 문서 선택 + 1차 페이지 선택 (Early Exit: 문서없음/일상대화/되묻기/미발견)
        async for ev in _stage_resolve_document(ctx):
            yield ev
        if ctx.done:
            return

        # PDF 열기 → Phase 2 정밀 → 미니 PDF/참조 → Vision 답변
        async for ev in _stage_answer(ctx):
            yield ev

    except GeneratorExit:
        logger.info("🛑 [Pipeline] 클라이언트 중단 요청 → 파이프라인 조기 종료")
        return
    except Exception as e:
        logger.error(f"❌ [Pipeline] 예상치 못한 오류: {e}", exc_info=True)
        yield _sse_event("error", content=f"시스템 오류: {str(e)}")
        yield await ctx.finish()


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
