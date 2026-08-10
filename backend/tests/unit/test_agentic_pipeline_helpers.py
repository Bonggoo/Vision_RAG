"""
파이프라인 헬퍼 순수 함수 단위 테스트.

기존에는 이 로직들이 235줄짜리 async generator(_stage_resolve_document) 안에
인라인으로 들어 있어 테스트가 불가능했다. 함수로 추출하면서 함께 붙인 테스트.
외부 의존 없음 — GCS/Gemini 호출 없음.
"""
import pytest

from app.services.agentic.context import PipelineContext
from app.services.agentic.doc_filter import (
    collect_identifiers,
    question_mentions_identifier,
)
from app.prompts import (
    HISTORY_MESSAGE_CHARS,
    RECENT_HISTORY_MESSAGES,
    vision_history_section,
)
from app.services.agentic.llm_steps import format_chat_context
from app.services.agentic.pipeline import (
    MAX_CLARIFICATION_CANDIDATES,
    _build_clarification_menu,
    _dedupe_page_indices,
    _find_carry_over_document,
    _match_document_by_device_info,
    _narrow_candidates,
    _should_ask_clarification,
)


def make_doc(doc_id, filename="doc.pdf", manufacturer="미상", model="미상", toc=None, pages=100):
    return {
        "document_id": doc_id,
        "filename": filename,
        "manufacturer": manufacturer,
        "model_series": model,
        "toc": toc or [],
        "total_pages": pages,
    }


def make_ctx(question="질문", previous_reference=None, document_id=None):
    return PipelineContext(
        document_id=document_id,
        question=question,
        chat_history=None,
        image=None,
        user_email="a@b.c",
        session_id=None,
        previous_reference=previous_reference,
    )


# ─── collect_identifiers ────────────────────────────────────────────────────

class TestCollectIdentifiers:
    def test_collects_full_string_and_word_parts(self):
        docs = [make_doc("1", manufacturer="Mitsubishi Electric", model="MELSEC-Q")]
        assert collect_identifiers(docs) == {"MITSUBISHI ELECTRIC", "MITSUBISHI", "ELECTRIC", "MELSEC-Q"}

    def test_skips_unknown_placeholder(self):
        docs = [make_doc("1", manufacturer="미상", model="미상")]
        assert collect_identifiers(docs) == set()

    def test_skips_single_char_parts(self):
        # 한 글자 조각('A')은 오탐이 심해 제외되고, 전체 문자열만 남는다
        docs = [make_doc("1", manufacturer="A Corp", model="미상")]
        assert collect_identifiers(docs) == {"A CORP", "CORP"}

    def test_exclude_document_id(self):
        docs = [
            make_doc("keep", manufacturer="LS", model="XGT"),
            make_doc("drop", manufacturer="OMRON", model="CJ2"),
        ]
        result = collect_identifiers(docs, exclude_document_id="drop")
        assert "OMRON" not in result
        assert "LS" in result

    def test_empty_documents(self):
        assert collect_identifiers([]) == set()


class TestQuestionMentionsIdentifier:
    def test_case_insensitive_match(self):
        assert question_mentions_identifier("미쓰비시 melsec-q 알람", {"MELSEC-Q"}) is True

    def test_no_match(self):
        assert question_mentions_identifier("배터리 교체 주기", {"MELSEC-Q"}) is False

    def test_empty_identifier_set_is_false(self):
        assert question_mentions_identifier("아무 질문", set()) is False


# ─── format_chat_context ────────────────────────────────────────────────────

class TestFormatChatContext:
    def test_none_returns_empty_string(self):
        assert format_chat_context(None) == ""
        assert format_chat_context([]) == ""

    def test_labels_roles_in_korean(self):
        result = format_chat_context([
            {"role": "user", "content": "안녕"},
            {"role": "assistant", "content": "반가워요"},
        ])
        assert "사용자: 안녕" in result
        assert "AI: 반가워요" in result

    def test_keeps_only_recent_turns(self):
        history = [{"role": "user", "content": f"메시지{i}"} for i in range(10)]
        result = format_chat_context(history)
        assert "메시지9" in result
        assert "메시지0" not in result

    def test_truncates_long_message(self):
        result = format_chat_context([{"role": "user", "content": "가" * 500}])
        assert "가" * HISTORY_MESSAGE_CHARS in result
        assert "가" * (HISTORY_MESSAGE_CHARS + 1) not in result

    def test_limits_match_what_frontend_sends(self):
        """절단 상한은 프론트 전송량(6개 메시지 × 300자)과 같아야 한다.

        더 작으면 이미 받아 둔 맥락을 백엔드가 스스로 버리게 된다
        (예전 문서선택 단계가 4개·200자로 잘라 Vision 과 서로 달랐다).
        """
        assert (RECENT_HISTORY_MESSAGES, HISTORY_MESSAGE_CHARS) == (6, 300)

    def test_vision_shares_the_same_truncation(self):
        """Vision 블록도 같은 규칙을 쓰되 후속 질문 지시만 덧붙는다."""
        history = [{"role": "user", "content": "가" * 500}]
        assert format_chat_context(history).rstrip() in vision_history_section(history)
        assert "후속 질문" in vision_history_section(history)
        assert vision_history_section(None) == ""


# ─── _dedupe_page_indices ───────────────────────────────────────────────────

class TestDedupePageIndices:
    def test_converts_to_zero_indexed(self):
        assert _dedupe_page_indices([1, 5, 10], total_pages=100) == [0, 4, 9]

    def test_removes_duplicates_preserving_order(self):
        assert _dedupe_page_indices([7, 3, 7, 3], total_pages=100) == [6, 2]

    def test_drops_out_of_range(self):
        assert _dedupe_page_indices([0, 1, 500], total_pages=10) == [0]

    def test_empty_falls_back_to_first_page(self):
        assert _dedupe_page_indices([], total_pages=10) == [0]

    def test_all_invalid_falls_back_to_first_page(self):
        assert _dedupe_page_indices([999, 1000], total_pages=10) == [0]


# ─── _match_document_by_device_info ─────────────────────────────────────────

class TestMatchDocumentByDeviceInfo:
    docs = [
        make_doc("a", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", manufacturer="LS ELECTRIC", model="XGT"),
        make_doc("c", manufacturer="MITSUBISHI", model="FR-A800"),
    ]

    def test_manufacturer_and_model_wins(self):
        matched = _match_document_by_device_info(self.docs, "Mitsubishi", "FR-A800")
        assert matched["document_id"] == "c"

    def test_model_only_match(self):
        matched = _match_document_by_device_info(self.docs, None, "XGT")
        assert matched["document_id"] == "b"

    def test_manufacturer_only_falls_back_to_first(self):
        matched = _match_document_by_device_info(self.docs, "MITSUBISHI", None)
        assert matched["document_id"] == "a"

    def test_model_takes_priority_over_manufacturer(self):
        # 제조사는 안 맞지만 모델이 맞으면 모델 매칭이 이긴다
        matched = _match_document_by_device_info(self.docs, "UNKNOWN-CO", "XGT")
        assert matched["document_id"] == "b"

    def test_no_match_returns_none(self):
        assert _match_document_by_device_info(self.docs, "SIEMENS", "S7") is None

    def test_both_none_returns_none(self):
        assert _match_document_by_device_info(self.docs, None, None) is None


# ─── _should_ask_clarification ──────────────────────────────────────────────

class TestShouldAskClarification:
    # 질문에 식별자가 있어야 '체크 3'이 발동하지 않는다
    docs = [
        make_doc("a", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("b", manufacturer="LS", model="XGT"),
    ]
    question_with_identifier = "MITSUBISHI MELSEC-Q 알람 2051"

    def test_high_confidence_with_identifier_does_not_clarify(self):
        candidates = [{"confidence": 0.95}, {"confidence": 0.2}]
        assert _should_ask_clarification(
            self.question_with_identifier, candidates, {}, self.docs
        ) is False

    def test_low_top_confidence_clarifies(self):
        candidates = [{"confidence": 0.6}]
        assert _should_ask_clarification(
            self.question_with_identifier, candidates, {}, self.docs
        ) is True

    def test_narrow_margin_clarifies(self):
        candidates = [{"confidence": 0.9}, {"confidence": 0.85}]
        assert _should_ask_clarification(
            self.question_with_identifier, candidates, {}, self.docs
        ) is True

    def test_llm_flag_clarifies(self):
        candidates = [{"confidence": 0.95}, {"confidence": 0.1}]
        doc_result = {"needs_clarification": True}
        assert _should_ask_clarification(
            self.question_with_identifier, candidates, doc_result, self.docs
        ) is True

    def test_missing_identifier_clarifies(self):
        candidates = [{"confidence": 0.95}, {"confidence": 0.1}]
        assert _should_ask_clarification("알람 2051 원인", candidates, {}, self.docs) is True

    def test_single_document_ignores_identifier_check(self):
        one_doc = [make_doc("a", manufacturer="MITSUBISHI", model="MELSEC-Q")]
        candidates = [{"confidence": 0.95}]
        assert _should_ask_clarification("알람 2051 원인", candidates, {}, one_doc) is False


# ─── _build_clarification_menu ──────────────────────────────────────────────

class TestBuildClarificationMenu:
    def test_maps_metadata_into_cards(self):
        docs = [make_doc("a", filename="Q매뉴얼.pdf", manufacturer="MITSUBISHI", model="MELSEC-Q")]
        menu = _build_clarification_menu([{"document_id": "a", "confidence": 0.8}], docs, docs)
        assert menu == [
            {
                "document_id": "a",
                "title": "Q매뉴얼.pdf",
                "manufacturer": "MITSUBISHI",
                "model_series": "MELSEC-Q",
                "confidence": 0.8,
            }
        ]

    def test_pads_when_llm_returns_single_candidate(self):
        """후보가 1개면 되묻기를 건너뛰고 확신에 찬 오답을 내던 버그의 회귀 테스트."""
        docs = [make_doc(str(i)) for i in range(4)]
        menu = _build_clarification_menu([{"document_id": "0", "confidence": 0.6}], docs, docs)
        assert len(menu) >= 2
        assert menu[0]["document_id"] == "0"
        assert menu[0]["confidence"] == 0.6
        assert menu[1]["confidence"] == 0.0  # 보강된 후보

    def test_deduplicates(self):
        docs = [make_doc("a"), make_doc("b")]
        candidates = [{"document_id": "a", "confidence": 0.9}, {"document_id": "a", "confidence": 0.4}]
        menu = _build_clarification_menu(candidates, docs, docs)
        assert [m["document_id"] for m in menu] == ["a", "b"]

    def test_respects_max_candidates(self):
        docs = [make_doc(str(i)) for i in range(20)]
        candidates = [{"document_id": str(i), "confidence": 0.5} for i in range(20)]
        menu = _build_clarification_menu(candidates, docs, docs)
        assert len(menu) == MAX_CLARIFICATION_CANDIDATES

    def test_unknown_candidate_id_is_skipped(self):
        docs = [make_doc("a")]
        candidates = [{"document_id": "ghost", "confidence": 0.9}]
        menu = _build_clarification_menu(candidates, docs, docs)
        assert [m["document_id"] for m in menu] == ["a"]  # 보강으로만 채워짐


# ─── _find_carry_over_document ──────────────────────────────────────────────

class TestFindCarryOverDocument:
    docs = [
        make_doc("prev", manufacturer="MITSUBISHI", model="MELSEC-Q"),
        make_doc("other", manufacturer="LS ELECTRIC", model="XGT"),
    ]

    def test_carries_over_when_no_other_identifier(self):
        ctx = make_ctx("2050은 뭐야?", previous_reference={"document_id": "prev"})
        assert _find_carry_over_document(ctx, self.docs)["document_id"] == "prev"

    def test_does_not_carry_over_when_other_device_mentioned(self):
        ctx = make_ctx("XGT 알람은?", previous_reference={"document_id": "prev"})
        assert _find_carry_over_document(ctx, self.docs) is None

    def test_no_previous_reference(self):
        assert _find_carry_over_document(make_ctx("질문"), self.docs) is None

    def test_single_document_corpus_skips(self):
        ctx = make_ctx("질문", previous_reference={"document_id": "prev"})
        assert _find_carry_over_document(ctx, [self.docs[0]]) is None

    def test_stale_previous_reference_returns_none(self):
        ctx = make_ctx("질문", previous_reference={"document_id": "deleted-doc"})
        assert _find_carry_over_document(ctx, self.docs) is None


# ─── _narrow_candidates ─────────────────────────────────────────────────────

class TestNarrowCandidates:
    def test_single_document_shortcut(self):
        docs = [make_doc("a", filename="유일.pdf")]
        selected, evidence, message = _narrow_candidates(make_ctx("아무 질문"), docs)
        assert selected == docs
        assert evidence == {}
        assert "유일.pdf" in message

    def test_previous_reference_is_force_included(self):
        """필터가 이전 참조 문서를 떨어뜨려도 후보군에 다시 넣는지."""
        docs = [
            make_doc(f"d{i}", filename=f"무관{i}.pdf", manufacturer=f"MFG{i}", model=f"M{i}")
            for i in range(6)
        ]
        docs.append(make_doc("target", filename="F388A 서보 매뉴얼.pdf", manufacturer="LS", model="F388A"))
        docs.append(make_doc("prev", filename="이전문서.pdf", manufacturer="OMRON", model="CJ2"))

        ctx = make_ctx("F388A 알람 코드", previous_reference={"document_id": "prev"})
        selected, _, _ = _narrow_candidates(ctx, docs)

        ids = [d["document_id"] for d in selected]
        assert ids[0] == "target"          # 모델번호 정확 일치가 최상위
        assert "prev" in ids               # 이전 참조 문서 강제 포함

    def test_no_match_returns_all_documents(self):
        docs = [make_doc(f"d{i}", filename=f"문서{i}.pdf") for i in range(5)]
        selected, _, message = _narrow_candidates(make_ctx("zzzz존재하지않는키워드"), docs)
        assert len(selected) == len(docs)
        assert "5개 문서 중 적합한" in message
