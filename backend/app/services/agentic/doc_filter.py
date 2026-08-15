"""질문 키워드 기반 1차 문서 후보 필터 및 관련 순수 함수.

LLM 호출 전에 후보를 좁혀 프롬프트 토큰과 지연을 줄이는 것이 목적이며,
'정답 문서를 떨어뜨리지 않는 것'을 정확도보다 우선한다(아래 확신 게이트 참고).
"""
import re

from app.services.pdf_service import normalize_manufacturer

# ─── 가중치 ──────────────────────────────────────────────────────────────────
# 파일명·제조사·모델 직접 매칭이 ToC 언급보다 훨씬 강한 관련도 신호다.
META_WEIGHT = 3
TOC_WEIGHT = 1
MODEL_WEIGHT = 12

# 문서당 프롬프트에 전달할 매칭 ToC 제목 상한
MAX_EVIDENCE_TITLES = 8

# 기본 보강 질문 최대 개수
MAX_DEFAULT_CLARIFICATION_QUESTIONS = 3

# 메타데이터가 비어 있을 때 저장되는 값
UNKNOWN = "미상"

# 문서 자체를 가리키는 범용어 — 질문의 '주제'로 치지 않는다
# (파일명에 '매뉴얼'이 흔히 들어 있어 무엇을 물어도 매칭되기 때문)
_DOCUMENT_WORDS = {
    "매뉴얼", "메뉴얼", "설명서", "문서", "자료", "manual", "document", "documents", "pdf",
}

# 주요 산업 도메인 동의어 (한글 질문 ↔ 영문 ToC 매칭 지원)
_SYNONYMS = {
    "위치결정": ["positioning"],
    "알람": ["alarm", "error", "warning", "err", "al"],
    "에러": ["error", "err", "alarm"],
    "경고": ["warning", "warn"],
    "모듈": ["module"],
    "서보": ["servo"],
    "설명서": ["manual"],
    "매뉴얼": ["manual"],
}

# 한글 조사 목록 — 긴 것부터 시도해 최장 일치를 제거
_JOSA = sorted(
    [
        "은", "는", "이", "가", "을", "를", "의", "에", "도", "만",
        "와", "과", "랑", "로", "으로", "에서", "에게", "한테",
        "보다", "부터", "까지", "처럼", "같이", "마다", "조차", "마저", "밖에",
        "이나", "이란", "에는", "에도", "와의", "과의",
        "로는", "로도", "으로는", "으로도", "만으로", "에서는", "에서도",
    ],
    key=len,
    reverse=True,
)

_MODEL_CODE_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9/\-]{1,}")
_KEYWORD_RE = re.compile(r"[가-힣a-zA-Z0-9]{2,}")

# 조사를 떼고 남은 어근의 최소 길이 ('차이'→'차'처럼 파괴되는 것을 방지)
_MIN_STEM_LENGTH = 2
# 모델번호로 인정할 최소 토큰 길이 ('2D' 같은 짧은 오탐 제외)
_MIN_MODEL_CODE_LENGTH = 3


def extract_model_codes(text: str) -> set[str]:
    """텍스트에서 모델번호처럼 보이는 토큰(영문+숫자 혼합, 3자 이상)만 추출합니다.

    예: 'F388A', 'L7NH', 'QD74MH', 'LS-R900', 'CZ-V20'.
    순수 숫자('4800'), 알파벳만('CV'), 점으로 끊기는 알람코드('AL.20'),
    2자 이하('2D')는 제외해 오탐을 줄입니다. 한글 조사는 정규식 문자군 밖이라
    자동으로 경계가 잘립니다(예: 'F388A를' → 'F388A').

    질문에 명시된 모델번호를 문서 메타데이터와 '정확 일치'로 대조해 강하게
    가중하기 위한 신호입니다 — F388A 질문이 F381 매뉴얼로 새는 것을 막습니다.
    """
    codes = set()
    for tok in _MODEL_CODE_RE.findall(text or ""):
        if len(tok) < _MIN_MODEL_CODE_LENGTH:
            continue
        if any(c.isalpha() for c in tok) and any(c.isdigit() for c in tok):
            codes.add(tok.casefold())
    return codes


def strip_josa(token: str) -> str:
    """한글 토큰 끝의 조사를 떼어낸 어근을 반환합니다 (뗄 게 없으면 원본).

    형태소 분석기 의존성 없이 최장 일치 접미사 제거로 근사합니다.
    어근이 2자 미만으로 남으면('차이'→'차'처럼 파괴되면) 떼지 않습니다.
    매칭이 substring 방식이므로 어근은 조사 붙은 원형이 매칭되는 모든 곳에
    + 그 이상을 매칭합니다 — 원형을 어근으로 '대체'해도 recall 손실이 없습니다.
    (예: '색상의'→'색상', '설정값을'→'설정값', '차이만으로'→'차이')
    """
    if not token or not ("가" <= token[-1] <= "힣"):
        return token
    for josa in _JOSA:
        if token.endswith(josa) and len(token) - len(josa) >= _MIN_STEM_LENGTH:
            return token[: -len(josa)]
    return token


def collect_identifiers(documents: list[dict], exclude_document_id: str | None = None) -> set[str]:
    """문서들의 제조사/모델 시리즈에서 대문자 식별자 집합을 뽑습니다.

    전체 문자열과 공백으로 나눈 각 조각(2자 이상)을 모두 담습니다
    — "Mitsubishi Electric" 에서 "MITSUBISHI" 도 잡히도록.

    질문에 다른 장비의 식별자가 들어 있는지 판단하는 데 쓰이며,
    이전에는 맥락 유지 분기와 되묻기 판단 두 곳에 같은 루프가 복붙돼 있었습니다.
    """
    identifiers: set[str] = set()
    for d in documents:
        if exclude_document_id is not None and str(d.get("document_id")) == exclude_document_id:
            continue
        for field in ("manufacturer", "model_series"):
            value = str(d.get(field, "")).strip()
            if not value or value == UNKNOWN:
                continue
            identifiers.add(value.upper())
            identifiers.update(part.upper() for part in value.split() if len(part) >= 2)
    return identifiers


def question_mentions_identifier(question: str, identifiers: set[str]) -> bool:
    """질문 안에 주어진 식별자 중 하나라도 등장하는지 확인합니다."""
    if not identifiers:
        return False
    q_upper = question.upper()
    return any(ident in q_upper for ident in identifiers)


def build_default_clarification_questions(question: str, documents: list[dict]) -> list[str]:
    """LLM이 보강 질문을 생성하지 못했을 때 쓸 기본 보강 질문을 만듭니다.

    주의: 이 문장들은 프론트에서 탭하면 '사용자 메시지'로 그대로 전송됩니다.
    따라서 AI가 사용자에게 묻는 문장("제조사가 어디인가요?")이 아니라,
    원 질문에 후보 문서의 제조사/모델을 덧붙여 재작성한 '사용자 입장의 질문'
    이어야 합니다. 예: "통신 에러 해결법" → "MITSUBISHI MELSEC-Q 통신 에러 해결법"

    질문에 이미 들어있는 제조사(별칭 포함)/모델은 다시 붙이지 않으며
    ("미쓰비시 Q 시리즈..." 질문에 "MITSUBISHI Q 시리즈"를 중복 부착 방지),
    덧붙일 정보가 없는 후보는 건너뜁니다. 전부 건너뛰면 빈 리스트를 반환해
    프론트가 추천 질문 섹션을 숨기고 문서 선택 카드만 노출하게 합니다.
    """
    q_lower = question.lower()
    q_manufacturer = normalize_manufacturer(question)  # 질문에 이미 언급된 제조사 (별칭 흡수)

    questions: list[str] = []
    seen_prefixes: set[str] = set()

    for d in documents:
        manufacturer = str(d.get("manufacturer", "")).strip()
        model = str(d.get("model_series", "")).strip()

        parts = []
        if manufacturer and manufacturer != UNKNOWN and normalize_manufacturer(manufacturer) != q_manufacturer:
            parts.append(manufacturer)
        if model and model != UNKNOWN and model.lower() not in q_lower:
            parts.append(model)
        if not parts:
            continue  # 이 후보로는 질문에 더할 정보가 없음

        prefix = " ".join(parts)
        if prefix in seen_prefixes:
            continue
        seen_prefixes.add(prefix)
        questions.append(f"{prefix} {question}")

        if len(questions) >= MAX_DEFAULT_CLARIFICATION_QUESTIONS:
            break

    return questions


# ─── 1차 문서 필터 ───────────────────────────────────────────────────────────

class _DocText:
    """문서 하나의 검색 대상 텍스트를 미리 소문자·공백제거 형태로 준비해 둔 것."""

    __slots__ = ("doc", "meta", "meta_ns", "toc", "toc_ns")

    def __init__(self, doc: dict):
        self.doc = doc
        meta = " ".join(
            str(doc.get(field) or "") for field in ("filename", "manufacturer", "model_series")
        ).lower()
        toc = " ".join(str(entry.get("title") or "") for entry in (doc.get("toc") or [])).lower()
        self.meta = meta
        self.meta_ns = meta.replace(" ", "")
        self.toc = toc
        self.toc_ns = toc.replace(" ", "")

    def hit(self, keyword: str) -> str | None:
        """키워드가 메타데이터에 걸리면 'meta', ToC 제목에 걸리면 'toc', 아니면 None."""
        kw = keyword.lower()
        kw_ns = kw.replace(" ", "")
        if kw in self.meta or kw_ns in self.meta_ns:
            return "meta"
        if kw in self.toc or kw_ns in self.toc_ns:
            return "toc"
        return None


def _expand_keywords(question: str) -> set[str]:
    """질문에서 키워드를 뽑고 조사를 떼어낸 뒤 동의어를 덧붙입니다."""
    raw = set(_KEYWORD_RE.findall(question.lower()))
    keywords = {strip_josa(kw) for kw in raw}

    expanded = set(keywords)
    for kw in keywords:
        for kor_key, eng_vals in _SYNONYMS.items():
            if kor_key in kw:
                expanded.update(eng_vals)
    return expanded


def question_has_corpus_contact(question: str, all_docs: list[dict]) -> bool:
    """질문의 고유어 중 하나라도 보유 문서의 메타데이터/목차에 등장하는지 봅니다.

    DF 컷(변별력 필터)을 **거치지 않은** 원본 키워드로 검사하는 것이 핵심입니다.
    filter_documents_by_keywords 의 fallback_none 은 '변별력 있는 키워드가 없음'
    이라서, 흔한 단어로만 이뤄진 정상 질문("서보 진동이 심해요")에서도 발생합니다.
    반면 이 함수가 False 라는 것은 질문에 등장한 어떤 단어도 보유 문서 어디에도
    없다는 뜻 — 보유하지 않은 장비/제조사를 물었을 가능성이 큽니다.

    '매뉴얼', '설명서' 같은 문서 자체를 가리키는 단어는 파일명에 흔히 들어 있어
    무엇을 물어도 접촉이 성립해 버리므로 제외합니다. "다이치 매뉴얼" 질문이
    파일명의 '매뉴얼' 때문에 접촉으로 판정되는 것을 막습니다.
    """
    doc_texts = [_DocText(d) for d in all_docs]
    for kw in _expand_keywords(question):
        if kw in _DOCUMENT_WORDS:
            continue
        if any(dt.hit(kw) for dt in doc_texts):
            return True
    return False


def _select_discriminative_keywords(
    keywords: set[str], doc_texts: list[_DocText]
) -> tuple[set[str], set[str]]:
    """변별력 있는 키워드와, 그중 증거 쪽지로 쓸 만큼 희귀한 키워드를 고릅니다.

    - DF 컷: 보유 문서의 1/3 초과에 등장하는 키워드('설정' 등 범용어)는 변별력이
      없으므로 점수에서 제외. 코퍼스 기준 즉석 계산이라 사용자마다 자가 적응한다.
    - 증거 컷: '명령'·'있는'처럼 DF컷은 통과하지만 10여 개 문서에 흔한 준범용어가
      잡음 쪽지를 남발하는 것을 방지 — 'SMATV'(1개 문서)급 단서만 LLM에 전달한다.
    """
    max_df = max(1, len(doc_texts) // 3)
    evidence_max_df = max(3, len(doc_texts) // 10)

    discriminative: set[str] = set()
    evidence: set[str] = set()
    for kw in keywords:
        df = sum(1 for dt in doc_texts if dt.hit(kw))
        if 0 < df <= max_df:
            discriminative.add(kw)
            if df <= evidence_max_df:
                evidence.add(kw)
    return discriminative, evidence


def _collect_matching_toc_titles(doc: dict, keywords: list[str]) -> list[str]:
    """주어진 키워드가 등장하는 ToC 제목을 최대 MAX_EVIDENCE_TITLES 개 수집합니다."""
    titles: list[str] = []
    lowered = [(kw.lower(), kw.lower().replace(" ", "")) for kw in keywords]
    for entry in doc.get("toc") or []:
        title = str(entry.get("title") or "")
        tl = title.lower()
        tl_ns = tl.replace(" ", "")
        if any(kw in tl or kw_ns in tl_ns for kw, kw_ns in lowered):
            titles.append(title[:60])
            if len(titles) >= MAX_EVIDENCE_TITLES:
                break
    return titles


def filter_documents_by_keywords(
    question: str, all_docs: list[dict]
) -> tuple[list[dict], str, dict]:
    """질문 키워드로 문서 후보를 좁히는 1차 필터.

    반환: (후보 문서 리스트, mode, toc_evidence)
      mode = "filtered"       — 증거가 충분해 후보를 좁혔음 (점수 내림차순 정렬)
             "fallback_weak"  — 매칭이 전부 미약(ToC 우연 매칭 1~2건)해 필터를
                                신뢰하지 않고 전체 문서를 반환
             "fallback_none"  — 매칭된 문서가 없어 전체 문서를 반환
      toc_evidence = {document_id: [질문 키워드와 겹친 ToC 제목, ...]}
             — 변별 키워드가 ToC 제목에서 발견된 문서만 담김. 점수로 뭉개지 않고
               문서 선택 LLM에게 그대로 전달해, 'SMATV'처럼 문서 제목에는 없고
               목차에만 있는 단서로도 올바른 문서를 고를 수 있게 하는 근거 자료.

    설계 (질문 품질 평가 107문항 실측에서 실패 8건이 전부 '정답 문서가 필터에서
    0점 탈락'한 recall 문제였던 것을 근거로 함):
      1. 조사 스트리핑 — '색상의'가 ToC의 '색상'과 매칭되지 않던 실패를 해소.
      2. DF 컷 — 범용어를 점수에서 제외 (_select_discriminative_keywords 참고).
      3. 확신 게이트 — 최고점이 META_WEIGHT 미만(파일명/제조사/모델 직접 매칭
         전무)이면 필터가 정답을 놓쳤을 가능성이 커서 전체 문서로 폴백.
         배제형 필터에서 0점 정답 문서는 이후 어떤 단계로도 복구 불가하므로,
         약한 증거로는 배제하지 않는다.
    """
    doc_texts = [_DocText(d) for d in all_docs]
    keywords = _expand_keywords(question)
    discriminative, evidence_kws = _select_discriminative_keywords(keywords, doc_texts)
    question_model_codes = extract_model_codes(question)

    scored: list[tuple[dict, int]] = []
    toc_evidence: dict[str, list[str]] = {}

    for dt in doc_texts:
        score = 0
        toc_hit_kws: list[str] = []

        for kw in discriminative:
            where = dt.hit(kw)
            if where == "meta":
                score += META_WEIGHT
            elif where == "toc":
                score += TOC_WEIGHT
                if kw in evidence_kws:
                    toc_hit_kws.append(kw)

        # ToC에서 발견된 변별 키워드는 어느 제목에서 나왔는지까지 수집해 LLM에 전달
        if toc_hit_kws:
            titles = _collect_matching_toc_titles(dt.doc, toc_hit_kws)
            if titles:
                toc_evidence[str(dt.doc.get("document_id", ""))] = titles

        # 명시 모델번호 정확 일치 → 강한 가중 (예: 'F388A' 질문 → 'F388A' 매뉴얼)
        if question_model_codes:
            matched = question_model_codes & extract_model_codes(dt.meta)
            if matched:
                score += MODEL_WEIGHT * len(matched)

        if score > 0:
            scored.append((dt.doc, score))

    if not scored:
        return list(all_docs), "fallback_none", toc_evidence

    scored.sort(key=lambda x: x[1], reverse=True)
    if scored[0][1] < META_WEIGHT:
        return list(all_docs), "fallback_weak", toc_evidence

    return [d for d, _ in scored], "filtered", toc_evidence
