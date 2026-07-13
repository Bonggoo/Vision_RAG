"""
질문 품질 자동 평가 러너.

evals/dataset.yaml의 골든 케이스를 파이프라인에 흘려보내고 SSE 이벤트를
파싱하여 채점합니다. 실행 대상은 두 가지:

- remote (기본): Cloud Run 등 배포된 백엔드에 HTTP로 POST /chat/stream
- local (--local): run_agentic_pipeline을 프로세스 내에서 직접 호출

되묻기(clarification) 플로우도 자동으로 검증합니다:
1턴에서 문서 후보 리스트가 오면, 기대 문서와 일치하는 후보를 골라
document_id를 지정해 2턴을 재질문하고 최종 답변까지 채점합니다
(프론트엔드에서 사용자가 문서를 선택하는 동작을 재현).

채점 축:
1. routing        — technical / general / clarification 최종 분기
2. clarification  — (expect_clarification 명시 시) 1턴 되묻기 발생 + 후보에 기대 문서 포함
3. document       — 참조 문서(파일명 부분 일치)
4. pages          — 참조 페이지 ±tolerance
5. keywords       — 답변 필수 키워드 포함률
   (+ 옵션 --judge: 기준 답변 대비 Gemini LLM 채점 1~5점)

사용법 (backend/ 디렉토리에서, venv 활성화 후):
    python -m evals.run_eval                       # defaults.base_url(Cloud Run)로 원격 실행
    python -m evals.run_eval --local               # 로컬 파이프라인 직접 호출
    python -m evals.run_eval --base-url http://localhost:8000
    python -m evals.run_eval --only greeting --judge --min-pass 0.8
    python -m evals.run_eval --generate 20          # dataset.yaml 대신 실제 매뉴얼
                                                     # ToC에서 매번 다른 20문항 생성해 실행

--generate N 모드: GET /documents(원격) 또는 metadata_service(로컬)로 실제 보유
매뉴얼 목록+ToC를 가져와, 문서를 무작위로 뽑고 그 ToC 섹션 제목을 근거로 Gemini가
자연스러운 사용자 질문을 합성합니다. 뽑힌 (문서, 페이지)가 곧 정답이므로 routing/
document/pages는 그대로 채점되고, answer_keywords·reference_answer는 없어 그
두 축은 건너뜁니다. 실행마다 무작위 샘플이라 매번 다른 질문 조합이 됩니다.

원격 인증 (우선순위 순, evals/.env 또는 환경변수에서 조회 — backend/.env 아님):
    --token <JWT>            브라우저 localStorage 등에서 복사한 access token
    EVAL_ACCESS_TOKEN        위와 동일 (환경변수)
    EVAL_JWT_SECRET          프로덕션 JWT_SECRET → 러너가 토큰 자체 발급
    (없으면 로컬 settings.JWT_SECRET으로 발급 시도 — 프로덕션 시크릿이 다르면 401)

결과는 콘솔 요약 + evals/results/<타임스탬프>.json 으로 저장됩니다.
"""
import argparse
import asyncio
import json
import logging
import os
import random
import statistics
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import yaml

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

EVALS_DIR = Path(__file__).resolve().parent
RESULTS_DIR = EVALS_DIR / "results"


def _env(key: str) -> str | None:
    """환경변수 → evals/.env 순으로 값을 찾습니다.

    backend/.env가 아니라 evals/.env를 쓰는 이유: app/config.py의 pydantic
    Settings는 SettingsConfigDict(env_file=".env")로 backend/.env 전체를 읽어
    선언되지 않은 키(EVAL_*)가 있으면 extra_forbidden 에러로 부팅 자체가
    실패합니다. eval 전용 시크릿은 여기서 분리 관리합니다.
    """
    if os.environ.get(key):
        return os.environ[key]
    env_file = EVALS_DIR / ".env"
    if env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line.startswith(f"{key}="):
                return line.split("=", 1)[1].strip().strip('"').strip("'") or None
    return None


# ─── SSE 파싱 ────────────────────────────────────────────────────────────────

class SSEBuffer:
    """HTTP 청크 경계에서 이벤트가 잘려도 안전한 증분 SSE 파서."""

    def __init__(self):
        self._buf = ""

    def feed(self, text: str) -> list[dict]:
        self._buf += text
        events = []
        while "\n\n" in self._buf:
            block, self._buf = self._buf.split("\n\n", 1)
            for line in block.splitlines():
                line = line.strip()
                if line.startswith("data: "):
                    try:
                        events.append(json.loads(line[len("data: "):]))
                    except json.JSONDecodeError:
                        pass
        return events


def _new_obs() -> dict:
    return {
        "answer": "",
        "references": [],
        "clarification": False,
        "clarification_content": "",
        "candidates": [],
        "suggested_questions": [],
        "errors": [],
        "reasoning": [],
    }


def _ingest(obs: dict, ev: dict):
    t = ev.get("type")
    if t == "answer":
        obs["answer"] += ev.get("content", "")
    elif t == "reference":
        obs["references"].append({
            "page": ev.get("page_number"),
            "document": ev.get("document_name", ""),
        })
    elif t == "clarification":
        obs["clarification"] = True
        obs["clarification_content"] = ev.get("content", "")
        obs["candidates"] = ev.get("candidates", [])
        obs["suggested_questions"] = ev.get("suggested_questions", [])
    elif t == "error":
        obs["errors"].append(ev.get("content", ""))
    elif t == "reasoning":
        obs["reasoning"].append(ev.get("content", ""))


# ─── 실행 대상 (transport) ───────────────────────────────────────────────────

class LocalTransport:
    """run_agentic_pipeline을 프로세스 내에서 직접 호출합니다."""

    name = "local"

    async def stream(self, question, document_id, chat_history, user_email):
        from app.services.agentic_graph import run_agentic_pipeline
        async for chunk in run_agentic_pipeline(
            document_id=document_id,
            question=question,
            chat_history=chat_history,
            image=None,
            user_email=user_email,
            session_id=None,  # 대화 저장 안 함
        ):
            yield chunk


class RemoteTransport:
    """배포된 백엔드에 HTTP로 POST /chat/stream 요청을 보냅니다."""

    name = "remote"

    def __init__(self, base_url: str, token: str, timeout: float):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout

    async def stream(self, question, document_id, chat_history, user_email):
        body = {"message": question}
        if document_id:
            body["document_id"] = document_id
        if chat_history:
            body["chat_history"] = chat_history
        headers = {"Authorization": f"Bearer {self.token}"}
        timeout = httpx.Timeout(self.timeout, connect=15.0)
        async with httpx.AsyncClient(timeout=timeout) as client:
            async with client.stream(
                "POST", f"{self.base_url}/chat/stream", json=body, headers=headers
            ) as resp:
                if resp.status_code != 200:
                    detail = (await resp.aread()).decode(errors="replace")[:300]
                    raise RuntimeError(f"HTTP {resp.status_code}: {detail}")
                async for text in resp.aiter_text():
                    yield text


async def _ask(transport, question, document_id, chat_history, user_email, timeout) -> dict:
    """질문 1턴을 실행하고 SSE 이벤트를 수집합니다."""
    obs = _new_obs()
    buf = SSEBuffer()

    async def consume():
        async for chunk in transport.stream(question, document_id, chat_history, user_email):
            for ev in buf.feed(chunk):
                _ingest(obs, ev)

    try:
        await asyncio.wait_for(consume(), timeout=timeout)
    except asyncio.TimeoutError:
        obs["errors"].append(f"TIMEOUT ({timeout:.0f}s)")
    except Exception as e:
        obs["errors"].append(f"요청 실패: {e}")
    return obs


# ─── 채점 ────────────────────────────────────────────────────────────────────

def _observed_type(obs: dict) -> str:
    """수집된 이벤트로부터 파이프라인이 택한 분기를 역산합니다."""
    if obs["clarification"]:
        return "clarification"
    if obs["errors"] and not obs["answer"]:
        return "error"
    if obs["references"]:
        return "technical"
    return "general"


def _candidate_label(c: dict) -> str:
    return f"{c.get('title', '')} / {c.get('manufacturer', '')} / {c.get('model_series', '')}"


def _pick_candidate(candidates: list[dict], key: str | None) -> dict | None:
    """되묻기 후보 중 key(부분 일치)에 맞는 문서를 고릅니다. 없으면 1순위."""
    if not candidates:
        return None
    if key:
        want = str(key).casefold()
        for c in candidates:
            if want in _candidate_label(c).casefold():
                return c
    return candidates[0]


def _score(expected: dict, obs: dict, defaults: dict) -> dict:
    """expected에 명시된 항목만 채점합니다. {검사명: {pass, detail}} 반환."""
    checks = {}

    if "type" in expected:
        got = _observed_type(obs)
        checks["routing"] = {
            "pass": got == expected["type"],
            "detail": f"기대 {expected['type']} / 실제 {got}",
        }

    if "document" in expected:
        want = str(expected["document"]).casefold()
        got_docs = sorted({r["document"] for r in obs["references"] if r["document"]})
        checks["document"] = {
            "pass": any(want in d.casefold() for d in got_docs),
            "detail": f"기대 '{expected['document']}' / 실제 {got_docs or '없음'}",
        }

    if "pages" in expected:
        tol = int(expected.get("page_tolerance", defaults.get("page_tolerance", 1)))
        got_pages = sorted({r["page"] for r in obs["references"] if r["page"]})
        hit = any(
            abs(g - int(e)) <= tol for g in got_pages for e in expected["pages"]
        )
        checks["pages"] = {
            "pass": hit,
            "detail": f"기대 {expected['pages']}(±{tol}) / 실제 {got_pages or '없음'}",
        }

    if "answer_keywords" in expected:
        # 공백 유무 차이(예: "부족전압" vs "부족 전압")로 인한 오탐 방지를 위해
        # 공백을 제거한 문자열로도 매칭을 시도합니다.
        answer = obs["answer"].casefold()
        answer_nospace = "".join(answer.split())
        keywords = expected["answer_keywords"]
        matched = [
            k for k in keywords
            if str(k).casefold() in answer or "".join(str(k).casefold().split()) in answer_nospace
        ]
        recall = len(matched) / len(keywords) if keywords else 1.0
        threshold = float(expected.get("min_keyword_recall", defaults.get("min_keyword_recall", 0.7)))
        missing = [k for k in keywords if k not in matched]
        checks["keywords"] = {
            "pass": recall >= threshold,
            "detail": f"포함률 {recall:.0%} (기준 {threshold:.0%})" + (f", 누락: {missing}" if missing else ""),
            "recall": recall,
        }

    return checks


async def _judge(question: str, reference_answer: str, answer: str) -> tuple[float, str]:
    """기준 답변 대비 생성 답변을 Gemini Flash로 1~5점 채점합니다."""
    from app.services.agent_service import _create_flash_llm, _clean_json_response
    from langchain_core.messages import HumanMessage

    prompt = f"""당신은 산업장비 매뉴얼 QA 시스템의 답변 품질 평가자입니다.

[질문]
{question}

[기준 답변]
{reference_answer}

[평가 대상 답변]
{answer}

기준 답변과 비교하여 정확성(사실 일치), 충실성(질문에 대한 직접적 응답), 완결성을 종합해 1~5점으로 채점하세요.
- 5: 기준 답변과 동등하거나 더 상세하며 오류 없음
- 3: 핵심은 맞지만 일부 누락 또는 부정확
- 1: 틀렸거나 질문과 무관

다른 텍스트 없이 JSON만 출력하세요: {{"score": <1~5 숫자>, "reason": "<한 문장 근거>"}}"""

    llm = _create_flash_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    data = json.loads(_clean_json_response(resp.content))
    return float(data["score"]), str(data.get("reason", ""))


async def _judge_document_equivalence(question: str, source_doc: str, selected_docs: list[str]) -> tuple[bool, str]:
    """--generate 모드에서 소스 문서 대신 다른 문서가 선택됐을 때, 그 문서도
    정답으로 인정 가능한지(같은 장비의 다른 판본이거나, 질문이 모델 비종속적이라
    선택된 문서로도 정확히 답할 수 있는지)를 Flash로 판정합니다.

    생성 질문은 일부러 모델명을 생략해 만들기 때문에(run_eval 상단 참고), 소스
    문서 1개만 정답으로 채점하면 "여러 매뉴얼이 답할 수 있는 일반 질문"과 "중복/
    판본 문서"가 구조적으로 실패로 찍힙니다. 이 판정으로 그 가짜 실패를 걸러냅니다.
    단, 서로 다른 모델번호(F388A vs F381 등)에 대한 모델 특정 질문은 불인정해
    실제 검색 오류 신호는 보존합니다.
    """
    from app.services.agent_service import _create_flash_llm, _clean_json_response
    from langchain_core.messages import HumanMessage

    sel = ", ".join(f"'{d}'" for d in selected_docs) or "없음"
    prompt = f"""당신은 산업장비 매뉴얼 검색 시스템의 평가자입니다.
이 질문은 원래 '{source_doc}' 매뉴얼에서 만들어졌지만, 이는 '출처'일 뿐
질문이 그 모델 전용이라는 뜻은 아닙니다. 검색 시스템은 대신 다음 문서를
참조해 답변했습니다: {sel}

참조 문서로도 이 질문에 '정확히 답할 수 있는지'를 판정하세요.
핵심 판단 기준은 **질문 텍스트 자체**입니다 (출처 문서명이 아니라).

[인정(equivalent=true) 조건 — 하나라도 해당]
- 참조 문서가 출처 문서와 같은 장비/모델의 다른 판본·번역본이라 내용이 실질적으로 동일
- 질문 텍스트에 특정 모델번호가 없고 일반적 내용(예: 통신 규격·설치·안전)이라,
  참조 문서가 같은 종류의 장비/기능을 다루면 정확히 답할 수 있음

[불인정(equivalent=false) 조건 — 하나라도 해당]
- 질문 텍스트가 특정 모델번호를 명시하고 그 모델 고유 사양을 물음
  (예: 질문에 'F388A'가 있는데 참조는 F381 → 불인정)
- 참조 문서가 다른 종류의 장비를 다뤄 질문의 기능·주제 자체가 없음

[질문]
{question}

다른 텍스트 없이 JSON만 출력: {{"equivalent": true 또는 false, "reason": "<한 문장 근거>"}}"""

    llm = _create_flash_llm()
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    data = json.loads(_clean_json_response(resp.content))
    return bool(data.get("equivalent", False)), str(data.get("reason", ""))


# ─── 케이스 실행 ─────────────────────────────────────────────────────────────

async def run_case(case: dict, defaults: dict, transport, judge_enabled: bool, equiv_check: bool = False) -> dict:
    """케이스 1건 실행. 되묻기가 오면 문서를 선택해 2턴까지 진행 후 채점합니다."""
    expected = case.get("expected", {})
    user_email = case.get("user_email") or defaults.get("user_email")
    timeout = float(case.get("timeout", defaults.get("timeout", 180)))
    question = case["question"]

    t0 = time.monotonic()
    turn1 = await _ask(transport, question, case.get("document_id"), None, user_email, timeout)
    final = turn1
    selected = None
    turns = 1

    # 되묻기 → 문서 선택 → 재질문 (최종 기대가 clarification이 아닐 때만)
    if turn1["clarification"] and expected.get("type") != "clarification":
        selected = _pick_candidate(
            turn1["candidates"],
            case.get("select_document") or expected.get("document"),
        )
        if selected:
            history = [
                {"role": "user", "content": question},
                {"role": "assistant", "content": turn1["clarification_content"]},
            ]
            final = await _ask(transport, question, str(selected["document_id"]), history, user_email, timeout)
            turns = 2
    latency = time.monotonic() - t0

    checks = _score(expected, final, defaults)

    # 문서 채점 보정: 소스 문서가 되묻기 후보 메뉴에 떴는지(=검색 recall)를 detail에
    # 덧붙이고, precision(자동선택)이 빗나갔더라도 선택된 문서가 '동등 문서'면 통과로
    # 인정합니다. --generate 모드에서만 적용 (골든셋은 정답이 명확하므로 엄격 유지).
    if equiv_check and "document" in checks:
        want = str(expected.get("document", "")).casefold()
        cand_titles = [c.get("title", "") for c in turn1["candidates"]]
        source_in_menu = any(want in t.casefold() for t in cand_titles)
        if turn1["candidates"]:
            checks["document"]["detail"] += f" | 되묻기 후보에 소스 {'포함' if source_in_menu else '누락'}"

        got_docs = sorted({r["document"] for r in final["references"] if r["document"]})
        if not checks["document"]["pass"] and got_docs:
            try:
                equivalent, reason = await _judge_document_equivalence(
                    question, expected.get("document", ""), got_docs
                )
                if equivalent:
                    checks["document"]["pass"] = True
                    checks["document"]["detail"] += f" | 동등 문서 인정: {reason}"
                    checks["document"]["equiv_accepted"] = True
                else:
                    checks["document"]["detail"] += f" | 실오답 확인: {reason}"
            except Exception as e:
                checks["document"]["detail"] += f" | 동등성 판정 실패: {e}"

    # 되묻기 플로우 검사 (expect_clarification 명시 시)
    if "expect_clarification" in expected:
        want = bool(expected["expect_clarification"])
        got = turn1["clarification"]
        ok = want == got
        detail = f"1턴 되묻기 {'발생' if got else '없음'} (기대: {'발생' if want else '없음'})"
        if ok and want and expected.get("document"):
            want_doc = str(expected["document"]).casefold()
            in_cands = any(want_doc in _candidate_label(c).casefold() for c in turn1["candidates"])
            ok = in_cands
            titles = [c.get("title", "") for c in turn1["candidates"]]
            detail += f", 후보에 기대 문서 {'포함' if in_cands else '누락'} (후보: {titles})"
        checks["clarification"] = {"pass": ok, "detail": detail}

    if judge_enabled and expected.get("reference_answer") and final["answer"]:
        threshold = float(expected.get("min_judge_score", defaults.get("min_judge_score", 3.5)))
        try:
            score, reason = await _judge(question, expected["reference_answer"], final["answer"])
            checks["judge"] = {
                "pass": score >= threshold,
                "detail": f"{score:.1f}점 (기준 {threshold}) — {reason}",
                "score": score,
            }
        except Exception as e:
            checks["judge"] = {"pass": False, "detail": f"채점 실패: {e}"}

    return {
        "id": case["id"],
        "question": question,
        "style": case.get("style"),
        "passed": all(c["pass"] for c in checks.values()) if checks else False,
        "checks": checks,
        "turns": turns,
        "clarification_candidates": [c.get("title", "") for c in turn1["candidates"]],
        "selected_document": (selected or {}).get("title"),
        "latency_sec": round(latency, 1),
        "answer": final["answer"],
        "references": final["references"],
        "errors": turn1["errors"] + ([] if final is turn1 else final["errors"]),
    }


# ─── 리포트 ──────────────────────────────────────────────────────────────────

def _print_report(results: list[dict]):
    print("\n" + "=" * 72)
    for r in results:
        mark = "✅ PASS" if r["passed"] else "❌ FAIL"
        flow = f", 되묻기→'{r['selected_document']}' 선택" if r["turns"] == 2 else ""
        print(f"{mark}  {r['id']}  ({r['latency_sec']}s, {r['turns']}턴{flow})")
        for name, c in r["checks"].items():
            sub = "✓" if c["pass"] else "✗"
            print(f"    {sub} {name}: {c['detail']}")
        for err in r["errors"]:
            print(f"    ⚠ error: {err}")
    print("=" * 72)

    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\n통과: {passed}/{total} ({passed / total:.0%})" if total else "\n실행된 케이스 없음")

    by_check: dict[str, list[bool]] = {}
    for r in results:
        for name, c in r["checks"].items():
            by_check.setdefault(name, []).append(c["pass"])
    for name, vals in sorted(by_check.items()):
        print(f"  - {name}: {sum(vals)}/{len(vals)}")

    # 문체별 분리 집계 (--generate의 terse/sentence 혼합 시)
    by_style: dict[str, list[dict]] = {}
    for r in results:
        if r.get("style"):
            by_style.setdefault(r["style"], []).append(r)
    if len(by_style) > 1:
        print("  문체별:")
        for style, rs in sorted(by_style.items()):
            p = sum(1 for r in rs if r["passed"])
            doc_p = sum(1 for r in rs if r["checks"].get("document", {}).get("pass"))
            print(f"    - {style}: 전체 {p}/{len(rs)}, document {doc_p}/{len(rs)}")

    if results:
        latencies = [r["latency_sec"] for r in results]
        print(f"  - 평균 응답 시간: {statistics.mean(latencies):.1f}s (최대 {max(latencies):.1f}s)")


# ─── 질문 자동 생성 (--generate) ──────────────────────────────────────────────

async def _fetch_documents(local: bool, base_url: str | None, token: str | None, user_email: str) -> list[dict]:
    """실제 보유 매뉴얼 목록(+ToC)을 가져옵니다. 원격은 GET /documents, 로컬은 metadata_service."""
    if local:
        from app.services.metadata_service import get_all_documents_async
        return await get_all_documents_async(owner_email=user_email)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            f"{base_url.rstrip('/')}/documents",
            headers={"Authorization": f"Bearer {token}"},
        )
        resp.raise_for_status()
        return resp.json().get("documents", [])


async def _synthesize_question(doc: dict, entry: dict, style: str = "sentence") -> str:
    """문서 메타데이터 + ToC 섹션 제목을 근거로 사용자 질문 1개를 생성합니다.

    style:
      - "sentence": 자연스러운 문장형 질문 (기본)
      - "terse":    급한 현장 기술자가 검색창에 치듯 키워드만 나열한 전보식 입력.
                    실사용자의 상당수가 이런 식으로 입력하므로, 키워드가 극도로
                    적은 입력에서도 라우팅/문서선택이 버티는지 측정하는 용도.
    """
    from app.services.agent_service import _create_flash_llm, _extract_text_content
    from langchain_core.messages import HumanMessage

    if style == "terse":
        style_rules = """- 급한 현장 기술자가 검색창에 치듯 **키워드 나열식**으로 작성
- 조사·존댓말·의문문 어미 생략, 2~5개 단어, 20자 이내
- 예시 형태: "AL.20 과부하", "2051 서보 알람", "원점복귀 안됨", "RS-485 종단저항 설정"
- 섹션 제목의 핵심 용어(에러코드/기능명/부품명)를 반드시 1개 이상 포함"""
    else:
        style_rules = """- 너무 일반적이지 않게, 섹션 제목이 암시하는 구체적 상황을 반영한 자연스러운 문장형 질문"""

    prompt = f"""당신은 산업 현장 기술자입니다. 아래 매뉴얼의 특정 섹션 제목만 보고,
현장에서 실제로 물어볼 법한 질문을 정확히 1개 작성하세요.

매뉴얼: {doc.get('filename', '')}
제조사: {doc.get('manufacturer', '미상')}
모델: {doc.get('model_series', '미상')}
섹션: {entry.get('title', '')}

규칙:
- 질문 1개만, 다른 설명이나 번호 매기기 없이 순수 질문 텍스트만 출력
- 제조사/모델명을 반드시 포함하지 않아도 됨 (실제 사용자는 종종 생략함)
- 단, "이 모델", "이 장비", "이번 개정판" 같은 지시어로 대상을 가리키지 말 것 —
  질문만 읽고도 무엇에 대한 것인지 알 수 있게 자립적으로 작성
  (지시어 질문은 어떤 검색으로도 라우팅이 불가능해 채점 노이즈가 됨)
{style_rules}
- 한국어로 작성"""

    llm = _create_flash_llm(temperature=0.9)
    resp = await llm.ainvoke([HumanMessage(content=prompt)])
    return _extract_text_content(resp.content).strip().strip('"').strip()


async def generate_cases(local: bool, base_url: str | None, token: str | None, user_email: str, n: int) -> list[dict]:
    """실제 매뉴얼 ToC에서 n개 (문서, 섹션)을 무작위로 뽑아 질문을 합성합니다.
    뽑힌 문서/페이지가 곧 정답이므로 routing/document/pages 채점의 expected로 씁니다."""
    documents = await _fetch_documents(local, base_url, token, user_email)

    def _entries_for(doc: dict) -> list[dict]:
        entries = [e for e in (doc.get("toc") or []) if e.get("title") and e.get("page")]
        # 챕터급(level 1) 항목은 실제 내용이 몇 페이지 뒤에 있는 경우가 많아
        # 페이지 채점 오차가 커짐 — 더 구체적인 하위 섹션(level>=2)을 우선 사용.
        specific = [e for e in entries if int(e.get("level") or 1) >= 2]
        return specific or entries

    eligible_docs = [d for d in documents if _entries_for(d)]
    if not eligible_docs:
        print("생성할 ToC 항목이 없습니다 (문서 없음 또는 ToC 미추출).")
        return []

    # ToC가 방대한 문서(예: 1000+ 항목)가 무작위 추출을 독식하지 않도록,
    # 항목 단위가 아니라 "문서" 단위로 먼저 고르게 분산시켜 뽑습니다.
    random.shuffle(eligible_docs)
    doc_cycle = (eligible_docs * (n // len(eligible_docs) + 1))[:max(n, len(eligible_docs))]
    random.shuffle(doc_cycle)
    picks = [(d, random.choice(_entries_for(d))) for d in doc_cycle[:n]]

    # 문체 배분: 30%는 전보식(terse — "2051 서보 알람" 같은 키워드 나열 입력),
    # 나머지는 문장형. 실사용자의 급한 검색형 입력에서도 파이프라인이 버티는지
    # 매 실행마다 함께 측정합니다.
    n_terse = round(n * 0.3)
    styles = ["terse"] * n_terse + ["sentence"] * (n - n_terse)
    random.shuffle(styles)

    async def _build(i, doc, entry, style):
        question = await _synthesize_question(doc, entry, style)
        page = int(entry["page"]) if isinstance(entry["page"], int) else entry["page"]
        # ToC 항목 페이지는 "섹션 시작점"일 뿐 실제 관련 내용은 몇 페이지
        # 뒤에 있을 수 있음 — 문서가 클수록 그 간격도 비례해서 커지는 경향이
        # 있어 총 페이지수에 비례한 허용 오차를 둠 (최소 8, 최대 40).
        total_pages = int(doc.get("total_pages") or 0)
        tolerance = max(8, min(40, total_pages // 25))
        return {
            "id": f"gen-{i:02d}-{str(doc.get('document_id', ''))[:8]}",
            "question": question,
            "style": style,
            "expected": {
                "type": "technical",
                "document": doc.get("filename", ""),
                "pages": [page] if isinstance(page, int) else [1],
                "page_tolerance": tolerance,
            },
        }

    return await asyncio.gather(
        *[_build(i, doc, entry, style) for i, ((doc, entry), style) in enumerate(zip(picks, styles), 1)]
    )


# ─── 진입점 ──────────────────────────────────────────────────────────────────

def _mint_token(user_email: str) -> str:
    """로컬에서 access token을 자체 발급합니다 (EVAL_JWT_SECRET 우선)."""
    from app.config import settings
    eval_secret = _env("EVAL_JWT_SECRET")
    if eval_secret:
        settings.JWT_SECRET = eval_secret
    from app.services.auth_service import create_access_token
    return create_access_token(
        data={"email": user_email, "name": "Eval Runner", "picture": ""},
        expires_delta=timedelta(hours=2),
    )


def main():
    parser = argparse.ArgumentParser(description="TechNote 질문 품질 자동 평가")
    parser.add_argument("--dataset", default=str(EVALS_DIR / "dataset.yaml"), help="골든 데이터셋 YAML 경로")
    parser.add_argument("--only", default=None, help="case id 부분 일치 필터")
    parser.add_argument("--user", default=None, help="문서 소유자 이메일 (defaults.user_email 덮어쓰기)")
    parser.add_argument("--base-url", default=None, help="원격 백엔드 URL (기본: dataset defaults.base_url)")
    parser.add_argument("--local", action="store_true", help="HTTP 대신 로컬 파이프라인 직접 호출")
    parser.add_argument("--token", default=None, help="원격 인증용 access token (기본: EVAL_ACCESS_TOKEN → 자체 발급)")
    parser.add_argument("--judge", action="store_true", help="reference_answer 기반 LLM 채점 활성화")
    parser.add_argument("--generate", type=int, default=0, metavar="N",
                         help="dataset.yaml 대신 실제 매뉴얼 ToC에서 N개 질문을 매번 새로 생성해 실행")
    parser.add_argument("--min-pass", type=float, default=0.0, help="통과율 미달 시 exit 1 (예: 0.8)")
    parser.add_argument("--verbose", action="store_true", help="파이프라인 내부 로그 출력")
    args = parser.parse_args()

    with open(args.dataset, encoding="utf-8") as f:
        dataset = yaml.safe_load(f)
    defaults = dataset.get("defaults", {}) or {}
    if args.user:
        defaults["user_email"] = args.user

    if not args.verbose:
        from app.utils.logger import logger as app_logger
        app_logger.setLevel(logging.WARNING)

    base_url = None if args.local else (args.base_url or defaults.get("base_url"))
    if base_url:
        token = args.token or _env("EVAL_ACCESS_TOKEN") or _mint_token(defaults.get("user_email", ""))
        timeout = float(defaults.get("timeout", 180))
        transport = RemoteTransport(base_url, token, timeout)
        print(f"대상: remote — {base_url}")
    else:
        token = None
        transport = LocalTransport()
        print("대상: local — run_agentic_pipeline 직접 호출")

    if args.generate > 0:
        print(f"실제 매뉴얼 ToC에서 질문 {args.generate}개 생성 중...")
        cases = asyncio.run(generate_cases(args.local, base_url, token, defaults.get("user_email", ""), args.generate))
        if not cases:
            sys.exit(1)
    else:
        cases = dataset.get("cases", []) or []
        if args.only:
            cases = [c for c in cases if args.only in c["id"]]
        if not cases:
            print("실행할 케이스가 없습니다. dataset.yaml 또는 --only 필터를 확인하세요.")
            sys.exit(1)

    # --generate 모드에서는 문서 동등성 판정을 켜서 '중복 문서 / 모델 비종속 일반
    # 질문'으로 인한 가짜 실패를 걸러냅니다.
    equiv_check = args.generate > 0

    results: list[dict] = []

    async def run_all():
        for i, case in enumerate(cases, 1):
            print(f"[{i}/{len(cases)}] {case['id']}: {case['question']}")
            results.append(await run_case(case, defaults, transport, args.judge, equiv_check))

    run_error = None
    try:
        asyncio.run(run_all())
    except KeyboardInterrupt:
        run_error = "KeyboardInterrupt (사용자 중단)"
        print(f"\n⚠ {run_error} — 지금까지의 부분 결과를 저장합니다.")
    except Exception as e:
        run_error = f"{type(e).__name__}: {e}"
        print(f"\n⚠ 실행 중 오류: {run_error} — 지금까지의 부분 결과를 저장합니다.")

    if results:
        _print_report(results)

    # 실행이 중간에 죽더라도 부분 결과와 오류 원인을 반드시 파일로 남깁니다.
    # (기존: 크래시 시 아무 흔적 없이 유실되어 예약 실행 실패 원인 추적 불가)
    RESULTS_DIR.mkdir(exist_ok=True)
    out_path = RESULTS_DIR / f"{datetime.now():%Y%m%d_%H%M%S}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(
            {
                "ran_at": datetime.now().isoformat(),
                "dataset": "generated" if args.generate else args.dataset,
                "target": getattr(transport, "base_url", "local"),
                "cases_planned": len(cases),
                "cases_completed": len(results),
                "error": run_error,
                "results": results,
            },
            f, ensure_ascii=False, indent=2,
        )
    print(f"\n결과 저장: {out_path}")

    if run_error and not results:
        print("실행된 케이스가 없습니다 → 실패 종료")
        sys.exit(1)

    pass_rate = (sum(1 for r in results if r["passed"]) / len(results)) if results else 0.0
    if pass_rate < args.min_pass:
        print(f"통과율 {pass_rate:.0%} < 기준 {args.min_pass:.0%} → 실패 종료")
        sys.exit(1)


if __name__ == "__main__":
    main()
