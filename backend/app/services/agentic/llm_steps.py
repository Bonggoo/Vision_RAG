"""파이프라인 각 단계의 LLM 호출.

호출 → JSON 파싱 → 검증 → 실패 시 폴백이라는 동일한 골격을 세 단계가 공유하므로
`_invoke_json` 으로 묶고, 각 단계는 프롬프트 조립과 결과 검증만 담당한다.
"""
import json
import re

import fitz  # PyMuPDF
from langchain_core.messages import HumanMessage

from app.prompts import (
    general_chat_prompt,
    refine_pages_prompt,
    select_document_prompt,
    select_pages_prompt,
    text_fallback_prompt,
)
from app.services.agent_service import (
    _clean_json_response,
    _create_flash_llm,
    _extract_text_content,
)
from app.utils.logger import logger

from .toc import normalize_page

# ─── 상한값 ──────────────────────────────────────────────────────────────────
RECENT_HISTORY_TURNS = 4          # 프롬프트에 실을 최근 대화 턴 수
HISTORY_MESSAGE_CHARS = 200       # 대화 이력 메시지당 최대 길이
MAX_REFINED_PAGES = 3             # Phase 2가 반환할 타겟 페이지 상한
MAX_COARSE_PAGES = 5              # Phase 1-2가 반환할 타겟 페이지 상한
MAX_TOC_CANDIDATES = 3            # 프론트에 노출할 ToC 후보 상한
MAX_SUGGESTED_QUESTIONS = 5       # LLM 보강 질문 상한
PHASE2_MAX_SCAN_PAGES = 200       # Phase 2에서 텍스트를 긁을 최대 페이지 수
FALLBACK_TEXT_CHARS = 8000        # 텍스트 폴백 프롬프트에 실을 본문 최대 길이
DEFAULT_CONFIDENCE = 0.5

# 보강 질문이 원 질문 주제를 이어받았는지 볼 때 무시할 범용어
GENERIC_QUESTION_WORDS = {
    "설명", "방법", "해결", "해결법", "알려줘", "알려", "어떻게", "무엇", "뭐야",
    "확인", "관련", "대해", "대한", "관해", "내용", "정보", "질문", "매뉴얼", "문서",
}


def format_chat_context(chat_history: list[dict] | None) -> str:
    """최근 대화 이력을 프롬프트에 넣을 문자열로 만듭니다 (없으면 빈 문자열)."""
    if not chat_history:
        return ""
    lines = [
        f"{'사용자' if item['role'] == 'user' else 'AI'}: {item['content'][:HISTORY_MESSAGE_CHARS]}"
        for item in chat_history[-RECENT_HISTORY_TURNS:]
    ]
    return "\n이전 대화 맥락:\n" + "\n".join(lines) + "\n"


async def _invoke_json(prompt: str) -> dict:
    """Flash-Lite LLM 을 호출하고 응답 JSON 을 dict 로 파싱합니다.

    실패는 호출부가 단계별 폴백을 결정할 수 있도록 예외로 전파합니다.
    """
    llm = _create_flash_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return json.loads(_clean_json_response(response.content))


# ─── Phase 1: 문서 선택 ──────────────────────────────────────────────────────

def _build_document_summaries(documents: list[dict], toc_evidence: dict | None) -> str:
    """문서 메타데이터 요약 블록을 만듭니다.

    ToC 전체는 제외해 토큰을 아끼되(~2,500 토큰), 질문 키워드와 겹친 ToC 제목만
    해당 문서에 한 줄 덧붙입니다 — 'SMATV'처럼 문서 제목에는 없고 목차에만 있는
    단서로 문서를 골라야 하는 질문에 대응하기 위함.
    """
    summaries = []
    for i, doc in enumerate(documents):
        summary = (
            f"[문서 {i + 1}]\n"
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
        summaries.append(summary)
    return "\n\n".join(summaries)


def _validate_candidates(raw_candidates, documents: list[dict]) -> list[dict]:
    """LLM 이 돌려준 후보 중 실제 존재하는 document_id 만 남기고 confidence 순 정렬."""
    valid_ids = {d["document_id"] for d in documents}
    validated = [
        {
            "document_id": c["document_id"],
            "confidence": float(c.get("confidence", DEFAULT_CONFIDENCE)),
            "reason": str(c.get("reason", "")),
        }
        for c in raw_candidates
        if isinstance(c, dict) and c.get("document_id") in valid_ids
    ]
    if not validated:
        validated = [
            {
                "document_id": documents[0]["document_id"],
                "confidence": DEFAULT_CONFIDENCE,
                "reason": "기본 선택",
            }
        ]
    validated.sort(key=lambda x: x["confidence"], reverse=True)
    return validated


def _question_keywords(question: str) -> set[str]:
    """질문에서 '주제'를 대표하는 핵심어를 뽑습니다.

    조사/서술어와 "설명", "방법" 류의 범용어는 어느 질문에나 붙을 수 있어 제외합니다.
    """
    tokens = re.findall(r"[0-9]+|[가-힣]+|[A-Za-z]+", question)
    return {t.upper() for t in tokens if len(t) >= 2 and t not in GENERIC_QUESTION_WORDS}


def _reflects_question(suggested: list[str], question: str) -> bool:
    """보강 질문들이 실제로 사용자의 질문 주제를 이어받았는지 확인합니다.

    Flash-Lite 가 프롬프트의 JSON 예시 문장을 그대로 베껴,
    사용자가 묻지도 않은 주제(예: "통신 에러 타임아웃")를 추천해 버리는 사고가 있었습니다.
    핵심어가 하나도 살아남지 않은 항목이 있으면 전체를 폐기하고,
    호출부가 후보 문서 기준 기본 보강 질문으로 대체하게 합니다.
    """
    keywords = _question_keywords(question)
    if not keywords:
        return True  # 대조할 핵심어가 없으면 판단 불가 → 통과
    return all(
        any(kw in s.upper() for kw in keywords)
        for s in suggested
    )


async def select_document(
    question: str,
    documents: list[dict],
    chat_history: list[dict] | None = None,
    previous_reference: dict | None = None,
    toc_evidence: dict | None = None,
) -> dict:
    """Phase 1: 메타데이터만으로 문서 선택 + 일상대화 판별.

    Returns:
        {
            "classification": "general" | "technical",
            "candidates": [{"document_id", "confidence", "reason"}, ...],
            "needs_clarification": bool,
            "suggested_questions": [str, ...],
            "reasoning": str,
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
            "needs_clarification": False,
            "suggested_questions": [],
        }

    previous_reference_section = ""
    if previous_reference and previous_reference.get("document_name"):
        previous_reference_section = (
            f"\n이전에 참조한 문서: {previous_reference['document_name']} "
            f"(제조사: {previous_reference.get('manufacturer', '')})\n"
        )

    prompt = select_document_prompt(
        _build_document_summaries(documents, toc_evidence),
        format_chat_context(chat_history),
        previous_reference_section,
        question,
    )

    try:
        result = await _invoke_json(prompt)

        classification = str(result.get("classification", "technical")).lower().strip()
        result["classification"] = "general" if "general" in classification else "technical"

        if result["classification"] == "technical":
            result["candidates"] = _validate_candidates(result.get("candidates", []), documents)
            result["needs_clarification"] = bool(result.get("needs_clarification", False))
            raw_questions = result.get("suggested_questions", [])
            suggested = (
                [str(q) for q in raw_questions[:MAX_SUGGESTED_QUESTIONS]]
                if isinstance(raw_questions, list)
                else []
            )
            if suggested and not _reflects_question(suggested, question):
                logger.warning(
                    f"⚠️ [Phase 1] 질문과 무관한 보강 질문 폐기: {suggested}"
                )
                suggested = []
            result["suggested_questions"] = suggested
        else:
            result["candidates"] = []
            result["needs_clarification"] = False
            result["suggested_questions"] = []

        top_confidence = result["candidates"][0]["confidence"] if result["candidates"] else "N/A"
        logger.info(
            f"📊 [Phase 1] 문서 선택 결과: classification={result['classification']}, "
            f"needs_clarification={result['needs_clarification']}, "
            f"top_confidence={top_confidence}, "
            f"suggested_questions={len(result['suggested_questions'])}개"
        )
        return result

    except Exception as e:
        logger.error(f"❌ [Phase 1] Document Selection Error: {e}", exc_info=True)
        return {
            "classification": "technical",
            "candidates": [
                {
                    "document_id": documents[0]["document_id"],
                    "confidence": DEFAULT_CONFIDENCE,
                    "reason": f"오류 발생 기본 선택: {e}",
                }
            ],
            "reasoning": f"문서 선택 중 오류 발생: {e}",
            "needs_clarification": False,
            "suggested_questions": [],
        }


# ─── Phase 1-2: ToC 기반 페이지 선택 ─────────────────────────────────────────

async def select_pages(
    question: str,
    toc: list[dict],
    total_pages: int,
    previous_reference: dict | None = None,
) -> dict:
    """Phase 1-2: 선택된 문서의 ToC 전체(잘림 없음)로 타겟 페이지를 고릅니다.

    Returns:
        {"target_pages": [int], "section_title": str,
         "toc_candidates": [{"title", "page"}], "reasoning": str}
    """
    logger.info(f"🔍 [Phase 1-2] ToC 기반 페이지 선택 시작 (질문: {question[:50]}...)")

    previous_pages_section = ""
    ref_pages = (previous_reference or {}).get("referenced_pages")
    if ref_pages:
        previous_pages_section = (
            f"\n이전에 참조한 페이지: {ref_pages} (같은 맥락의 후속 질문일 수 있습니다)\n"
        )

    prompt = select_pages_prompt(
        json.dumps(toc, ensure_ascii=False), total_pages, previous_pages_section, question
    )

    try:
        result = await _invoke_json(prompt)

        result["target_pages"] = [
            normalize_page(p) for p in result.get("target_pages", [1])
        ][:MAX_COARSE_PAGES]

        result["toc_candidates"] = [
            {"title": str(c["title"]), "page": normalize_page(c.get("page", 1))}
            for c in result.get("toc_candidates", [])
            if isinstance(c, dict) and "title" in c
        ][:MAX_TOC_CANDIDATES]

        return result

    except Exception as e:
        logger.error(f"❌ [Phase 1-2] Page Selection Error: {e}", exc_info=True)
        return {
            "target_pages": [1],
            "section_title": "알 수 없음",
            "toc_candidates": [],
            "reasoning": f"페이지 추론 중 오류 발생: {e}",
        }


# ─── Phase 2: 섹션 텍스트 기반 정밀 탐색 ─────────────────────────────────────

async def refine_pages_with_text(
    doc: fitz.Document,
    section_start: int,
    section_end: int,
    question: str,
) -> dict:
    """Phase 2: 섹션 텍스트를 추출해 정확한 타겟 페이지를 특정합니다."""
    logger.info(f"🔍 [Phase 2] 정밀 텍스트 탐색 시작: p.{section_start}~{section_end}")

    scan_end = min(section_end, section_start + PHASE2_MAX_SCAN_PAGES - 1, doc.page_count)
    full_text = "\n".join(
        f"--- PAGE {idx + 1} ---\n{doc[idx].get_text()}\n"
        for idx in range(section_start - 1, scan_end)
    )

    try:
        result = await _invoke_json(refine_pages_prompt(question, full_text, section_start))

        # 정규화 후 스캔 범위 밖 페이지는 버린다 (LLM 환각 페이지 방지)
        pages = [normalize_page(p) for p in result.get("target_pages", [section_start])]
        pages = [p for p in pages if section_start <= p <= scan_end] or [section_start]
        result["target_pages"] = pages[:MAX_REFINED_PAGES]
        return result

    except Exception as e:
        logger.error(f"❌ [Phase 2] Text Refine Error: {e}", exc_info=True)
        return {
            "reasoning": f"세부 텍스트 분석 실패, 섹션 시작 페이지로 폴백: {e}",
            "target_pages": [section_start],
            "section_title": "알 수 없음",
        }


# ─── 답변 생성 ───────────────────────────────────────────────────────────────

async def generate_general_answer(question: str) -> str:
    """일상대화 답변을 생성합니다. 실패 시 예외를 그대로 올립니다."""
    llm = _create_flash_llm()
    response = await llm.ainvoke([HumanMessage(content=general_chat_prompt(question))])
    return _extract_text_content(response.content)


async def generate_text_fallback(
    pdf_path: str,
    target_pages: list[int],
    question: str,
    chat_history: list[dict] | None = None,
) -> str:
    """Vision 분석 실패 시 타겟 페이지의 텍스트만으로 답변을 생성합니다."""
    doc = fitz.open(pdf_path)
    try:
        full_text = "\n".join(
            f"--- PAGE {page_num} ---\n{doc[page_num - 1].get_text()}\n"
            for page_num in target_pages
            if 1 <= page_num <= doc.page_count
        )
    finally:
        doc.close()

    if not full_text.strip():
        return (
            "⚠️ 해당 페이지에서 텍스트를 추출할 수 없습니다. "
            "스캔된 PDF이거나 이미지 기반 문서일 수 있습니다."
        )

    prompt = text_fallback_prompt(
        format_chat_context(chat_history), question, full_text[:FALLBACK_TEXT_CHARS]
    )
    llm = _create_flash_llm()
    response = await llm.ainvoke([HumanMessage(content=prompt)])
    return _extract_text_content(response.content)
