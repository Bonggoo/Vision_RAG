"""Agentic Search 파이프라인 오케스트레이터.

3단계 하이브리드 추론(텍스트 + PDF)으로 정확한 페이지를 찾아 답변합니다.
  Phase 1   : 메타데이터 기반 문서 선택 (Flash-Lite, ToC 제외)
  Phase 1-2 : ToC 전체 기반 1차 페이지 추론 (Flash-Lite, 텍스트)
  Phase 2   : 섹션 전체 텍스트 분석 → 정확한 타겟 페이지 특정 (Flash-Lite, 텍스트)
  Phase 3   : 타겟 페이지 미니 PDF → Vision 답변 스트리밍

각 stage 는 `PipelineContext` 를 공유하는 async generator 이며 SSE 문자열을 yield 합니다.
early exit 는 `ctx.finish()` 를 yield 하고 `ctx.done` 으로 orchestrator 에 알립니다.
"""
import base64
from typing import AsyncGenerator

import fitz  # PyMuPDF

from app.prompts import vision_source_section
from app.services.agent_service import analyze_pages_with_vision
from app.services.metadata_service import (
    get_all_documents_async,
    get_document_async,
    get_document_path_async,
)
from app.services.pdf_service import render_page_thumbnail
from app.utils.logger import logger

from .classification import quick_classify
from .context import PipelineContext
from .doc_filter import (
    build_default_clarification_questions,
    collect_identifiers,
    filter_documents_by_keywords,
    question_mentions_identifier,
)
from .llm_steps import (
    generate_general_answer,
    generate_text_fallback,
    refine_pages_with_text,
    select_document,
    select_pages,
)
from .toc import (
    build_breadcrumb,
    find_section_page_range,
    normalize_page,
    resolve_target_pages_without_toc,
)

# ─── 되묻기 임계값 ───────────────────────────────────────────────────────────
# 최상위 후보가 이보다 낮으면 확신이 없다고 본다.
CLARIFY_CONFIDENCE_THRESHOLD = 0.7
# 1·2위 후보 점수 차가 이보다 작으면 우열을 가리기 어렵다고 본다.
CLARIFY_CONFIDENCE_MARGIN = 0.2
# 되묻기 메뉴에 올릴 후보 수 (최소 이상이어야 되묻고, 최대까지만 노출)
MIN_CLARIFICATION_CANDIDATES = 2
MAX_CLARIFICATION_CANDIDATES = 5

# 섹션이 이 페이지 수 이하면 Phase 2 정밀 탐색을 건너뛰고 1차 결과를 그대로 쓴다.
SKIP_REFINE_SECTION_SIZE = 3

# 장비 이미지 인식 결과를 신뢰할 최소 confidence
IMAGE_MATCH_MIN_CONFIDENCE = 0.5

# 참조 페이지 썸네일 렌더링 DPI
THUMBNAIL_DPI = 150

GENERAL_FALLBACK_ANSWER = (
    "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요? "
    "매뉴얼 PDF를 업로드하신 뒤 관련 질문(예: 특정 에러 코드나 조치 방법)을 "
    "입력해 주시면 정확히 분석하여 답변해 드리겠습니다."
)


# ─── 일상대화 답변 ───────────────────────────────────────────────────────────

async def _emit_general_answer(ctx: PipelineContext, fallback: str):
    """일상대화 답변을 생성해 yield 합니다. 실패 시 전달된 폴백 문장을 사용합니다."""
    try:
        yield ctx.add_answer(await generate_general_answer(ctx.question))
    except Exception as e:
        logger.error(f"❌ [Pipeline] 일상대화 답변 생성 실패: {e}")
        yield ctx.add_answer(fallback)


# ─── Stage: 장비 이미지 분석 ─────────────────────────────────────────────────

def _match_document_by_device_info(
    documents: list[dict], manufacturer: str | None, model: str | None
) -> dict | None:
    """이미지에서 인식한 제조사/모델로 문서를 찾습니다.

    제조사+모델 동시 일치 → 모델만 → 제조사만 순으로 우선순위를 둡니다.
    """
    def _find(predicate) -> dict | None:
        return next((d for d in documents if predicate(d)), None)

    manuf_u = manufacturer.upper() if manufacturer else None
    model_u = model.upper() if model else None

    def doc_manuf(d):
        return str(d.get("manufacturer", "")).upper()

    def doc_model(d):
        return str(d.get("model_series", "")).upper()

    if manuf_u and model_u:
        matched = _find(lambda d: manuf_u in doc_manuf(d) and model_u in doc_model(d))
        if matched:
            return matched
    if model_u:
        matched = _find(lambda d: model_u in doc_model(d))
        if matched:
            return matched
    if manuf_u:
        return _find(lambda d: manuf_u in doc_manuf(d))
    return None


async def _stage_image_analysis(ctx: PipelineContext):
    """Step -1: 업로드된 장비 이미지를 분석해 document_id 를 보강하고 질문을 리라이팅합니다."""
    if not ctx.image:
        return

    yield ctx.reasoning("📸 업로드하신 장비 이미지를 분석하고 있습니다...")
    try:
        from app.services.agent_service import analyze_device_image_with_gemini

        meta = await analyze_device_image_with_gemini(ctx.image)
        if not meta or meta.get("confidence", 0.0) < IMAGE_MATCH_MIN_CONFIDENCE:
            yield ctx.reasoning(
                "⚠️ 이미지에서 명확한 장비 브랜드나 알람코드를 파악하지 못해 일반 RAG 모드로 계속합니다."
            )
            return

        manufacturer = meta.get("manufacturer")
        model = meta.get("model_series")
        error_code = meta.get("error_code")
        symptom = meta.get("symptom")

        info_parts = [
            f"{label}: {value}"
            for label, value in (
                ("제조사", manufacturer),
                ("모델", model),
                ("인식된 알람", error_code),
                ("증상", symptom),
            )
            if value
        ]
        yield ctx.reasoning("🔍 이미지 인식 성공!\n- " + "\n- ".join(info_parts))

        # document_id 가 지정되지 않았으면 인식 결과로 문서를 자동 매칭
        if ctx.document_id is None:
            all_docs = await get_all_documents_async(owner_email=ctx.user_email)
            matched = _match_document_by_device_info(all_docs, manufacturer, model)
            if matched:
                ctx.document_id = matched["document_id"]
                yield ctx.reasoning(
                    "📂 분석 정보를 기반으로 매칭된 매뉴얼을 자동으로 선택했습니다:\n"
                    f"- 파일명: {matched.get('filename')}"
                )

        # 질문 보강 (리라이팅)
        rewritten = [
            part
            for part in (
                manufacturer,
                model,
                f"알람코드 {error_code}" if error_code else None,
                symptom,
            )
            if part
        ]
        if rewritten:
            prefix = " ".join(rewritten)
            # 사용자 질문이 사실상 비어 있으면 알람 원인 질문으로 대체
            if len(ctx.question.strip()) < 5:
                ctx.question = f"{prefix} 원인과 조치 대처법"
            else:
                ctx.question = f"{prefix} 에러 상황: {ctx.question}"
            yield ctx.reasoning(f"⚙️ 질문 보강 완료: '{ctx.question}'")

    except Exception as e:
        logger.error(f"❌ [Pipeline] 이미지 전처리 실패: {e}")
        yield ctx.reasoning(f"⚠️ 이미지 분석 중 오류 발생, 일반 RAG 모드로 진행합니다. (오류: {e})")


# ─── Stage: 규칙 기반 일상대화 조기 응답 ─────────────────────────────────────

async def _stage_quick_general(ctx: PipelineContext):
    """규칙 기반 분류가 명확한 일상대화로 판단하면 LLM 라우팅 없이 즉시 답변합니다."""
    if quick_classify(ctx.question) != "general":
        return

    yield ctx.reasoning("일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다...")
    async for ev in _emit_general_answer(ctx, GENERAL_FALLBACK_ANSWER):
        yield ev
    yield await ctx.finish()


# ─── Stage: 문서 선택 ────────────────────────────────────────────────────────

def _find_carry_over_document(ctx: PipelineContext, all_docs: list[dict]) -> dict | None:
    """이전 참조 문서를 그대로 이어받을 수 있으면 그 문서를 반환합니다.

    새 질문에 '다른' 장비의 제조사/모델 식별자가 등장하면 맥락이 바뀐 것으로 보고
    이어받지 않습니다.
    """
    prev_ref = ctx.previous_reference
    if not (all_docs and len(all_docs) > 1 and prev_ref and prev_ref.get("document_id")):
        return None

    prev_doc_id = str(prev_ref["document_id"])
    other_identifiers = collect_identifiers(all_docs, exclude_document_id=prev_doc_id)
    if question_mentions_identifier(ctx.question, other_identifiers):
        return None

    return next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)


def _narrow_candidates(
    ctx: PipelineContext, all_docs: list[dict]
) -> tuple[list[dict], dict, str]:
    """1차 키워드 필터로 후보를 좁힙니다.

    반환: (LLM 에 넘길 문서 리스트, toc_evidence, 사용자에게 보여줄 reasoning 문구)
    """
    if len(all_docs) == 1:
        return all_docs, {}, f"📄 '{all_docs[0].get('filename', '')}' 문서에서 관련 페이지를 찾고 있습니다..."

    filtered, mode, toc_evidence = filter_documents_by_keywords(ctx.question, all_docs)

    if mode != "filtered":
        # 매칭 없음 또는 증거 미약 → 필터를 신뢰하지 않고 전체 문서를 LLM 에 전달
        logger.info(f"🔎 [ToC 키워드 필터] {mode} → 전체 {len(all_docs)}개 문서를 LLM에 전달")
        return all_docs, toc_evidence, f"📚 {len(all_docs)}개 문서 중 적합한 문서와 페이지를 찾고 있습니다..."

    # 이전 참조 문서는 후보군에서 소실되지 않도록 강제 포함
    prev_ref = ctx.previous_reference
    if prev_ref and prev_ref.get("document_id"):
        prev_doc_id = str(prev_ref["document_id"])
        if not any(str(d["document_id"]) == prev_doc_id for d in filtered):
            prev_doc = next((d for d in all_docs if str(d["document_id"]) == prev_doc_id), None)
            if prev_doc:
                filtered.append(prev_doc)
                logger.info(
                    f"🔎 [ToC 키워드 필터] 이전 참조 문서를 후보군에 강제 포함: {prev_doc.get('filename')}"
                )

    logger.info(f"🔎 [ToC 키워드 필터] {len(all_docs)}개 → {len(filtered)}개 문서로 필터링")
    return (
        filtered,
        toc_evidence,
        f"📚 {len(all_docs)}개 문서 중 목차 키워드 매칭으로 {len(filtered)}개 후보를 좁혔습니다...",
    )


def _should_ask_clarification(
    question: str, candidates: list[dict], doc_result: dict, all_docs: list[dict]
) -> bool:
    """되묻기가 필요한지 3중 체크로 판단합니다."""
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None

    # 체크 1: 최상위 confidence 가 낮거나, 1·2위 격차가 근소
    confidence_unclear = top["confidence"] < CLARIFY_CONFIDENCE_THRESHOLD or (
        second is not None
        and top["confidence"] - second["confidence"] < CLARIFY_CONFIDENCE_MARGIN
    )

    # 체크 2: LLM 이 직접 되묻기가 필요하다고 판단
    llm_says_clarify = bool(doc_result.get("needs_clarification", False))

    # 체크 3: 문서가 여러 개인데 질문에 제조사/모델 식별자가 전혀 없음
    no_identifier = len(all_docs) > 1 and not question_mentions_identifier(
        question, collect_identifiers(all_docs)
    )

    logger.info(
        f"🔍 [되묻기 판단] confidence_unclear={confidence_unclear}, "
        f"llm_says_clarify={llm_says_clarify}, no_identifier={no_identifier}"
    )
    return confidence_unclear or llm_says_clarify or no_identifier


def _build_clarification_menu(
    candidates: list[dict], all_docs: list[dict], docs_for_selection: list[dict]
) -> list[dict]:
    """되묻기 화면에 노출할 문서 후보 카드를 만듭니다.

    LLM 후보를 우선 담고, 2개 미만이면 관련도 상위 문서로 보강합니다.
    LLM 이 후보를 1개만 반환해도 질문에 식별자가 없으면 사용자가 고를 수 있도록
    선택지를 제공하기 위함입니다 (후보 1개일 때 되묻기를 건너뛰고 확신에 찬
    오답을 내던 문제의 대응).
    """
    menu: list[dict] = []
    seen: set = set()

    def add(doc_meta: dict | None, confidence: float) -> None:
        if not doc_meta or doc_meta["document_id"] in seen:
            return
        seen.add(doc_meta["document_id"])
        menu.append(
            {
                "document_id": doc_meta["document_id"],
                "title": doc_meta.get("filename", "알 수 없음"),
                "manufacturer": doc_meta.get("manufacturer", "미상"),
                "model_series": doc_meta.get("model_series", "미상"),
                "confidence": confidence,
            }
        )

    for c in candidates[:MAX_CLARIFICATION_CANDIDATES]:
        add(next((d for d in all_docs if d["document_id"] == c["document_id"]), None), c["confidence"])

    if len(menu) < MIN_CLARIFICATION_CANDIDATES:
        for d in docs_for_selection:
            if len(menu) >= MAX_CLARIFICATION_CANDIDATES:
                break
            add(d, 0.0)

    return menu


async def _emit_coarse_pages(ctx: PipelineContext, toc: list[dict], total_pages: int, label: str):
    """Phase 1-2 를 실행하고 결과를 ctx 에 저장한 뒤 reasoning 을 yield 합니다."""
    page_result = await select_pages(
        ctx.question, toc, total_pages, ctx.previous_reference, ctx.chat_history
    )
    ctx.coarse_pages = page_result.get("target_pages", [1])
    ctx.coarse_title = page_result.get("section_title", "")
    yield ctx.reasoning(
        f"{label} → '{ctx.coarse_title}' (p.{ctx.coarse_pages})\n{page_result.get('reasoning', '')}"
    )


async def _stage_resolve_document(ctx: PipelineContext):
    """문서 선택(또는 맥락 유지)과 ToC 기반 1차 페이지 선택을 수행합니다.

    결과는 ctx.document_id / selected_doc_filename / coarse_pages / coarse_title 에 저장됩니다.
    early exit(문서 없음 / 일상대화 / 되묻기 / 문서 미발견) 시 ctx.finish() 를 yield 합니다.
    """
    all_docs: list[dict] = []

    if ctx.document_id is None:
        # 문서 목록은 이 stage 안에서 한 번만 조회해 재사용한다
        # (이전에는 맥락 유지 분기와 문서 선택 분기가 각각 조회해 매 질문마다 왕복이 2회였음)
        all_docs = await get_all_documents_async(owner_email=ctx.user_email)

        carried_over = _find_carry_over_document(ctx, all_docs)
        if carried_over:
            ctx.document_id = str(carried_over["document_id"])
            yield ctx.reasoning(
                f"🔄 이전 대화 맥락을 이어받아 '{carried_over.get('filename')}' 문서에서 검색을 계속합니다."
            )

    # ─── 문서가 여전히 미지정: 필터 → LLM 선택 → (필요 시) 되묻기 ───
    if ctx.document_id is None:
        if not all_docs:
            yield ctx.error("업로드된 문서가 없습니다. 먼저 PDF 매뉴얼을 업로드해 주세요.")
            yield await ctx.finish()
            return

        docs_for_selection, toc_evidence, narrow_message = _narrow_candidates(ctx, all_docs)
        yield ctx.reasoning(narrow_message)

        doc_result = await select_document(
            ctx.question,
            docs_for_selection,
            ctx.chat_history,
            ctx.previous_reference,
            toc_evidence=toc_evidence,
        )

        if doc_result["classification"] == "general":
            yield ctx.reasoning("일상적 대화로 판별되어 일반 에이전트 모드로 답변을 생성합니다...")
            async for ev in _emit_general_answer(
                ctx, "안녕하세요! Vision RAG 에이전트입니다. 무엇을 도와드릴까요?"
            ):
                yield ev
            yield await ctx.finish()
            return

        candidates = doc_result.get("candidates", [])
        if candidates:
            needs_clarification = _should_ask_clarification(
                ctx.question, candidates, doc_result, all_docs
            )
            menu = _build_clarification_menu(candidates, all_docs, docs_for_selection)

            # 관련 문서가 실제로 1개뿐이면 모호함이 없으므로 그대로 답변한다
            if needs_clarification and len(menu) >= MIN_CLARIFICATION_CANDIDATES:
                # LLM 이 보강 질문을 만들지 못했으면 화면에 함께 뜨는 후보 기준으로 생성
                suggested = doc_result.get("suggested_questions") or (
                    build_default_clarification_questions(ctx.question, menu)
                )
                yield ctx.clarification(
                    "질문을 좀 더 구체화하면 정확한 답변을 드릴 수 있어요. "
                    "아래에서 질문을 선택하거나, 해당 매뉴얼을 직접 선택해 주세요.",
                    menu,
                    suggested,
                )
                yield await ctx.finish()
                return

            ctx.document_id = candidates[0]["document_id"]
        else:
            ctx.document_id = all_docs[0]["document_id"]

        selected_doc = next(
            (d for d in all_docs if d["document_id"] == ctx.document_id), all_docs[0]
        )
        ctx.selected_doc_filename = selected_doc.get("filename", "")
        yield ctx.reasoning(
            f"📄 '{ctx.selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다..."
        )
        async for ev in _emit_coarse_pages(
            ctx,
            selected_doc.get("toc", []),
            selected_doc.get("total_pages", 0),
            f"📄 '{ctx.selected_doc_filename}'",
        ):
            yield ev
        return

    # ─── 문서가 지정됨 (사용자 지정 또는 맥락 유지): 페이지 선택만 수행 ───
    meta = await get_document_async(ctx.document_id, owner_email=ctx.user_email)
    if meta is None:
        yield ctx.error(f"문서를 찾을 수 없습니다: {ctx.document_id}")
        yield await ctx.finish()
        return

    ctx.selected_doc_filename = meta.get("filename", "")
    yield ctx.reasoning(f"📄 '{ctx.selected_doc_filename}' 문서에서 관련 페이지를 찾고 있습니다...")
    async for ev in _emit_coarse_pages(
        ctx, meta.get("toc", []), meta.get("total_pages", 0), "📄"
    ):
        yield ev


# ─── Stage: 답변 생성 ────────────────────────────────────────────────────────

def _dedupe_page_indices(target_pages: list[int], total_pages: int) -> list[int]:
    """타겟 페이지를 0-indexed 로 바꾸고 범위 밖/중복을 제거합니다 (원래 순서 유지)."""
    indices: list[int] = []
    for p in target_pages:
        idx = normalize_page(p) - 1
        if 0 <= idx < total_pages and idx not in indices:
            indices.append(idx)
    return indices or [0]


def _build_mini_pdf(doc: fitz.Document, page_indices: list[int]) -> bytes:
    """타겟 페이지만 골라 담은 미니 PDF 를 만듭니다.

    비연속 페이지(예: p.12, p.115)가 잡혔을 때 min~max 사이를 전부 넣으면 PDF 가
    비대해지므로, 필요한 페이지만 sparse 하게 삽입해 Vision 토큰을 아낍니다.
    """
    mini_doc = fitz.open()
    try:
        for page_idx in sorted(page_indices):
            mini_doc.insert_pdf(doc, from_page=page_idx, to_page=page_idx)
        return mini_doc.tobytes()
    finally:
        mini_doc.close()


async def _refine_target_pages(ctx: PipelineContext, doc: fitz.Document, toc: list[dict]):
    """Phase 2 정밀 탐색을 수행하고 최종 타겟 페이지를 ctx.coarse_pages 에 반영합니다."""
    total_pages = doc.page_count
    section_start, section_end = find_section_page_range(toc, ctx.coarse_pages, total_pages)
    if section_end - section_start + 1 <= SKIP_REFINE_SECTION_SIZE:
        # 섹션이 이미 충분히 좁으면 Phase 1 결과를 그대로 사용
        return

    yield ctx.reasoning(
        f"[세부 탐색] '{ctx.coarse_title}' 섹션(p.{section_start}~{section_end})의 "
        "텍스트를 분석하여 정확한 페이지를 찾고 있습니다..."
    )
    refined = await refine_pages_with_text(doc, section_start, section_end, ctx.question)
    ctx.coarse_pages = refined.get("target_pages", ctx.coarse_pages)
    yield ctx.reasoning(
        f"[세부 탐색] '{refined.get('section_title', ctx.coarse_title)}' → "
        f"타겟 페이지 {ctx.coarse_pages}\n{refined.get('reasoning', '')}"
    )


async def _stage_answer(ctx: PipelineContext):
    """PDF 열기 → Phase 2 정밀 탐색 → 미니 PDF/참조 이미지 → Vision 답변."""
    meta = await get_document_async(ctx.document_id, owner_email=ctx.user_email)
    if meta is None:
        yield ctx.error(f"문서를 찾을 수 없습니다: {ctx.document_id}")
        yield await ctx.finish()
        return

    pdf_path = await get_document_path_async(ctx.document_id, owner_email=ctx.user_email)
    if pdf_path is None:
        yield ctx.error("PDF 파일을 찾을 수 없습니다.")
        yield await ctx.finish()
        return

    try:
        doc = fitz.open(pdf_path)
    except Exception as e:
        logger.error(f"❌ [Pipeline] PDF 파일 열기 실패 ({pdf_path}): {e}", exc_info=True)
        yield ctx.error(f"PDF 파일 열기 실패: {e}")
        yield await ctx.finish()
        return

    # PDF 를 여는 데 성공했으면 어떤 경로로 빠져나가든 반드시 닫는다
    try:
        toc = meta.get("toc", [])
        if toc:
            async for ev in _refine_target_pages(ctx, doc, toc):
                yield ev
        else:
            # 소형 문서(이미지·짧은 일반문서)는 ToC 없이 전체 페이지를 Vision 으로 분석
            small_doc_pages = resolve_target_pages_without_toc(doc.page_count)
            if small_doc_pages is None:
                yield ctx.error("목차(ToC)가 없는 문서입니다. 먼저 ToC를 추출해주세요.")
                yield await ctx.finish()
                return
            ctx.coarse_pages = small_doc_pages
            yield ctx.reasoning(
                f"[전체 분석] 목차 없는 소형 문서({doc.page_count}페이지)로 판단되어 "
                "전체 페이지를 분석합니다."
            )

        yield ctx.reasoning(f"페이지 {ctx.coarse_pages}에서 미니 PDF를 추출하고 있습니다...")

        page_indices = _dedupe_page_indices(ctx.coarse_pages, doc.page_count)
        try:
            mini_pdf_bytes = _build_mini_pdf(doc, page_indices)
        except Exception as e:
            logger.error(f"❌ [Pipeline] 미니 PDF 생성 실패: {e}", exc_info=True)
            yield ctx.error(f"PDF 처리 중 오류: {e}")
            yield await ctx.finish()
            return

        # 참조 페이지 썸네일 송출 (개별 실패는 건너뛰고 계속)
        for page_idx in page_indices:
            try:
                png_bytes = render_page_thumbnail(doc, page_idx, dpi=THUMBNAIL_DPI)
                encoded = base64.b64encode(png_bytes).decode("utf-8")
                yield ctx.reference(page_idx + 1, f"data:image/png;base64,{encoded}")
            except Exception as e:
                logger.error(f"❌ [Pipeline] p.{page_idx + 1} 썸네일 생성 실패: {e}")
    finally:
        doc.close()

    # ─── Vision 분석 (스트리밍) + 텍스트 폴백 ───
    # 첨부 페이지가 문서 어디에서 왔는지(ToC 계층 + 원문 페이지)를 함께 알려 준다.
    # ToC 는 업로드 시 추출해 둔 것이라 LLM 추가 호출이 없다.
    source_pages = [idx + 1 for idx in page_indices]
    source_section = vision_source_section(
        meta.get("filename", ""),
        build_breadcrumb(meta.get("toc", []), min(source_pages)),
        source_pages,
    )

    yield ctx.reasoning("Gemini Vision으로 페이지를 분석하고 있습니다...")
    try:
        async for chunk in analyze_pages_with_vision(
            mini_pdf_bytes,
            ctx.question,
            chat_history=ctx.chat_history,
            source_section=source_section,
        ):
            yield ctx.add_answer(chunk)
    except Exception as e:
        logger.error(f"❌ [Pipeline] Vision 분석 재시도 모두 실패: {e}", exc_info=True)
        yield ctx.reasoning("⚠️ Vision 분석이 실패하여 텍스트 기반으로 답변을 생성합니다...")
        try:
            yield ctx.add_answer(
                await generate_text_fallback(
                    pdf_path, ctx.coarse_pages, ctx.question, ctx.chat_history
                )
            )
        except Exception as fb_err:
            logger.error(f"❌ [Pipeline] 텍스트 Fallback 도 실패: {fb_err}", exc_info=True)
            yield ctx.error(f"Vision 분석 및 텍스트 분석 모두 실패: {e}")

    logger.info("🏁 [Pipeline] Agentic Search 파이프라인 처리 완료")
    yield await ctx.finish()


# ─── Orchestrator ───────────────────────────────────────────────────────────

async def run_agentic_pipeline(
    document_id: str | None,
    question: str,
    chat_history: list[dict] | None = None,
    image: str | None = None,
    user_email: str | None = None,
    session_id: str | None = None,
    previous_reference: dict | None = None,
) -> AsyncGenerator[str, None]:
    """Agentic Search 파이프라인을 실행하고 SSE 이벤트를 순서대로 흘려보냅니다."""
    logger.info(f"🚀 [Pipeline] Agentic Search 파이프라인 작동 시작 (질문: '{question}')")

    ctx = PipelineContext(
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

        # 규칙 기반 빠른 일상대화 판별 → Early Exit
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
        yield ctx.error(f"시스템 오류: {e}")
        yield await ctx.finish()
