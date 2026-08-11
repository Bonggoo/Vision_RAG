"""LLM 토큰 사용량 계측.

Gemini 호출마다 입력/출력/캐시히트 토큰을 한 줄로 남깁니다.
프롬프트 구조를 바꾸기 전에 '지금 얼마나 쓰는지'를 먼저 재기 위한 것으로,
집계는 로그 파싱(Cloud Logging)에 맡기고 여기서는 기록만 합니다.

`cache_read` 는 Gemini 암묵적 캐싱으로 할인된 입력 토큰 수입니다 —
프롬프트 앞부분(프리픽스)이 이전 호출과 동일할 때만 0보다 커집니다.
"""
from app.utils.logger import logger

# 사용량 딕셔너리의 표준 키 (합산 대상)
USAGE_KEYS = ("input_tokens", "output_tokens", "cache_read")

EMPTY_USAGE: dict = {key: 0 for key in USAGE_KEYS}


def extract_usage(message) -> dict:
    """LangChain 응답(AIMessage 또는 스트리밍 청크)에서 토큰 사용량을 뽑습니다.

    `usage_metadata` 가 없는 응답(구버전·에러 경로)은 0으로 처리해
    호출부가 분기하지 않아도 되게 합니다.
    """
    usage_metadata = getattr(message, "usage_metadata", None) or {}
    details = usage_metadata.get("input_token_details") or {}
    return {
        "input_tokens": int(usage_metadata.get("input_tokens") or 0),
        "output_tokens": int(usage_metadata.get("output_tokens") or 0),
        "cache_read": int(details.get("cache_read") or 0),
    }


def merge_usage(left: dict, right: dict) -> dict:
    """사용량 두 개를 합칩니다 (스트리밍 청크 누적용).

    astream 은 첫 청크에만 input_tokens/cache_read 를 싣고 이후 청크는 0 이므로
    단순 합산이 곧 그 호출 전체의 사용량이 됩니다.
    """
    return {key: left.get(key, 0) + right.get(key, 0) for key in USAGE_KEYS}


def cache_hit_ratio(usage: dict) -> float:
    """입력 토큰 중 캐시로 할인된 비율(0.0~1.0). 입력이 0이면 0.0."""
    input_tokens = usage.get("input_tokens", 0)
    if input_tokens <= 0:
        return 0.0
    return usage.get("cache_read", 0) / input_tokens


def log_usage(stage: str, usage: dict) -> None:
    """계측된 토큰 사용량을 한 줄로 남깁니다. stage 는 파이프라인 단계 이름."""
    logger.info(
        f"🧮 [Usage] {stage}: in={usage.get('input_tokens', 0)} "
        f"out={usage.get('output_tokens', 0)} "
        f"cached={usage.get('cache_read', 0)} "
        f"({cache_hit_ratio(usage) * 100:.0f}%)"
    )


def log_response_usage(stage: str, message) -> dict:
    """응답 하나의 사용량을 뽑아 바로 로깅합니다 (비스트리밍 호출용)."""
    usage = extract_usage(message)
    log_usage(stage, usage)
    return usage
