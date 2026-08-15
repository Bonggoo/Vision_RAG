"""
파이프라인 전체 흐름 스모크 테스트.

LLM/GCS 를 전부 모킹하고 run_agentic_pipeline 을 끝까지 돌려, 각 분기가
기대한 SSE 이벤트 순서를 내는지 확인한다. stage 분해 리팩토링 과정에서
early exit 경로가 끊기는 것을 잡기 위한 안전망.
"""
import asyncio
import json

import fitz
import pytest

from app.services.agentic import pipeline as pl


# ─── 헬퍼 ────────────────────────────────────────────────────────────────────

def parse_events(chunks: list[str]) -> list[dict]:
    """SSE 문자열 목록을 이벤트 dict 목록으로 변환."""
    return [json.loads(c.removeprefix("data: ").strip()) for c in chunks]


def event_types(events: list[dict]) -> list[str]:
    return [e["type"] for e in events]


def collect(gen) -> list[dict]:
    """async generator 를 끝까지 소비해 이벤트 목록으로 만든다.

    레포 컨벤션에 맞춰 pytest-asyncio 없이 asyncio.run 으로 처리한다.
    """
    async def _drain():
        return [chunk async for chunk in gen]

    return parse_events(asyncio.run(_drain()))


def make_doc(doc_id="d1", filename="매뉴얼.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q", toc=None):
    return {
        "document_id": doc_id,
        "filename": filename,
        "manufacturer": manufacturer,
        "model_series": model,
        "toc": toc if toc is not None else [{"level": 1, "title": "알람 목록", "page": 10}],
        "total_pages": 120,
    }


@pytest.fixture
def sample_pdf(tmp_path):
    """20페이지짜리 빈 PDF 를 만들어 경로를 돌려준다."""
    path = tmp_path / "sample.pdf"
    doc = fitz.open()
    for i in range(20):
        page = doc.new_page()
        page.insert_text((72, 72), f"page {i + 1} content")
    doc.save(path)
    doc.close()
    return str(path)


@pytest.fixture
def stub_answer_path(monkeypatch, sample_pdf):
    """답변 단계(_stage_answer)의 외부 의존을 전부 모킹한다."""
    monkeypatch.setattr(pl, "get_document_path_async", _async_return(sample_pdf))
    monkeypatch.setattr(pl, "render_page_thumbnail", lambda doc, idx, dpi=150: b"\x89PNG-fake")

    async def fake_vision(*args, **kwargs):
        yield "답변 "
        yield "본문입니다."

    monkeypatch.setattr(pl, "analyze_pages_with_vision", fake_vision)
    monkeypatch.setattr(
        pl,
        "refine_pages_with_text",
        _async_return({"target_pages": [12], "section_title": "알람 목록", "reasoning": "정밀 탐색"}),
    )
    return sample_pdf


def _async_return(value):
    async def _fn(*args, **kwargs):
        return value
    return _fn


# ─── 일상대화 조기 종료 ──────────────────────────────────────────────────────

def test_greeting_exits_before_document_lookup(monkeypatch):
    """규칙 기반 분류가 인사말을 잡아내면 문서 조회 없이 바로 답변하고 끝난다."""
    monkeypatch.setattr(pl, "generate_general_answer", _async_return("안녕하세요!"))

    def _boom(*args, **kwargs):
        raise AssertionError("일상대화 분기에서 문서를 조회하면 안 된다")

    monkeypatch.setattr(pl, "get_all_documents_async", _boom)

    events = collect(pl.run_agentic_pipeline(None, "안녕하세요"))

    assert event_types(events) == ["reasoning", "answer", "done"]
    assert events[1]["content"] == "안녕하세요!"


def test_general_answer_falls_back_when_llm_fails(monkeypatch):
    """일상대화 LLM 이 죽어도 폴백 문장으로 답한다."""
    async def _fail(*args, **kwargs):
        raise RuntimeError("LLM down")

    monkeypatch.setattr(pl, "generate_general_answer", _fail)
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return([]))

    events = collect(pl.run_agentic_pipeline(None, "안녕"))

    assert event_types(events) == ["reasoning", "answer", "done"]
    assert events[1]["content"] == pl.GENERAL_FALLBACK_ANSWER


# ─── 문서 없음 ───────────────────────────────────────────────────────────────

def test_no_documents_returns_error(monkeypatch):
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return([]))

    events = collect(pl.run_agentic_pipeline(None, "서보 알람 2051 원인"))

    assert event_types(events) == ["error", "done"]
    assert "업로드된 문서가 없습니다" in events[0]["content"]


# ─── 되묻기 ──────────────────────────────────────────────────────────────────

def test_ambiguous_question_asks_clarification(monkeypatch):
    """식별자 없는 모호한 질문이면 후보 카드를 띄우고 조기 종료한다."""
    docs = [
        make_doc("a", filename="Q매뉴얼.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", filename="XGT매뉴얼.pdf", manufacturer="LS", model="XGT"),
    ]
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return(docs))
    monkeypatch.setattr(
        pl,
        "select_document",
        _async_return({
            "classification": "technical",
            "candidates": [
                {"document_id": "a", "confidence": 0.55, "reason": ""},
                {"document_id": "b", "confidence": 0.45, "reason": ""},
            ],
            "needs_clarification": True,
            "suggested_questions": [],
        }),
    )

    events = collect(pl.run_agentic_pipeline(None, "알람 코드 원인이 뭐야"))

    assert event_types(events)[-2:] == ["clarification", "done"]
    clarification = events[-2]
    assert len(clarification["candidates"]) == 2
    # LLM 이 보강 질문을 안 줬으므로 후보 기준 기본 질문이 생성된다
    assert clarification["suggested_questions"]
    assert all("알람 코드 원인이 뭐야" in q for q in clarification["suggested_questions"])


def test_unrelated_question_reports_no_match(monkeypatch):
    """보유하지 않은 장비를 물으면 되묻기가 아니라 '못 찾음'으로 끝낸다.

    회귀 배경: "다이치 메뉴얼"(보유 없는 제조사)에 대해 되묻기 카드가 뜨면서
    "미쓰비시 MELSEC-Q 시리즈 다이치 메뉴얼" 같은 보강 질문이 생성돼,
    존재하지 않는 매뉴얼이 있는 것처럼 보였다.
    """
    docs = [
        make_doc("a", filename="Q매뉴얼.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", filename="XGT매뉴얼.pdf", manufacturer="LS", model="XGT"),
    ]
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return(docs))
    monkeypatch.setattr(
        pl,
        "select_document",
        _async_return({
            "classification": "technical",
            "candidates": [
                {"document_id": "a", "confidence": 0.1, "reason": ""},
                {"document_id": "b", "confidence": 0.05, "reason": ""},
            ],
            "needs_clarification": True,
            "suggested_questions": ["MITSUBISHI MELSEC-Q 시리즈 다이치 메뉴얼"],
        }),
    )

    events = collect(pl.run_agentic_pipeline(None, "다이치 메뉴얼"))

    assert event_types(events)[-2:] == ["clarification", "done"]
    clarification = events[-2]
    assert clarification["mode"] == "no_match"
    assert clarification["suggested_questions"] == []
    assert "찾지 못했습니다" in clarification["content"]
    # 직접 고를 수 있도록 문서 목록 자체는 남긴다
    assert len(clarification["candidates"]) == 2


def test_unrelated_question_drops_suggestions_even_if_llm_is_confident(monkeypatch):
    """LLM 이 confidence 를 높게 줘 미발견 분기를 비껴가도 보강 질문은 폐기한다."""
    docs = [
        make_doc("a", filename="Q매뉴얼.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", filename="XGT매뉴얼.pdf", manufacturer="LS", model="XGT"),
    ]
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return(docs))
    monkeypatch.setattr(
        pl,
        "select_document",
        _async_return({
            "classification": "technical",
            "candidates": [
                {"document_id": "a", "confidence": 0.5, "reason": ""},
                {"document_id": "b", "confidence": 0.45, "reason": ""},
            ],
            "needs_clarification": True,
            "suggested_questions": ["MITSUBISHI MELSEC-Q 시리즈 다이치 매뉴얼"],
        }),
    )

    events = collect(pl.run_agentic_pipeline(None, "다이치 매뉴얼"))

    clarification = events[-2]
    assert clarification["type"] == "clarification"
    assert clarification["mode"] == "ambiguous"
    assert clarification["suggested_questions"] == []


def test_confident_question_skips_clarification(monkeypatch, stub_answer_path):
    """식별자가 명확하고 confidence 가 높으면 되묻지 않고 바로 답변한다."""
    docs = [
        make_doc("a", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", manufacturer="LS", model="XGT"),
    ]
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return(docs))
    monkeypatch.setattr(pl, "get_document_async", _async_return(docs[0]))
    monkeypatch.setattr(
        pl,
        "select_document",
        _async_return({
            "classification": "technical",
            "candidates": [
                {"document_id": "a", "confidence": 0.95, "reason": ""},
                {"document_id": "b", "confidence": 0.05, "reason": ""},
            ],
            "needs_clarification": False,
            "suggested_questions": [],
        }),
    )
    monkeypatch.setattr(
        pl,
        "select_pages",
        _async_return({"target_pages": [10], "section_title": "알람 목록", "reasoning": "ToC 매칭"}),
    )

    events = collect(pl.run_agentic_pipeline(None, "MITSUBISHI MELSEC-Q 알람 2051 원인"))

    types = event_types(events)
    assert "clarification" not in types
    assert "reference" in types
    assert types[-1] == "done"
    assert "".join(e["content"] for e in events if e["type"] == "answer") == "답변 본문입니다."


# ─── 문서 지정 경로 ──────────────────────────────────────────────────────────

def test_explicit_document_skips_selection(monkeypatch, stub_answer_path):
    """document_id 가 주어지면 문서 목록 조회/선택 LLM 을 아예 타지 않는다."""
    doc = make_doc("a")
    monkeypatch.setattr(pl, "get_document_async", _async_return(doc))
    monkeypatch.setattr(
        pl,
        "select_pages",
        _async_return({"target_pages": [10], "section_title": "알람 목록", "reasoning": ""}),
    )

    def _boom(*args, **kwargs):
        raise AssertionError("document_id 지정 시 전체 문서를 조회하면 안 된다")

    monkeypatch.setattr(pl, "get_all_documents_async", _boom)
    monkeypatch.setattr(pl, "select_document", _boom)

    events = collect(pl.run_agentic_pipeline("a", "알람 2051 원인"))

    assert event_types(events)[-1] == "done"
    assert "reference" in event_types(events)


def test_missing_document_returns_error(monkeypatch):
    monkeypatch.setattr(pl, "get_document_async", _async_return(None))
    events = collect(pl.run_agentic_pipeline("ghost", "알람 2051 원인"))
    assert event_types(events) == ["error", "done"]
    assert "찾을 수 없습니다" in events[0]["content"]


# ─── ToC 없는 문서 ───────────────────────────────────────────────────────────

def test_large_document_without_toc_errors(monkeypatch, stub_answer_path):
    """ToC 가 없고 소형 문서도 아니면(20p) 안내 에러를 내고 종료한다."""
    doc = make_doc("a", toc=[])
    monkeypatch.setattr(pl, "get_document_async", _async_return(doc))
    monkeypatch.setattr(
        pl, "select_pages", _async_return({"target_pages": [1], "section_title": "", "reasoning": ""})
    )

    events = collect(pl.run_agentic_pipeline("a", "알람 2051 원인"))

    assert event_types(events)[-2:] == ["error", "done"]
    assert "목차(ToC)가 없는 문서" in events[-2]["content"]


# ─── Vision 실패 → 텍스트 폴백 ───────────────────────────────────────────────

def test_vision_failure_falls_back_to_text(monkeypatch, stub_answer_path):
    doc = make_doc("a")
    monkeypatch.setattr(pl, "get_document_async", _async_return(doc))
    monkeypatch.setattr(
        pl, "select_pages", _async_return({"target_pages": [10], "section_title": "", "reasoning": ""})
    )

    async def _vision_dies(*args, **kwargs):
        raise RuntimeError("vision quota")
        yield  # pragma: no cover — async generator 로 만들기 위한 장식

    monkeypatch.setattr(pl, "analyze_pages_with_vision", _vision_dies)
    monkeypatch.setattr(pl, "generate_text_fallback", _async_return("텍스트 폴백 답변"))

    events = collect(pl.run_agentic_pipeline("a", "알람 2051 원인"))

    answers = [e["content"] for e in events if e["type"] == "answer"]
    assert answers == ["텍스트 폴백 답변"]
    assert event_types(events)[-1] == "done"


# ─── 맥락 유지 ───────────────────────────────────────────────────────────────

def test_carries_over_previous_document(monkeypatch, stub_answer_path):
    """짧은 후속 질문이면 이전 참조 문서를 이어받고 문서 선택 LLM 을 건너뛴다."""
    docs = [
        make_doc("prev", filename="이전.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("other", filename="다른.pdf", manufacturer="LS", model="XGT"),
    ]
    monkeypatch.setattr(pl, "get_all_documents_async", _async_return(docs))
    monkeypatch.setattr(pl, "get_document_async", _async_return(docs[0]))
    monkeypatch.setattr(
        pl, "select_pages", _async_return({"target_pages": [10], "section_title": "", "reasoning": ""})
    )

    def _boom(*args, **kwargs):
        raise AssertionError("맥락 유지 시 문서 선택 LLM 을 호출하면 안 된다")

    monkeypatch.setattr(pl, "select_document", _boom)

    events = collect(
        pl.run_agentic_pipeline(None, "2050은?", previous_reference={"document_id": "prev"})
    )

    assert any("이전 대화 맥락을 이어받아" in e.get("content", "") for e in events)
    assert event_types(events)[-1] == "done"
