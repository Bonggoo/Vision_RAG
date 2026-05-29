#!/usr/bin/env python3
"""
Vision RAG 답변 품질 및 성능 분석 테스트 스크립트.

이 스크립트는 doc/질문.md (100개 정밀 질문) 및 doc/질문2.md (50개 대충 입력한 현장 질문)을 파싱하여,
배포된 Cloud Run 서버 또는 로컬 서버에 비동기 병렬(Semaphore) 질의를 전달하고,
그 결과를 실시간 로깅 및 JSON/마크다운 종합 분석 리포트로 출력합니다.
"""

import os
import re
import sys
import json
import time
import asyncio
import argparse
from datetime import datetime
from typing import List, Dict, Any, Optional

import httpx

# 기본 설정값
DEFAULT_SERVER = "https://vision-rag-backend-1023361734160.asia-northeast3.run.app"
DEFAULT_CONCURRENCY = 3
DEFAULT_OUTPUT_DIR = "/Users/choibonggoo/Worksapce/Vision_RAG/backend/test_reports"

# 마크다운 파싱 정규식
SECTOR_PATTERN = re.compile(r"^\[(.*)\]$")
QUESTION_PATTERN = re.compile(r"^\d+\.\s+(.*)$")


class QualityTestRunner:
    def __init__(self, server_url: str, concurrency: int, output_dir: str):
        self.server_url = server_url.rstrip("/")
        self.concurrency = concurrency
        self.output_dir = output_dir
        self.semaphore = asyncio.Semaphore(concurrency)
        self.print_lock = asyncio.Lock()  # 콘솔 실시간 로깅이 꼬이지 않기 위한 락

        # 결과 리포트 저장용 폴더 생성
        os.makedirs(self.output_dir, exist_ok=True)

    def parse_questions(self, file_path: str, file_type: int) -> List[Dict[str, Any]]:
        """마크다운 파일에서 질문을 파싱하여 정형화된 리스트로 반환합니다."""
        if not os.path.exists(file_path):
            print(f"❌ 파일을 찾을 수 없습니다: {file_path}")
            return []

        questions = []
        current_category = "미분류"
        file_name = os.path.basename(file_path)

        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                # 카테고리/섹션 감지 (예: [로보스타 (Robostar)] 또는 [1. 다짜고짜 에러/알람 코드만 던지기])
                sector_match = SECTOR_PATTERN.match(line)
                if sector_match:
                    current_category = sector_match.group(1).strip()
                    continue

                # 질문 라인 감지 (예: 1. E011 뜸. 어떻게 함?)
                q_match = QUESTION_PATTERN.match(line)
                if q_match:
                    q_text = q_match.group(1).strip()
                    questions.append({
                        "file_source": file_name,
                        "file_type": file_type,
                        "category": current_category,
                        "question": q_text
                    })

        print(f"📖 {file_name} 파싱 완료: {len(questions)}개 질문 추출됨. (카테고리: {current_category})")
        return questions

    async def check_server_health(self) -> bool:
        """테스트 시작 전 대상 API 서버의 상태를 체크합니다."""
        async with httpx.AsyncClient() as client:
            try:
                resp = await client.get(f"{self.server_url}/", timeout=10.0)
                if resp.status_code == 200:
                    data = resp.json()
                    print(f"✅ 서버 연결 확인 성공! ({self.server_url}) - 메시지: {data.get('message', '')}")
                    return True
                else:
                    print(f"❌ 서버 응답 에러: Status {resp.status_code}")
                    return False
            except Exception as e:
                print(f"❌ 서버 연결 실패 ({self.server_url}): {e}")
                return False

    async def run_single_question(self, index: int, total: int, item: Dict[str, Any]) -> Dict[str, Any]:
        """단일 질문에 대해 비동기적으로 백엔드에 질의하고 SSE 응답을 파싱합니다."""
        question = item["question"]
        file_source = item["file_source"]
        category = item["category"]

        async with self.semaphore:
            start_time = time.time()
            answer_parts = []
            reasoning_parts = []
            references = []
            error_msg = None
            status = "FAIL"

            async with self.print_lock:
                print(f"🚀 [{index}/{total}] 질의 시작 ({file_source} | {category}): {question[:40]}...")
                sys.stdout.flush()

            try:
                # SSE 엔드포인트 POST 요청
                # Timeout은 RAG 추론을 위해 넉넉히 180초 지정
                async with httpx.AsyncClient(timeout=180.0) as client:
                    async with client.stream(
                        "POST",
                        f"{self.server_url}/chat/stream",
                        json={"question": question, "document_id": None, "chat_history": []}
                    ) as response:
                        if response.status_code != 200:
                            error_msg = f"HTTP Error Status {response.status_code}"
                        else:
                            # Stream 라인 바이 라인 읽기
                            async for line in response.aiter_lines():
                                if not line.startswith("data: "):
                                    continue
                                raw_data = line[6:]
                                try:
                                    obj = json.loads(raw_data)
                                except json.JSONDecodeError:
                                    continue

                                evt_type = obj.get("type", "")
                                content = obj.get("content", "")

                                if evt_type == "answer":
                                    answer_parts.append(content)
                                elif evt_type == "reasoning":
                                    reasoning_parts.append(content)
                                elif evt_type == "reference":
                                    # 레퍼런스는 페이지 번호 등을 저장
                                    page_info = {
                                        "page_number": obj.get("page_number"),
                                        "document_title": obj.get("document_title", "Unknown")
                                    }
                                    if page_info not in references:
                                        references.append(page_info)
                                elif evt_type == "error":
                                    error_msg = content
                                elif evt_type == "done":
                                    break

            except Exception as e:
                error_msg = str(e)

            elapsed = time.time() - start_time
            answer = "".join(answer_parts).strip()
            reasoning = "".join(reasoning_parts).strip()

            # 성공 판정: 에러가 없고, 답변의 길이가 최소 30자 이상일 때
            if not error_msg and len(answer) >= 30:
                status = "SUCCESS"

            # 콘솔 실시간 로깅 동기화 출력
            async with self.print_lock:
                status_icon = "✅" if status == "SUCCESS" else "❌"
                ref_pages = [r.get("page_number") for r in references if r.get("page_number") is not None]
                print(f"⏱️  [{index}/{total}] 완료 ({status_icon}) | 시간: {elapsed:.1f}초 | 답변: {len(answer)}자 | 참조페이지: {ref_pages}")
                if error_msg:
                    print(f"    ⚠️ 에러: {error_msg}")
                sys.stdout.flush()

            return {
                "index": index,
                "file_source": file_source,
                "category": category,
                "question": question,
                "answer": answer,
                "reasoning": reasoning,
                "references": references,
                "latency_seconds": round(elapsed, 2),
                "status": status,
                "error": error_msg
            }

    async def run_all_tests(self, questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """비동기 Task들을 생성하여 Semaphore 제어 속에 전수 테스트를 실행합니다."""
        total = len(questions)
        print(f"\n⚡ 총 {total}개의 질문 테스트를 동시성 {self.concurrency}으로 병렬 실행합니다.")
        print(f"⌛ RAG 추론 속도 및 실서버 리소스에 따라 수 분 이상 소요될 수 있습니다...\n")
        
        tasks = []
        for idx, item in enumerate(questions, 1):
            tasks.append(self.run_single_question(idx, total, item))

        results = await asyncio.gather(*tasks)
        return results

    def generate_reports(self, results: List[Dict[str, Any]], start_time_str: str, elapsed_total: float):
        """테스트 통계를 분석하여 JSON 로그 및 마크다운 종합 품질 분석 리포트를 생성합니다."""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        
        total_questions = len(results)
        success_count = sum(1 for r in results if r["status"] == "SUCCESS")
        fail_count = total_questions - success_count
        success_rate = (success_count / total_questions) * 100 if total_questions > 0 else 0
        
        latencies = [r["latency_seconds"] for r in results if r["status"] == "SUCCESS"]
        avg_latency = sum(latencies) / len(latencies) if latencies else 0
        max_latency = max([r["latency_seconds"] for r in results]) if results else 0
        min_latency = min([r["latency_seconds"] for r in results]) if results else 0

        # 카테고리(제조사/질문유형)별 통계 산출
        category_stats = {}
        for r in results:
            cat = r["category"]
            file_src = r["file_source"]
            key = f"{file_src} - {cat}"
            if key not in category_stats:
                category_stats[key] = {"total": 0, "success": 0, "latencies": []}
            
            category_stats[key]["total"] += 1
            if r["status"] == "SUCCESS":
                category_stats[key]["success"] += 1
                category_stats[key]["latencies"].append(r["latency_seconds"])

        # 1. JSON 파일 저장
        json_path = os.path.join(self.output_dir, f"report_{timestamp}.json")
        report_data = {
            "metadata": {
                "test_date": start_time_str,
                "target_server": self.server_url,
                "concurrency": self.concurrency,
                "total_questions": total_questions,
                "success_count": success_count,
                "fail_count": fail_count,
                "success_rate_percent": round(success_rate, 2),
                "avg_latency_seconds": round(avg_latency, 2),
                "total_elapsed_seconds": round(elapsed_total, 2)
            },
            "category_summary": {
                k: {
                    "total": v["total"],
                    "success": v["success"],
                    "success_rate": round((v["success"] / v["total"]) * 100, 2),
                    "avg_latency": round(sum(v["latencies"]) / len(v["latencies"]), 2) if v["latencies"] else 0
                } for k, v in category_stats.items()
            },
            "details": results
        }
        with open(json_path, "w", encoding="utf-8") as jf:
            json.dump(report_data, jf, ensure_ascii=False, indent=2)

        # 2. 마크다운 보고서 생성
        md_path = os.path.join(self.output_dir, f"report_{timestamp}.md")
        with open(md_path, "w", encoding="utf-8") as mf:
            mf.write(f"# 📊 Vision RAG 답변 품질 및 성능 분석 종합 리포트\n\n")
            mf.write(f"> **본 리포트는 질문의 난이도 및 형태(정밀 질문 vs 급박한 대충 질문)에 따른 RAG 답변 매칭률 및 품질을 실시간 검증한 결과입니다.**\n\n")
            
            # 메타데이터 표
            mf.write(f"### 📋 테스트 개요\n")
            mf.write(f"| 항목 | 상세 정보 |\n")
            mf.write(f"| :--- | :--- |\n")
            mf.write(f"| **테스트 일시** | {start_time_str} |\n")
            mf.write(f"| **대상 API 서버** | `{self.server_url}` |\n")
            mf.write(f"| **병렬 동시 요청 수** | `{self.concurrency}` 개의 동시 채널 |\n")
            mf.write(f"| **총 테스트 소요 시간** | `{elapsed_total:.1f}` 초 (약 `{elapsed_total/60:.1f}` 분) |\n")
            mf.write(f"| **총 질문 수** | **{total_questions}** 개 |\n")
            mf.write(f"| **최종 성공률** | **{success_rate:.2f}%** ({success_count} / {total_questions}) |\n")
            mf.write(f"| **평균 답변 지연 시간** | `{avg_latency:.2f}` 초 (최소 `{min_latency:.1f}`초 ~ 최대 `{max_latency:.1f}`초) |\n\n")

            # 카테고리 통계 표
            mf.write(f"### 🏷️ 카테고리 및 질문 유형별 품질 분석\n\n")
            mf.write(f"| 질문 출처 및 카테고리 | 총 질문 수 | 성공 건수 | 성공률 | 평균 지연 시간 (초) |\n")
            mf.write(f"| :--- | :---: | :---: | :---: | :---: |\n")
            for k, v in sorted(category_stats.items()):
                tot = v["total"]
                suc = v["success"]
                rate = (suc / tot) * 100
                avg_l = sum(v["latencies"]) / len(v["latencies"]) if v["latencies"] else 0
                mf.write(f"| {k} | {tot} | {suc} | **{rate:.1f}%** | {avg_l:.2f}s |\n")
            mf.write("\n")

            # 실패 질문 리스트 (트러블슈팅 용도)
            if fail_count > 0:
                mf.write(f"### ⚠️ 답변 생성 실패 질문 목록 ({fail_count}건)\n")
                mf.write(f"> RAG 서버 내부 오류 또는 에러가 발생했거나, 최종 답변이 30자 이하로 부실하게 작성된 질문들입니다.\n\n")
                mf.write(f"| 순번 | 출처 - 카테고리 | 질문 내용 | 지연시간 | 에러/실패 원인 |\n")
                mf.write(f"| :---: | :--- | :--- | :---: | :--- |\n")
                for r in results:
                    if r["status"] == "FAIL":
                        err = r["error"] if r["error"] else "답변 30자 미만 (부실 응답)"
                        mf.write(f"| {r['index']} | {r['file_source']} - {r['category']} | {r['question']} | {r['latency_seconds']}s | <font color='red'>{err}</font> |\n")
                mf.write("\n")

            # 상세 테스트 결과 (Carousels 형태 또는 리스트 형태로 가독성 극대화)
            mf.write(f"### 📝 상세 질의응답 로그 (성공 건 중 주요 30자 미리보기)\n")
            mf.write(f"다음은 개별 질문에 대한 백엔드 RAG의 응답 결과 요약입니다.\n\n")
            mf.write(f"| 순번 | 상태 | 카테고리 | 질문 | 답변 요약 (마크다운) | 참조 페이지 |\n")
            mf.write(f"| :---: | :---: | :--- | :--- | :--- | :--- |\n")
            for r in results:
                status_lbl = "🟢 성공" if r["status"] == "SUCCESS" else "🔴 실패"
                preview = r["answer"].replace("\n", " ")[:120] + "..." if r["answer"] else "-"
                ref_pages = ", ".join([f"P{item.get('page_number')}" for item in r["references"] if item.get('page_number') is not None])
                if not ref_pages:
                    ref_pages = "없음"
                mf.write(f"| {r['index']} | {status_lbl} | {r['category']} | {r['question']} | {preview} | {ref_pages} |\n")

        print(f"\n🎉 분석 리포트 생성이 완료되었습니다!")
        print(f"  📂 JSON 원시 로그: {json_path}")
        print(f"  📂 마크다운 종합 리포트: {md_path}")


async def async_main():
    parser = argparse.ArgumentParser(description="Vision RAG 답변 품질 측정 도구")
    parser.add_argument("--server", type=str, default=DEFAULT_SERVER, help="대상 백엔드 API 주소")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY, help="비동기 병렬 요청 수")
    parser.add_argument("--file", type=str, default="both", choices=["1", "2", "both"], help="테스트할 질문 파일 (1: 질문.md, 2: 질문2.md, both: 둘 다)")
    parser.add_argument("--limit", type=int, default=None, help="테스트할 질문 개수 제한 (기본: 전체)")
    parser.add_argument("--output-dir", type=str, default=DEFAULT_OUTPUT_DIR, help="리포트 파일 저장 폴더")
    
    args = parser.parse_args()

    # 경로 정의
    workspace_root = "/Users/choibonggoo/Worksapce/Vision_RAG"
    q_file1 = os.path.join(workspace_root, "doc/질문.md")
    q_file2 = os.path.join(workspace_root, "doc/질문2.md")

    runner = QualityTestRunner(
        server_url=args.server,
        concurrency=args.concurrency,
        output_dir=args.output_dir
    )

    # 1. 서버 헬스체크 우선 수행
    print(f"🌐 [1/3] 대상 백엔드 서버 헬스체크 중...")
    if not await runner.check_server_health():
        print("❌ 대상 서버가 활성화되어 있지 않아 테스트를 시작할 수 없습니다. 서버 상태를 확인해주세요.")
        sys.exit(1)

    # 2. 질문 파싱
    print(f"\n📖 [2/3] 질문 파일 마크다운 파싱 중...")
    questions = []
    if args.file == "1" or args.file == "both":
        questions.extend(runner.parse_questions(q_file1, file_type=1))
    if args.file == "2" or args.file == "both":
        questions.extend(runner.parse_questions(q_file2, file_type=2))

    if not questions:
        print("❌ 파싱된 질문이 없습니다. 질문 파일 경로를 확인해주세요.")
        sys.exit(1)

    # 제한 옵션 반영
    if args.limit and args.limit > 0:
        print(f"⚠️ [제한 적용] 전체 {len(questions)}개 중 상위 {args.limit}개 질문만 테스트를 수행합니다.")
        questions = questions[:args.limit]

    # 3. 비동기 테스트 실행
    print(f"\n🚀 [3/3] 품질 테스트 실행 단계 돌입")
    start_time_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    start_perf = time.time()

    # asyncio.run()에 의해 이벤트 루프 상에서 직접 비동기 수행
    results = await runner.run_all_tests(questions)

    elapsed_total = time.time() - start_perf

    # 4. 리포트 생성 및 저장
    runner.generate_reports(results, start_time_str, elapsed_total)


def main():
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("\n⚠️ 사용자에 의해 테스트가 중단되었습니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
