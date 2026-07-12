"""dedup_service.py 순수 함수 단위 테스트.

근접 중복 감지 — 진짜 중복(재추출본·제조사 표기만 다른 문서)은 잡고,
정당한 별권(기본편/응용편)이나 다른 모델은 오탐하지 않아야 한다.
"""
from app.services.dedup_service import (
    document_fingerprint,
    similarity,
    find_similar_documents,
)


def _doc(doc_id, filename, titles, pages=100, model=None):
    return {
        "document_id": doc_id,
        "filename": filename,
        "total_pages": pages,
        "model_series": model,
        "status": "indexed",
        "toc": [{"level": 1, "title": t, "page": i + 1} for i, t in enumerate(titles)],
    }


class TestFingerprint:
    def test_toc_titles_become_tokens(self):
        fp = document_fingerprint(_doc("a", "f", ["에러 코드 목록", "설치 방법"]))
        assert "에러" in fp and "설치" in fp

    def test_falls_back_to_filename_when_no_toc(self):
        fp = document_fingerprint({"filename": "키엔스 CV-X 매뉴얼", "toc": []})
        assert "키엔스" in fp and "cv" in fp

    def test_short_tokens_dropped(self):
        # 1글자 토큰 제외
        assert "a" not in document_fingerprint({"filename": "a bb ccc", "toc": []})


class TestSimilarity:
    def test_identical_toc_is_one(self):
        titles = ["개요", "설치", "배선", "알람 코드", "유지보수"]
        assert similarity(_doc("a", "x", titles), _doc("b", "y", titles)) == 1.0

    def test_disjoint_toc_is_zero(self):
        a = _doc("a", "x", ["압력 설정", "누설 판정"])
        b = _doc("b", "y", ["초점 조정", "조명 각도"])
        assert similarity(a, b) == 0.0

    def test_manufacturer_spelling_ignored(self):
        # ToC 제목이 같으면 제조사 표기('미쓰비시'/'미쓰비시전기') 차이는 무관
        titles = ["개요", "심플모션 파라미터", "위치결정 데이터"]
        a = _doc("a", "미쓰비시 QD77MS 매뉴얼", titles)
        b = _doc("b", "미쓰비시전기 QD77MS 매뉴얼", titles)
        assert similarity(a, b) == 1.0


class TestFindSimilar:
    def test_flags_near_duplicate(self):
        titles = ["개요", "설치", "배선", "알람", "보수"]
        new = _doc("new", "CV-X 매뉴얼", titles)
        existing = [_doc("old", "CV-X 매뉴얼 (재추출)", titles)]
        hits = find_similar_documents(new, existing)
        assert len(hits) == 1
        assert hits[0]["document_id"] == "old"
        assert hits[0]["reason"] == "toc"
        assert hits[0]["score"] == 1.0

    def test_different_volumes_not_flagged(self):
        # 기본편/응용편: 목차 내용이 실제로 다르면 중복 아님
        basic = _doc("b", "시리얼 통신 (기본편)", ["개요", "초기 설정", "기본 통신"])
        applied = _doc("a", "시리얼 통신 (응용편)", ["고급 프로토콜", "예제 프로그램", "트러블슈팅"])
        assert find_similar_documents(basic, [applied]) == []

    def test_excludes_self(self):
        titles = ["개요", "설치"]
        d = _doc("same", "x", titles)
        assert find_similar_documents(d, [d]) == []

    def test_skips_analyzing_and_error_docs(self):
        titles = ["개요", "설치", "배선"]
        new = _doc("new", "x", titles)
        pending = _doc("p", "x", titles); pending["status"] = "analyzing"
        broken = _doc("e", "x", titles); broken["status"] = "error"
        assert find_similar_documents(new, [pending, broken]) == []

    def test_same_model_different_doc_type_not_flagged(self):
        # 오탐 방지: 같은 model_series + 같은 페이지지만 ToC가 다른(카탈로그 vs
        # 설정가이드) 두 문서는 중복이 아니다. 둘 다 ToC가 있으면 metadata 규칙 미적용.
        catalog = _doc("c", "CZ-V20 카탈로그", ["제품 사양", "라인업", "옵션"], pages=6, model="CZ-V20")
        guide = _doc("g", "CZ-V20 설정 가이드", ["초기 설정", "티칭 절차", "임계값 조정"], pages=6, model="CZ-V20")
        assert find_similar_documents(catalog, [guide]) == []

    def test_metadata_fallback_for_scanned_docs(self):
        # ToC가 없는 스캔 문서 두 개: 같은 model_series + 페이지 근접이면 감지
        new = {"document_id": "n", "filename": "스캔본", "toc": [],
               "model_series": "LR-Z", "total_pages": 16, "status": "indexed"}
        old = {"document_id": "o", "filename": "스캔본2", "toc": [],
               "model_series": "LR-Z", "total_pages": 17, "status": "indexed"}
        hits = find_similar_documents(new, [old])
        assert len(hits) == 1 and hits[0]["reason"] == "metadata"

    def test_sorted_by_score_desc(self):
        titles = ["개요", "설치", "배선", "알람", "보수", "사양"]
        new = _doc("new", "x", titles)
        near = _doc("near", "x", titles)                    # 1.0
        partial = _doc("partial", "x", titles[:3] + ["기타1", "기타2", "기타3"])  # 부분
        hits = find_similar_documents(new, [partial, near], threshold=0.2)
        assert [h["document_id"] for h in hits] == ["near", "partial"]
