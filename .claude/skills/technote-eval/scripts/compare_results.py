#!/usr/bin/env python3
"""TechNote eval 결과 이력 비교 (backend/evals/results/*.json).

축별 통과율 추이와 실패 상세를 뽑아, 전체 통과율만 보고 오판하는 것을 막습니다.
`--generate` 실행은 매번 질문이 새로 합성되므로 케이스 단위 비교가 성립하지 않고,
축별 비율로만 비교합니다. 고정 데이터셋(dataset.yaml / claude_dataset.yaml)은
case id가 안정적이라 케이스 단위 diff를 합니다.

사용법:
    python3 compare_results.py                  # 최근 10회 추이
    python3 compare_results.py --last 5
    python3 compare_results.py --diff           # 최신 vs 직전 (같은 데이터셋끼리)
    python3 compare_results.py --diff A.json B.json
    python3 compare_results.py --failures       # 최신 실행의 실패 상세
    python3 compare_results.py --results-dir <경로>
"""
import argparse
import json
import statistics
import sys
from pathlib import Path

CORE_AXES = ["routing", "document"]  # 신뢰도 높은 축
NOISY_AXES = ["pages"]               # 근사 정답 기반 — 참고용


def find_results_dir(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit).expanduser()
        if not p.is_dir():
            sys.exit(f"결과 디렉토리가 없습니다: {p}")
        return p
    cur = Path.cwd().resolve()
    for base in [cur, *cur.parents]:
        for cand in (base / "backend" / "evals" / "results",
                     base / "evals" / "results",
                     base / "results"):
            if cand.is_dir():
                return cand
    sys.exit("results 디렉토리를 찾지 못했습니다. --results-dir로 지정하세요.")


def load_run(path: Path) -> dict:
    try:
        d = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as e:
        return {"_path": path, "_broken": str(e), "results": []}
    d["_path"] = path
    return d


def load_runs(results_dir: Path) -> list[dict]:
    runs = [load_run(p) for p in sorted(results_dir.glob("*.json"))]
    return [r for r in runs if r.get("results") and not r.get("_broken")]


def dataset_label(run: dict) -> str:
    """generated / dataset.yaml / claude_dataset.yaml 등으로 정규화."""
    ds = run.get("dataset") or "?"
    return ds if ds == "generated" else Path(ds).name


def axis_stats(run: dict) -> dict[str, list[bool]]:
    ax: dict[str, list[bool]] = {}
    for r in run["results"]:
        for name, c in (r.get("checks") or {}).items():
            ax.setdefault(name, []).append(bool(c.get("pass")))
    return ax


def style_stats(run: dict) -> dict[str, dict]:
    by: dict[str, dict] = {}
    for r in run["results"]:
        s = r.get("style")
        if not s:
            continue
        b = by.setdefault(s, {"n": 0, "doc": 0})
        b["n"] += 1
        if (r.get("checks") or {}).get("document", {}).get("pass"):
            b["doc"] += 1
    return by


def classify_doc_failure(detail: str) -> str:
    """document 실패의 성격을 detail 문자열에서 판별합니다.

    러너가 detail에 남기는 표기:
      - '실오답 확인'  → 동등성 판정에서도 불인정된 진짜 오답
      - '되묻기 후보에 소스 누락' → 검색이 후보로도 못 띄움 (recall 문제)
      - '되묻기 후보에 소스 포함' → 후보엔 떴는데 자동선택이 틀림 (precision 문제)
    """
    if "실오답" in detail:
        base = "실오답 확인"
    else:
        base = "실패"
    if "누락" in detail:
        return f"{base} / recall(후보에도 없음)"
    if "포함" in detail:
        return f"{base} / precision(후보엔 있었음)"
    return base


def fmt_rate(passed: int, total: int) -> str:
    if not total:
        return "  -  "
    return f"{passed:>2}/{total:<2}"


def print_trend(runs: list[dict], last: int) -> None:
    if not runs:
        print("결과 파일이 없습니다.")
        return

    by_ds: dict[str, list[dict]] = {}
    for r in runs:
        by_ds.setdefault(dataset_label(r), []).append(r)

    # 최근에 돌린 데이터셋부터 — 일회성 스크래치 데이터셋이 위로 올라오지 않도록
    ordered = sorted(by_ds.items(), key=lambda kv: kv[1][-1]["_path"].stem, reverse=True)

    for ds, rs in ordered:
        rs = rs[-last:]
        print(f"\n■ 데이터셋: {ds}   (최근 {len(rs)}회)")
        print(f"  {'실행':<16} {'n':>3}  {'routing':>8} {'document':>9} {'pages':>7}  {'전체':>7}  평균지연")
        print("  " + "-" * 68)
        for r in rs:
            ax = axis_stats(r)
            res = r["results"]
            n = len(res)
            overall = sum(1 for x in res if x.get("passed"))
            lats = [x.get("latency_sec", 0) for x in res if x.get("latency_sec")]
            avg = f"{statistics.mean(lats):.0f}s" if lats else "-"
            cells = []
            for a in ("routing", "document", "pages"):
                v = ax.get(a, [])
                cells.append(fmt_rate(sum(v), len(v)))
            print(f"  {r['_path'].stem:<16} {n:>3}  {cells[0]:>8} {cells[1]:>9} {cells[2]:>7}  "
                  f"{fmt_rate(overall, n):>7}  {avg:>6}")

        # 핵심 축 요약 — 전체 통과율의 흔들림이 pages 때문인지 판별
        core_perfect = all(
            all(axis_stats(r).get(a, [True])) for r in rs for a in CORE_AXES
        )
        if core_perfect and len(rs) > 1:
            print("\n  → 이 구간 routing·document는 전부 만점입니다. "
                  "전체 통과율의 변동은 pages(근사 지표) 때문이므로 품질 저하로 읽지 마세요.")


def diff_generated(new: dict, old: dict) -> None:
    """생성 데이터셋: 질문이 매번 달라 케이스 비교 불가 → 축별 비율만 비교."""
    print("\n■ 축별 비교 (생성 질문은 매 실행 새로 합성되므로 케이스 단위 비교는 불가)")
    na, oa = axis_stats(new), axis_stats(old)
    print(f"  {'축':<12} {'이전':>8} {'최신':>8}   변화")
    print("  " + "-" * 44)
    for a in sorted(set(na) | set(oa)):
        nv, ov = na.get(a, []), oa.get(a, [])
        nr = sum(nv) / len(nv) if nv else 0
        orr = sum(ov) / len(ov) if ov else 0
        delta = (nr - orr) * 100
        arrow = "→" if abs(delta) < 1 else ("▲" if delta > 0 else "▼")
        tag = "  (참고용 지표)" if a in NOISY_AXES else ""
        print(f"  {a:<12} {fmt_rate(sum(ov), len(ov)):>8} {fmt_rate(sum(nv), len(nv)):>8}   "
              f"{arrow} {delta:+.0f}%p{tag}")


def diff_fixed(new: dict, old: dict) -> None:
    """고정 데이터셋: case id가 안정적이므로 케이스 단위로 비교."""
    nmap = {r["id"]: r for r in new["results"]}
    omap = {r["id"]: r for r in old["results"]}
    shared = sorted(set(nmap) & set(omap))
    broke = [i for i in shared if omap[i].get("passed") and not nmap[i].get("passed")]
    fixed = [i for i in shared if not omap[i].get("passed") and nmap[i].get("passed")]

    print(f"\n■ 케이스 단위 비교 (공통 {len(shared)}건)")
    print(f"  새로 깨진 케이스: {len(broke)}건 / 새로 통과한 케이스: {len(fixed)}건")
    for i in broke:
        r = nmap[i]
        print(f"\n  ❌ {i}")
        print(f"     질문: {r.get('question', '')[:80]}")
        for name, c in (r.get("checks") or {}).items():
            if not c.get("pass"):
                print(f"     ✗ {name}: {c.get('detail', '')[:160]}")
    if fixed:
        print(f"\n  ✅ 새로 통과: {', '.join(fixed[:20])}")


def print_failures(run: dict) -> None:
    """최신 실행의 실패를 축별 신뢰도에 맞춰 정리합니다."""
    res = run["results"]
    print(f"\n■ 실패 상세 — {run['_path'].stem} (dataset={dataset_label(run)}, n={len(res)})")

    doc_fails = []
    routing_fails = []
    page_fail_n = 0
    for r in res:
        checks = r.get("checks") or {}
        if not checks.get("routing", {}).get("pass", True):
            routing_fails.append(r)
        d = checks.get("document")
        if d and not d.get("pass"):
            doc_fails.append(r)
        p = checks.get("pages")
        if p and not p.get("pass"):
            page_fail_n += 1

    # '실제 error'는 라우팅 판단이 틀린 게 아니라 케이스 자체가 죽은 것(HTTP 401/타임아웃 등).
    # 품질 저하로 읽으면 안 되고 실행 환경 문제로 다뤄야 해서 분리합니다.
    errored = [r for r in routing_fails if "error" in r["checks"]["routing"].get("detail", "")]
    misrouted = [r for r in routing_fails if r not in errored]

    if errored:
        print(f"\n  ⚠ 실행 오류 {len(errored)}건 — 라우팅 판단이 아니라 케이스가 죽은 것입니다"
              f" (HTTP 401/타임아웃 등). 채점 결과로 해석하지 말고 원인부터 확인하세요.")
        for r in errored[:5]:
            errs = r.get("errors") or []
            print(f"    - {r['id']}: {(errs[0] if errs else '')[:120]}")
        if len(errored) > 5:
            print(f"    … 외 {len(errored) - 5}건")

    if misrouted:
        print(f"\n  ▶ routing 실패 {len(misrouted)}건 — 신뢰도 높은 축, 반드시 원인 확인")
        for r in misrouted[:15]:
            print(f"    - {r['id']} [{r.get('style', '-')}] {r.get('question', '')[:70]}")
            print(f"      {r['checks']['routing'].get('detail', '')}")
        if len(misrouted) > 15:
            print(f"    … 외 {len(misrouted) - 15}건")
    elif not errored:
        print("\n  ▶ routing: 실패 없음")

    if doc_fails:
        print(f"\n  ▶ document 실패 {len(doc_fails)}건 — 동등성 판정에서도 걸러지지 않은 건들")
        for r in doc_fails[:20]:
            detail = r["checks"]["document"].get("detail", "")
            print(f"    - {r['id']} [{r.get('style', '-')}] {classify_doc_failure(detail)}")
            print(f"      질문: {r.get('question', '')[:70]}")
            print(f"      {detail[:200]}")
        if len(doc_fails) > 20:
            print(f"    … 외 {len(doc_fails) - 20}건")
    else:
        print("  ▶ document: 실패 없음")

    if page_fail_n:
        print(f"\n  ▶ pages 실패 {page_fail_n}건 — ToC 위치 기반 근사 지표라 노이즈가 큽니다. "
              "통과율만 언급하고 개별 나열은 하지 마세요.")

    st = style_stats(run)
    if len(st) > 1:
        print("\n  ▶ 문체별 document 통과율")
        for s, b in sorted(st.items()):
            print(f"    - {s:<9} {b['doc']}/{b['n']}")
        terse, sent = st.get("terse"), st.get("sentence")
        if terse and sent and terse["n"] and sent["n"]:
            tr, sr = terse["doc"] / terse["n"], sent["doc"] / sent["n"]
            if sr - tr >= 0.2:
                print("    → terse(키워드 나열형)가 문장형보다 눈에 띄게 낮습니다: "
                      "키워드 빈약 입력에서 문서선택이 약하다는 신호입니다.")


def main() -> None:
    ap = argparse.ArgumentParser(description="TechNote eval 결과 이력 비교")
    ap.add_argument("--results-dir", default=None)
    ap.add_argument("--last", type=int, default=10, help="추이에 표시할 실행 수 (기본 10)")
    ap.add_argument("--dataset", default=None,
                    help="데이터셋 필터 (예: generated, claude_dataset.yaml). 부분 일치")
    ap.add_argument("--diff", nargs="*", metavar="JSON",
                    help="두 실행 비교. 인자 없으면 같은 데이터셋의 최신 vs 직전")
    ap.add_argument("--failures", action="store_true", help="최신 실행의 실패 상세")
    args = ap.parse_args()

    results_dir = find_results_dir(args.results_dir)
    runs = load_runs(results_dir)
    if not runs:
        sys.exit(f"유효한 결과 파일이 없습니다: {results_dir}")

    total_n = len(runs)
    if args.dataset:
        runs = [r for r in runs if args.dataset in dataset_label(r)]
        if not runs:
            sys.exit(f"'{args.dataset}'와 일치하는 데이터셋 실행이 없습니다.")

    print(f"결과 디렉토리: {results_dir}  (총 {total_n}개 실행"
          + (f", 필터 '{args.dataset}' → {len(runs)}개)" if args.dataset else ")"))

    if args.diff is not None:
        if len(args.diff) == 2:
            new, old = load_run(Path(args.diff[1])), load_run(Path(args.diff[0]))
        else:
            latest = runs[-1]
            ds = dataset_label(latest)
            same = [r for r in runs if dataset_label(r) == ds]
            if len(same) < 2:
                sys.exit(f"같은 데이터셋({ds}) 실행이 2회 미만이라 비교할 수 없습니다.")
            new, old = same[-1], same[-2]
        print(f"\n비교: {old['_path'].stem} (이전)  →  {new['_path'].stem} (최신)")
        if dataset_label(new) == "generated" or dataset_label(new) != dataset_label(old):
            diff_generated(new, old)
        else:
            diff_fixed(new, old)
        print_failures(new)
        return

    if args.failures:
        print_failures(runs[-1])
        return

    print_trend(runs, args.last)


if __name__ == "__main__":
    main()
