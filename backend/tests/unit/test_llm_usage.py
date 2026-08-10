"""app/utils/llm_usage.py 단위 테스트. 외부 호출 없음."""

from app.utils.llm_usage import (
    EMPTY_USAGE,
    cache_hit_ratio,
    extract_usage,
    merge_usage,
)


class _FakeMessage:
    """LangChain AIMessage/청크의 usage_metadata 만 흉내낸 스텁."""

    def __init__(self, usage_metadata):
        self.usage_metadata = usage_metadata


class TestExtractUsage:
    def test_full_metadata(self):
        msg = _FakeMessage({
            "input_tokens": 1200,
            "output_tokens": 80,
            "total_tokens": 1280,
            "input_token_details": {"cache_read": 1024},
        })
        assert extract_usage(msg) == {
            "input_tokens": 1200,
            "output_tokens": 80,
            "cache_read": 1024,
        }

    def test_missing_usage_metadata_is_zero(self):
        """usage_metadata 가 없는 응답도 0으로 떨어져야 호출부가 분기하지 않는다."""
        assert extract_usage(_FakeMessage(None)) == EMPTY_USAGE
        assert extract_usage(object()) == EMPTY_USAGE

    def test_missing_input_token_details(self):
        msg = _FakeMessage({"input_tokens": 10, "output_tokens": 2})
        assert extract_usage(msg)["cache_read"] == 0

    def test_none_values_coerced_to_zero(self):
        msg = _FakeMessage({
            "input_tokens": None,
            "output_tokens": 5,
            "input_token_details": {"cache_read": None},
        })
        assert extract_usage(msg) == {
            "input_tokens": 0,
            "output_tokens": 5,
            "cache_read": 0,
        }


class TestMergeUsage:
    def test_streaming_chunks_sum(self):
        """astream 은 첫 청크에만 입력 토큰을 싣고 이후는 출력만 늘어난다."""
        chunks = [
            {"input_tokens": 30, "output_tokens": 15, "cache_read": 16},
            {"input_tokens": 0, "output_tokens": 28, "cache_read": 0},
            {"input_tokens": 0, "output_tokens": 1, "cache_read": 0},
        ]
        total = dict(EMPTY_USAGE)
        for chunk in chunks:
            total = merge_usage(total, chunk)
        assert total == {"input_tokens": 30, "output_tokens": 44, "cache_read": 16}

    def test_merge_with_empty_is_identity(self):
        usage = {"input_tokens": 7, "output_tokens": 3, "cache_read": 2}
        assert merge_usage(dict(EMPTY_USAGE), usage) == usage

    def test_missing_keys_treated_as_zero(self):
        assert merge_usage({"input_tokens": 5}, {"output_tokens": 2}) == {
            "input_tokens": 5,
            "output_tokens": 2,
            "cache_read": 0,
        }

    def test_does_not_mutate_inputs(self):
        left = {"input_tokens": 1, "output_tokens": 1, "cache_read": 1}
        right = dict(left)
        merge_usage(left, right)
        assert left == {"input_tokens": 1, "output_tokens": 1, "cache_read": 1}


class TestCacheHitRatio:
    def test_partial_hit(self):
        assert cache_hit_ratio({"input_tokens": 200, "cache_read": 50}) == 0.25

    def test_no_input_tokens_is_zero_not_division_error(self):
        assert cache_hit_ratio(EMPTY_USAGE) == 0.0

    def test_full_hit(self):
        assert cache_hit_ratio({"input_tokens": 100, "cache_read": 100}) == 1.0
