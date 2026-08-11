"""ToC(목차) 페이지 번호 정규화 및 섹션 범위 계산."""
import re

# ToC가 없는 문서에서 전체 페이지를 그대로 Vision 분석할 수 있는 최대 페이지 수.
# 이미지 업로드(1페이지)나 짧은 일반 문서(회의록·점검표 등)가 여기에 해당합니다.
SMALL_DOC_FULL_SCAN_PAGES = 5

# Phase 2 텍스트 탐색 섹션 최대 길이. 너무 넓히면 프롬프트 토큰과 지연이 급증한다.
SECTION_SCAN_WINDOW = 50

# "3-32"(챕터-페이지) 형식에서 뒤쪽 숫자를 뽑기 위한 패턴
_CHAPTER_PAGE_RE = re.compile(r"(\d+)[^\d]+(\d+)")


def normalize_page(page_value) -> int:
    """ToC의 페이지 값을 정수로 정규화합니다.

    지원 형식:
    - int / float: 정수로 변환
    - "32": 문자열 정수
    - "3-32" (챕터-페이지): 하이픈 뒤 숫자를 사용
    - 그 외: 1
    """
    if isinstance(page_value, int):
        return page_value
    if isinstance(page_value, float):
        return int(page_value)
    if isinstance(page_value, str):
        page_value = page_value.strip()
        if page_value.isdigit():
            return int(page_value)
        match = _CHAPTER_PAGE_RE.match(page_value)
        if match:
            return int(match.group(2))
    return 1


def resolve_target_pages_without_toc(total_pages: int) -> list[int] | None:
    """ToC 없는 문서의 전체 페이지 폴백.

    소형 문서면 전체 페이지 목록(1-indexed)을, 대형이면 `None`(→ 에러 응답)을 반환합니다.
    """
    if 0 < total_pages <= SMALL_DOC_FULL_SCAN_PAGES:
        return list(range(1, total_pages + 1))
    return None


def build_breadcrumb(toc: list[dict], page: int) -> str:
    """주어진 페이지가 속한 ToC 계층 경로를 만듭니다.

    예: "3장 트러블슈팅 > 3.2 알람 목록"

    각 level 에서 `page` 이하이면서 가장 가까운 항목을 고른 뒤 상위→하위 순으로
    잇습니다. 하위 항목이 상위 항목보다 앞 페이지면 다른 장에 속한 것이므로
    거기서 경로를 끊습니다.

    ToC 는 업로드 시 이미 추출해 둔 것이라 추가 LLM 호출이 없습니다.
    """
    if not toc:
        return ""

    # level → (가장 가까운 page, title)
    nearest: dict[int, tuple[int, str]] = {}
    for entry in toc:
        entry_page = normalize_page(entry.get("page", 1))
        if entry_page > page:
            continue
        title = str(entry.get("title") or "").strip()
        if not title:
            continue
        try:
            level = int(entry.get("level", 1) or 1)
        except (TypeError, ValueError):
            level = 1
        found = nearest.get(level)
        if found is None or entry_page >= found[0]:
            nearest[level] = (entry_page, title)

    parts: list[str] = []
    last_page = 0
    for level in sorted(nearest):
        entry_page, title = nearest[level]
        if entry_page < last_page:
            break  # 상위 항목보다 앞선 하위 항목 → 다른 장 소속
        parts.append(title)
        last_page = entry_page
    return " > ".join(parts)


def find_section_page_range(
    toc: list[dict], target_pages: list[int], total_pages: int
) -> tuple[int, int]:
    """Phase 2 텍스트 검색 범위를 결정합니다.

    - start: target_pages 이전의 가장 가까운 ToC 항목 (섹션 시작점)
    - end: start 로부터 최대 SECTION_SCAN_WINDOW 페이지

    ToC 하위 항목 경계에서 끊지 않습니다.
    """
    if not target_pages:
        return 1, min(SECTION_SCAN_WINDOW, total_pages)

    pages = sorted({normalize_page(entry.get("page", 1)) for entry in toc})
    min_target = min(target_pages)

    start = min_target
    for p in reversed(pages):
        if p <= min_target:
            start = p
            break

    end = min(start + SECTION_SCAN_WINDOW - 1, total_pages)
    return start, end
