"""
agentic_graph.py 순수 함수 단위 테스트.
외부 의존 없음 — GCS/Gemini 호출 없음.
"""
import json
import pytest
from unittest.mock import patch


# ─── 테스트 대상 import ─────────────────────────────────────────────────────
from app.services.agentic_graph import (
    _normalize_page,
    _find_section_page_range,
    _sse_event,
    _quick_classify,
    _generate_default_clarification_questions,
    _extract_model_codes,
    _strip_josa,
    _filter_documents_by_keywords,
)


# ─── _normalize_page ────────────────────────────────────────────────────────

class TestNormalizePage:
    def test_int_passthrough(self):
        assert _normalize_page(42) == 42

    def test_float_truncates(self):
        assert _normalize_page(3.9) == 3

    def test_string_integer(self):
        assert _normalize_page("32") == 32

    def test_chapter_page_format(self):
        # "3-32" → 32 (하이픈 뒤 숫자)
        assert _normalize_page("3-32") == 32

    def test_chapter_page_single_digit(self):
        assert _normalize_page("1-1") == 1

    def test_unknown_string_returns_one(self):
        assert _normalize_page("abc") == 1

    def test_empty_string_returns_one(self):
        assert _normalize_page("") == 1

    def test_none_returns_one(self):
        assert _normalize_page(None) == 1


# ─── _extract_model_codes ────────────────────────────────────────────────────

class TestExtractModelCodes:
    """질문/메타데이터에서 모델번호 토큰 추출 — 문서 선택 시 정확 일치 가중용."""

    def test_extracts_alphanumeric_model(self):
        # 한글 조사가 붙어도 정규식 경계에서 잘려 모델번호만 추출
        assert _extract_model_codes("F388A를 생산 라인에 설치") == {"f388a"}

    def test_extracts_hyphenated_model(self):
        assert _extract_model_codes("LS-R900의 고속 응답 모드") == {"ls-r900"}
        assert _extract_model_codes("CZ-V20 컬러 센서") == {"cz-v20"}

    def test_underscore_splits_token(self):
        # SV_MEMORY는 밑줄로 끊겨 제외되고, 실제 모델(L7NH)만 남음
        assert _extract_model_codes("SV_MEMORY 알람 L7NH 서보") == {"l7nh"}

    def test_alarm_code_excluded(self):
        # 'AL.20' — 점으로 끊겨 'AL'(숫자 없음)·'20'(문자 없음) 둘 다 탈락
        assert _extract_model_codes("AL.20 알람이 떠 있는데") == set()

    def test_two_char_token_excluded(self):
        # '2D' — 2자 이하는 제외 (오탐 방지)
        assert _extract_model_codes("GS1 2D 심볼과 선형 바코드") == {"gs1"}

    def test_pure_korean_returns_empty(self):
        assert _extract_model_codes("종단 저항은 별도로 부착해야 하나요") == set()

    def test_model_disambiguation_f388a_vs_f381(self):
        # 핵심 회귀 방어: 'F388A' 질문이 'F381' 문서로 새면 안 됨.
        q = _extract_model_codes("F388A의 최대 하중과 샘플링 속도는?")
        doc_388 = _extract_model_codes("유니펄스 F388A 웨이브 폼 체커 사용 설명서")
        doc_381 = _extract_model_codes("유니펄스 F381 취급설명서")
        assert q & doc_388 == {"f388a"}   # 정답 문서와는 정확 일치
        assert q & doc_381 == set()        # 유사 모델과는 매칭 안 됨


# ─── _strip_josa ─────────────────────────────────────────────────────────────

class TestStripJosa:
    def test_strips_common_particles(self):
        assert _strip_josa("색상의") == "색상"
        assert _strip_josa("설정값을") == "설정값"
        assert _strip_josa("센서가") == "센서"
        assert _strip_josa("라인에서") == "라인"

    def test_strips_longest_particle_first(self):
        # '차이만으로' → '차이만' + '으로'가 아니라 '차이' + '만으로'
        assert _strip_josa("차이만으로") == "차이"

    def test_protects_short_roots(self):
        # 어근이 2자 미만으로 남으면 떼지 않음 ('차이'의 '이'는 조사가 아니라 어근)
        assert _strip_josa("차이") == "차이"
        assert _strip_josa("회로") == "회로"
        assert _strip_josa("온도") == "온도"

    def test_ascii_untouched(self):
        assert _strip_josa("manual") == "manual"
        assert _strip_josa("f388a") == "f388a"


# ─── _filter_documents_by_keywords ───────────────────────────────────────────

class TestFilterDocuments:
    """1차 문서 필터 — 조사 스트리핑 + DF 컷 + 확신 게이트."""

    def _doc(self, doc_id, filename, toc_titles, model=None):
        return {
            "document_id": doc_id,
            "filename": filename,
            "manufacturer": "테스트",
            "model_series": model or "",
            "toc": [{"title": t, "page": i + 1} for i, t in enumerate(toc_titles)],
        }

    def _corpus(self):
        return [
            self._doc("servo", "LS 서보 드라이브 L7NH 사용 설명서",
                      ["설치 방법", "알람 코드", "파라미터 설정"], model="L7NH"),
            self._doc("vision", "키엔스 CV-X 비전 시스템 매뉴얼",
                      ["설치 방법", "카메라 설정", "화상 처리 도구"], model="CV-X"),
            self._doc("sensor", "키엔스 LR-W 화이트 스폿 광 센서 카탈로그",
                      ["색으로 판별", "검출 사례", "설치 방법"], model="LR-W"),
            self._doc("plc", "미쓰비시 MELSEC-Q 시리얼 통신 모듈",
                      ["버퍼 메모리", "프로토콜 설정", "설치 방법"], model="MELSEC-Q"),
        ]

    def test_josa_stripped_keyword_matches(self):
        # '색상의' → '색상'... 은 '색으로'와 안 붙지만, '판별하려면'이 아닌
        # 명시적 케이스: '서보의' → '서보'가 파일명 '서보 드라이브'에 매칭
        docs, mode, _ = _filter_documents_by_keywords("서보의 알람 원인", self._corpus())
        assert mode == "filtered"
        assert docs[0]["document_id"] == "servo"

    def test_df_cut_ignores_corpus_generic_words(self):
        # '설치 방법'은 4/4 문서 ToC에 있음(DF > 1/3) → 점수 기여 없음
        # → 남는 변별 키워드가 없어 전체 폴백
        docs, mode, _ = _filter_documents_by_keywords("설치 방법 알려줘", self._corpus())
        assert mode in ("fallback_none", "fallback_weak")
        assert len(docs) == 4

    def test_weak_evidence_falls_back_to_all(self):
        # ToC 우연 매칭 1~2점뿐이면(메타 직접 매칭 없음) 전체 문서 반환
        docs, mode, _ = _filter_documents_by_keywords("버퍼 메모리 읽기", self._corpus())
        if mode == "filtered":
            # 메타 매칭이 있으면 filtered여도 무방 — 이 경우 정답이 포함돼야 함
            assert any(d["document_id"] == "plc" for d in docs)
        else:
            assert len(docs) == 4

    def test_model_code_match_is_trusted(self):
        docs, mode, _ = _filter_documents_by_keywords("L7NH 알람 확인", self._corpus())
        assert mode == "filtered"
        assert docs[0]["document_id"] == "servo"

    def test_no_match_returns_all(self):
        docs, mode, _ = _filter_documents_by_keywords("김치찌개 끓이는 법", self._corpus())
        assert mode == "fallback_none"
        assert len(docs) == 4

    def test_never_returns_empty(self):
        for q in ["ㅁㄴㅇㄹ", "설정", "이 모델 나사산 규격", ""]:
            docs, _, _ = _filter_documents_by_keywords(q, self._corpus())
            assert len(docs) >= 1


class TestTocEvidence:
    """매칭된 ToC 제목 수집 — 목차에만 있는 단서를 문서 선택 LLM에 전달하기 위함.

    실측 배경: 'SMATV'처럼 문서 제목/모델명에는 없고 목차에만 있는 용어로
    질문하면, 발견이 점수로 뭉개져 전달 과정에서 증발 → 정답 문서가 후보에
    오르지 못했음 (NEO NETWORK 문서 5건 실패, 2026-07-13 500문항 평가).
    """

    def _corpus(self):
        return [
            {"document_id": "neo", "filename": "네오정보시스템 NEO NETWORK 제품군 통합 사용 설명서",
             "manufacturer": "네오정보시스템", "model_series": "NEO NETWORK",
             "toc": [{"title": "SMATV(광 송장비)", "page": 6},
                     {"title": "광방송장비(SMATV) (Product Lineup)", "page": 10},
                     {"title": "커플러 (Product Lineup)", "page": 10},
                     {"title": "무선랜 AP (Product Lineup)", "page": 8}]},
            {"document_id": "servo", "filename": "LS 서보 드라이브 L7NH 사용 설명서",
             "manufacturer": "LS", "model_series": "L7NH",
             "toc": [{"title": "설치 방법", "page": 1}, {"title": "알람 코드", "page": 2}]},
            {"document_id": "vision", "filename": "키엔스 CV-X 비전 시스템 매뉴얼",
             "manufacturer": "KEYENCE", "model_series": "CV-X",
             "toc": [{"title": "설치 방법", "page": 1}, {"title": "카메라 설정", "page": 3}]},
            {"document_id": "plc", "filename": "미쓰비시 MELSEC-Q 시리얼 통신 모듈",
             "manufacturer": "MITSUBISHI", "model_series": "MELSEC-Q",
             "toc": [{"title": "설치 방법", "page": 1}, {"title": "버퍼 메모리", "page": 5}]},
        ]

    def test_toc_only_term_collected_as_evidence(self):
        # 핵심 시나리오: 'SMATV'는 어느 문서 제목에도 없고 NEO 목차에만 있음.
        # 점수가 약해 폴백하더라도 evidence에는 매칭 제목이 살아있어야 한다.
        docs, mode, ev = _filter_documents_by_keywords("SMATV 광방송장비 라인업", self._corpus())
        assert "neo" in ev
        assert any("SMATV" in t for t in ev["neo"])
        # 다른 문서에는 쪽지가 붙지 않음
        assert "servo" not in ev and "vision" not in ev

    def test_generic_words_produce_no_evidence(self):
        # '설치 방법'은 여러 문서 목차에 있어 DF컷으로 제외 → 쪽지 남발 방지
        _, _, ev = _filter_documents_by_keywords("설치 방법 알려줘", self._corpus())
        assert ev == {}

    def test_no_match_no_evidence(self):
        _, _, ev = _filter_documents_by_keywords("김치찌개 끓이는 법", self._corpus())
        assert ev == {}

    def test_evidence_capped_per_doc(self):
        # 문서당 최대 8개 제한
        big = {"document_id": "big", "filename": "대형 매뉴얼", "manufacturer": "X",
               "model_series": "Y",
               "toc": [{"title": f"위빙모드 활용 {i}", "page": i} for i in range(1, 30)]}
        _, _, ev = _filter_documents_by_keywords("위빙모드 설정", [big] + self._corpus())
        assert len(ev.get("big", [])) <= 8


# ─── _find_section_page_range ────────────────────────────────────────────────

class TestFindSectionPageRange:
    def _toc(self, pages):
        return [{"title": f"Section {p}", "level": 1, "page": p} for p in pages]

    def test_empty_target_pages_returns_default(self):
        toc = self._toc([1, 10, 20, 30])
        start, end = _find_section_page_range(toc, [], total_pages=100)
        assert start == 1
        assert end == 50

    def test_finds_nearest_toc_entry_before_target(self):
        toc = self._toc([1, 10, 20, 30, 50])
        start, end = _find_section_page_range(toc, [25], total_pages=100)
        assert start == 20  # 25 이전 가장 가까운 항목

    def test_exact_match_on_toc_entry(self):
        toc = self._toc([1, 10, 20, 30])
        start, end = _find_section_page_range(toc, [20], total_pages=100)
        assert start == 20

    def test_end_capped_at_total_pages(self):
        toc = self._toc([1, 90])
        start, end = _find_section_page_range(toc, [91], total_pages=95)
        assert end == 95  # start+49=139 이지만 total_pages=95로 cap

    def test_range_max_50_pages(self):
        toc = self._toc([1, 10, 20])
        start, end = _find_section_page_range(toc, [15], total_pages=200)
        assert end - start <= 49

    def test_target_before_all_toc_entries(self):
        toc = self._toc([10, 20, 30])
        start, end = _find_section_page_range(toc, [5], total_pages=100)
        # toc에 5 이하 항목 없으면 target 자체를 start로
        assert start == 5

    def test_multiple_target_pages_uses_minimum(self):
        toc = self._toc([1, 10, 20, 30])
        start, end = _find_section_page_range(toc, [25, 28], total_pages=100)
        assert start == 20  # min([25, 28])=25, 25 이전 가장 가까운 항목=20


# ─── _sse_event ──────────────────────────────────────────────────────────────

class TestSseEvent:
    def test_event_format(self):
        result = _sse_event("answer", text="안녕하세요")
        assert result.startswith("data: ")
        assert result.endswith("\n\n")

    def test_event_contains_type(self):
        result = _sse_event("reasoning", text="탐색 중")
        payload = json.loads(result.removeprefix("data: ").strip())
        assert payload["type"] == "reasoning"
        assert payload["text"] == "탐색 중"

    def test_done_event(self):
        result = _sse_event("done")
        payload = json.loads(result.removeprefix("data: ").strip())
        assert payload["type"] == "done"

    def test_extra_kwargs_included(self):
        result = _sse_event("reference", page=5, image="base64data")
        payload = json.loads(result.removeprefix("data: ").strip())
        assert payload["page"] == 5
        assert payload["image"] == "base64data"


# ─── _quick_classify ────────────────────────────────────────────────────────

class TestQuickClassify:
    def test_greeting_short_korean(self):
        assert _quick_classify("안녕하세요") == "general"

    def test_greeting_english(self):
        assert _quick_classify("hello") == "general"

    def test_technical_error_keyword(self):
        assert _quick_classify("AL.10 에러가 발생했습니다") == "technical"

    def test_technical_alarm_keyword(self):
        assert _quick_classify("알람 코드 확인 방법") == "technical"

    def test_technical_parameter(self):
        assert _quick_classify("파라미터 설정값을 바꾸려면") == "technical"

    def test_ambiguous_returns_none(self):
        # LLM 판별이 필요한 모호한 질문
        assert _quick_classify("이 장비 사용 방법을 알려주세요") is None

    def test_long_greeting_is_not_general(self):
        # 20자 초과 → greeting 패턴 적용 안 됨
        assert _quick_classify("안녕하세요 저는 오늘 이 장비에 대해 여쭤보고 싶습니다") is None


# ─── _generate_default_clarification_questions ──────────────────────────────

class TestGenerateDefaultClarificationQuestions:
    def _docs(self):
        return [
            {"manufacturer": "MITSUBISHI", "model_series": "MELSERVO"},
            {"manufacturer": "FANUC", "model_series": "미상"},
            {"manufacturer": "미상", "model_series": "Q-Series"},
        ]

    def test_returns_at_most_3_questions(self):
        questions = _generate_default_clarification_questions("알람 확인", self._docs())
        assert len(questions) <= 3

    def test_user_perspective_rewrite(self):
        # 탭하면 사용자 메시지로 전송되므로, 원 질문 + 제조사/모델 재작성 형태여야 함
        questions = _generate_default_clarification_questions("알람 확인", self._docs())
        assert questions[0] == "MITSUBISHI MELSERVO 알람 확인"
        # 모든 질문이 원 질문을 포함해야 함 (AI가 사용자에게 묻는 문장 금지)
        assert all("알람 확인" in q for q in questions)
        assert not any(q.endswith("가요?") or q.endswith("나요?") for q in questions)

    def test_ignores_misang_values(self):
        questions = _generate_default_clarification_questions("알람", self._docs())
        combined = " ".join(questions)
        assert "미상" not in combined
        # 미상인 필드만 빼고 나머지는 활용: "FANUC 알람", "Q-Series 알람"
        assert "FANUC 알람" in questions
        assert "Q-Series 알람" in questions

    def test_dedupes_same_prefix(self):
        docs = [
            {"manufacturer": "LS산전", "model_series": "L7NH"},
            {"manufacturer": "LS산전", "model_series": "L7NH"},
        ]
        questions = _generate_default_clarification_questions("알람", docs)
        assert questions == ["LS산전 L7NH 알람"]

    def test_empty_docs(self):
        # 재작성할 근거가 없으면 빈 리스트 (프론트에서 추천 질문 섹션 숨김)
        questions = _generate_default_clarification_questions("알람", [])
        assert questions == []
