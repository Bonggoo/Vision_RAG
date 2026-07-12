"""근접 중복(near-duplicate) 문서 감지.

바이트 단위 SHA-256 사전검사(upload preflight)는 '완전히 동일한 파일'만 잡습니다.
같은 매뉴얼을 다른 방식으로 내보낸 재추출본(예: 페이지 수가 1~4장 다른 PDF)은
바이트가 달라 통과해버려, 사용자 코퍼스에 사실상 같은 문서가 여러 벌 쌓이고
문서 선택 시 후보가 쪼개져 검색 품질이 떨어집니다.

이 모듈은 **콘텐츠 지문**(추출된 ToC 제목 토큰 집합)으로 문서 간 유사도를 재고,
분석 파이프라인 끝(ToC·모델 추출 완료 후)에서 새 문서와 유사한 기존 문서를
찾아냅니다. 자동 삭제/차단은 하지 않고 결과를 메타데이터에 실어 사용자에게
'유사 문서가 있습니다 — 유지/교체/삭제'로 노출하기 위한 감지 전용 로직입니다.

실측 코퍼스(55개) 기준 진짜 중복은 ToC Jaccard 0.99~1.00, 정당한 별권
(기본편/응용편 등)은 0.35 미만이라 임계값 0.7이 오탐 없이 분리합니다.
ToC 제목 비교는 제조사 표기 차이('미쓰비시'/'미쓰비시전기')에 영향받지 않는
장점도 있습니다.
"""
import re

_TOKEN_RE = re.compile(r"[가-힣A-Za-z0-9]+")

# ToC Jaccard가 이 값 이상이면 근접 중복으로 판단
DEFAULT_THRESHOLD = 0.7
# ToC가 없는(스캔) 문서의 보조 판정: 페이지 수 허용 오차 비율
_PAGE_RATIO = 0.05


def _tokenize(text: str) -> set[str]:
    return {t for t in _TOKEN_RE.findall((text or "").lower()) if len(t) >= 2}


def document_fingerprint(meta: dict) -> set[str]:
    """문서의 콘텐츠 지문 = ToC 제목 토큰 집합. ToC가 없으면 파일명 토큰으로 대체."""
    tokens: set[str] = set()
    for entry in (meta.get("toc") or []):
        tokens |= _tokenize(entry.get("title"))
    if tokens:
        return tokens
    return _tokenize(meta.get("filename") or meta.get("original_filename"))


def similarity(meta_a: dict, meta_b: dict) -> float:
    """두 문서의 ToC 지문 Jaccard 유사도(0.0~1.0)."""
    fa, fb = document_fingerprint(meta_a), document_fingerprint(meta_b)
    if not fa or not fb:
        return 0.0
    return len(fa & fb) / len(fa | fb)


def _pages_close(a: dict, b: dict) -> bool:
    pa, pb = int(a.get("total_pages") or 0), int(b.get("total_pages") or 0)
    if not pa or not pb:
        return False
    return abs(pa - pb) <= max(2, round(max(pa, pb) * _PAGE_RATIO))


def _same_model_series(a: dict, b: dict) -> bool:
    sa = (a.get("model_series") or "").strip().lower()
    sb = (b.get("model_series") or "").strip().lower()
    return bool(sa) and sa == sb


def find_similar_documents(
    new_meta: dict,
    existing_metas: list[dict],
    threshold: float = DEFAULT_THRESHOLD,
) -> list[dict]:
    """new_meta와 근접 중복으로 판단되는 기존 문서 목록을 유사도 내림차순으로 반환.

    판정 규칙 (하나라도 해당하면 중복 후보):
      1. ToC 지문 Jaccard ≥ threshold  (reason="toc")
      2. 같은 model_series + 페이지 수 근접  (reason="metadata")
         — 단, **둘 중 하나라도 ToC가 없는(스캔) 경우에만** 적용하는 보조 신호.
         둘 다 ToC가 있는데 제목이 다르면 같은 제품의 '다른 문서'(예: 카탈로그
         vs 설정가이드)일 가능성이 커서, 이때는 metadata 규칙을 쓰지 않고 ToC
         지문만 신뢰합니다(오탐 방지).

    분석 중/오류 상태의 문서와 자기 자신은 비교에서 제외합니다.
    반환: [{"document_id", "filename", "score", "reason"}, ...]
    """
    new_id = str(new_meta.get("document_id", ""))
    new_has_toc = bool(new_meta.get("toc"))
    results: list[dict] = []

    for m in existing_metas:
        if str(m.get("document_id", "")) == new_id:
            continue
        if m.get("status") in ("analyzing", "error"):
            continue

        score = similarity(new_meta, m)
        both_have_toc = new_has_toc and bool(m.get("toc"))
        reason = None
        if score >= threshold:
            reason = "toc"
        elif not both_have_toc and _same_model_series(new_meta, m) and _pages_close(new_meta, m):
            reason = "metadata"

        if reason:
            results.append({
                "document_id": str(m.get("document_id", "")),
                "filename": m.get("filename", ""),
                "score": round(score, 3),
                "reason": reason,
            })

    results.sort(key=lambda x: x["score"], reverse=True)
    return results
