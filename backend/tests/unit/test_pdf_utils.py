"""
pdf_service.py 순수 함수 단위 테스트.
fitz.Document 의존 함수는 제외 — GCS/LLM 없이 검증 가능한 함수만.
"""
import pytest
from app.services.pdf_service import normalize_manufacturer, is_toc_meaningful


# ─── normalize_manufacturer ─────────────────────────────────────────────────

class TestNormalizeManufacturer:
    @pytest.mark.parametrize("input_name, expected", [
        ("mitsubishi", "MITSUBISHI"),
        ("MITSUBISHI", "MITSUBISHI"),
        ("미쯔비시", "MITSUBISHI"),
        ("미쓰비시", "MITSUBISHI"),
        ("fanuc", "FANUC"),
        ("화낙", "FANUC"),
        ("파낙", "FANUC"),
        ("keyence", "KEYENCE"),
        ("키엔스", "KEYENCE"),
        ("yaskawa", "YASKAWA"),
        ("야스카와", "YASKAWA"),
        ("omron", "OMRON"),
        ("오므론", "OMRON"),
        ("siemens", "SIEMENS"),
        ("지멘스", "SIEMENS"),
    ])
    def test_known_manufacturers(self, input_name, expected):
        assert normalize_manufacturer(input_name) == expected

    def test_none_returns_none(self):
        assert normalize_manufacturer(None) is None

    def test_empty_string_returns_none(self):
        assert normalize_manufacturer("") is None

    def test_unknown_ascii_uppercases(self):
        # 한글 없는 알 수 없는 제조사 → 대문자화
        result = normalize_manufacturer("Schunk")
        assert result == "SCHUNK"

    def test_strips_whitespace(self):
        assert normalize_manufacturer("  fanuc  ") == "FANUC"


# ─── is_toc_meaningful ──────────────────────────────────────────────────────

class TestIsTocMeaningful:
    def _entry(self, level=1, page=1):
        return {"title": "Section", "level": level, "page": page}

    def test_empty_toc_is_not_meaningful(self):
        assert is_toc_meaningful([], total_pages=100) is False

    def test_short_toc_with_only_level1_not_meaningful(self):
        # 서브레벨 없고 20개 미만 → False
        toc = [self._entry(level=1, page=i) for i in range(10)]
        assert is_toc_meaningful(toc, total_pages=50) is False

    def test_toc_with_sublevels_is_meaningful(self):
        toc = [self._entry(level=1)] * 5 + [self._entry(level=2)] * 5
        assert is_toc_meaningful(toc, total_pages=50) is True

    def test_toc_with_20_plus_level1_is_meaningful(self):
        toc = [self._entry(level=1, page=i) for i in range(20)]
        assert is_toc_meaningful(toc, total_pages=50) is True

    def test_large_doc_too_sparse(self):
        # 200페이지인데 항목 1개 → 100p당 1개 기준 미달
        toc = [self._entry(level=1)]
        assert is_toc_meaningful(toc, total_pages=200) is False

    def test_large_doc_with_sublevels_is_meaningful(self):
        # 200페이지, 항목 5개지만 서브레벨 포함 → True
        toc = [self._entry(level=1, page=i * 40) for i in range(3)] + \
              [self._entry(level=2, page=10)]
        assert is_toc_meaningful(toc, total_pages=200) is True

    def test_large_doc_sufficient_entries_level1_only(self):
        # 200페이지, level=1 항목 20개 이상 → True
        toc = [self._entry(level=1, page=i * 10) for i in range(20)]
        assert is_toc_meaningful(toc, total_pages=200) is True
