# 🔧 Vision RAG 리팩토링 계획서

> 작성일: 2026-06-27 · 갱신: 2026-06-29
> 대상: 백엔드(`backend/`) + 프론트엔드(`frontend/`) 전체
> 상태: **전 Phase 완료** — H2·pytest·Phase 5 포함 모든 트랙 완료

본 문서는 기능 고도화가 아닌 **코드 구조·유지보수성 개선**을 위한 리팩토링 로드맵입니다.
기능 요구사항 현황 및 잔여 작업은 [`remaining_tasks.md`](./remaining_tasks.md)를 참고하세요.

---

## 0. ✅ 진행 현황 (2026-06-29)

| Phase | 항목 | 상태 | 커밋 |
|-------|------|------|------|
| 1 | dead code 제거·빈 디렉토리·이중 Depends 정리·`lifespan` 전환·루트 스크래치 정리 | ✅ | `13f224b` |
| 2 | ToC 추출 통합(`build_toc`)·프롬프트 외부화(`app/prompts.py`)·조회 최적화 | ✅ | `13f224b` |
| 3 (C1) | `run_agentic_pipeline` 거대 함수 분해 (596→~58줄, `_PipelineContext`+4 stage) | ✅ | `c9c4503` |
| 4 (M8) | 프론트 공유 타입 추출 (`src/types/`) | ✅ | `13f224b` |
| 4 (M5) | `useChatStream` 훅 분리·`Sidebar` 하위 컴포넌트 분해 | ✅ | `c9c4503` |
| H2 | 동기 GCS I/O → `asyncio.to_thread` 래퍼 (8개 파일, 전 호출처) | ✅ | `6073b36` |
| Phase 4 | `pytest` 단위 테스트 63개 (`_normalize_page`·`_find_section_page_range`·SSE·분류·제조사·ToC) | ✅ | `73de5a1` |
| Phase 5 | Cloud Tasks 큐·Cloud Run 성능 설정·`JWT_SECRET` 하드코딩 제거 | ✅ | `a3745ab` |

**남은 GCP 수동 설정 (Phase 5 배포 적용을 위해 필요)**
> 아래는 코드가 아닌 GCP 콘솔/CLI 작업입니다.

```bash
# 1. Cloud Tasks API 활성화
gcloud services enable cloudtasks.googleapis.com

# 2. 분석 큐 생성 (asia-northeast3 = 서울)
gcloud tasks queues create vision-rag-analysis \
  --location=asia-northeast3 \
  --max-concurrent-dispatches=5 \
  --max-attempts=3

# 3. Cloud Build 치환변수 추가 (GCP 콘솔 > Cloud Build > 트리거 > 변수)
#    _JWT_SECRET          = <기존 JWT 시크릿>
#    _CLOUD_TASKS_QUEUE   = projects/{project}/locations/asia-northeast3/queues/vision-rag-analysis
#    _CLOUD_RUN_URL       = https://vision-rag-backend-xxx.a.run.app
#    _INTERNAL_TASK_SECRET= <새로 생성한 랜덤 문자열>
```

---

## 1. 진단 요약

기능 완성도는 높으나(개선 목록 대부분 완료), **비즈니스 로직이 거대 함수 하나와 중복된 복붙 코드에 묶여 있어** 기능 추가 시 회귀에 취약합니다.

| 항목 | 규모 |
|------|------|
| 백엔드 (Python) | ~5,100줄 |
| 프론트엔드 (TS/TSX) | ~3,100줄 |
| 최대 함수 | `run_agentic_pipeline` **610줄** |
| 최대 컴포넌트 | `Sidebar.tsx` **652줄** |
| 단위 테스트 | 사실상 없음 (`pytest` 미설치, `conftest` 없음) |

---

## 2. 발견된 문제 (근거 포함)

### 🔴 Critical — 구조

| # | 문제 | 위치 | 영향 |
|---|------|------|------|
| C1 | **God function**: `run_agentic_pipeline`이 610줄. 이미지분석·분류·문서선택·페이지선택·Phase2·PDF추출·Vision·저장이 한 함수. SSE `yield`와 `collected_*` 누적이 뒤엉킴 | `services/agentic_graph.py:483-1092` | 흐름 추적·테스트 불가, 수정 시 회귀 위험 |
| C2 | **ToC 추출 로직 복붙**: Case A/B/C 분기가 두 곳에 거의 동일 중복 | `services/pdf_service.py:147-184` ↔ `routers/upload.py:109-132` | 한쪽만 고치면 동작 불일치 |
| C3 | **프롬프트 인라인 중복**: 일반대화 프롬프트가 두 곳에 동일 하드코딩. 모든 LLM 프롬프트가 함수 내부 f-string으로 흩어짐 | `services/agentic_graph.py:634`, `790` 외 | 프롬프트 버전관리·튜닝 불가 |

### 🟠 High — 성능 / 정확성

| # | 문제 | 위치 |
|---|------|------|
| H1 | **불필요한 느린 경로**: `user_email`을 알면서도 `get_document(document_id)`를 인자 없이 호출 → GCS 전체 glob 탐색 발생 | `services/agentic_graph.py:947` |
| H2 | **동기 GCS I/O를 async 컨텍스트에서 직접 호출** (`download_as_text`, `list_blobs`) → 이벤트 루프 블로킹 | `services/metadata_service.py`, `services/conversation_service.py` 전반 |
| H3 | **파이프라인 내 중복 조회**: `get_all_documents`/`get_document`가 한 요청에서 여러 번 호출 | `services/agentic_graph.py:565,662,694,920,947` |

### 🟡 Medium — 위생 / 일관성

| # | 문제 | 위치 |
|---|------|------|
| M1 | **Dead code**: `reason_target_pages`, `render_page_image`, 미사용 `extract_pages_as_pdf` import, `extract_document_title_with_gemini` | `agent_service.py:257`, `pdf_service.py:423`, `agentic_graph.py:16`, `agent_service.py:492` |
| M2 | **이중 의존성 주입**: 라우터 데코레이터 `dependencies=[...]` + 함수 인자 `Depends(get_current_user)`를 **19곳**에서 동시 선언 | 모든 라우터 |
| M3 | **deprecated**: `@app.on_event("startup")` → Lifespan 핸들러로 교체 권장 | `main.py:64` |
| M4 | **빈 죽은 디렉토리**: `src/stores/`, `src/types/`, `src/components/ui` (실제 코드는 `src/store/` 사용) | frontend |
| M5 | **거대 컴포넌트**: `Sidebar.tsx` 652줄, `page.tsx` 460줄 (SSE 파싱 150줄이 컴포넌트에 인라인) | frontend |
| M6 | **루트 스크래치 방치**: `batch_test.py`, `test_chat.py`, `scratch/`, `stich/`, `test_logs/`가 리포 루트에 | 루트 |
| M7 | **조용한 실패**: 거의 모든 함수가 `except: return []/None`으로 에러를 삼킴 → 디버깅 곤란 | 전반 |
| M8 | **프론트 타입 분산**: 타입이 store 파일 내부 정의, API 응답 다수 `any` | `lib/api.ts`, `store/*.ts` |

---

## 3. 리팩토링 로드맵 (4단계, 위험도 오름차순)

### Phase 1 — 안전한 정리 *(위험 낮음 / 예상 반나절)*
- [ ] Dead code 제거 — `reason_target_pages`, `render_page_image`, `extract_document_title_with_gemini`, 미사용 import (M1)
- [ ] 빈 디렉토리 삭제 — `src/stores/`, `src/types/`(추후 재생성), `src/components/ui` (M4)
- [ ] 루트 스크래치 파일 정리 — `scratch/`로 이동 또는 `.gitignore` 등록 (M6)
- [ ] 이중 `Depends` 제거 — 라우터 레벨 `dependencies`만 유지, `current_user`가 실제 필요한 핸들러만 인자 유지 (M2)
- [ ] `@app.on_event("startup")` → `lifespan` 컨텍스트 매니저 전환 (M3)

> **효과**: 즉각적 가독성 향상, 회귀 위험 거의 없음. **여기서 시작 권장.**

### Phase 2 — 중복 제거 *(위험 중간)*
- [ ] **ToC 추출 통합** (C2): Case A/B/C 로직을 `pdf_service.build_toc(doc, total_pages) -> (toc, status)` 단일 함수로 추출 → `process_document_upload`와 `_run_analysis_pipeline` 양쪽에서 호출
- [ ] **프롬프트 외부화** (C3): `app/prompts/` 모듈로 분리(상수 또는 템플릿), 중복 제거 및 버전 관리 가능화
- [ ] **조회 1회화** (H1, H3): 파이프라인 진입 시 문서 메타데이터를 1회 로드해 `user_email`과 함께 전달, 느린 glob 경로 제거

### Phase 3 — 핵심 구조 개선 *(위험 높음 / 핵심)*
- [ ] **`run_agentic_pipeline` 분해** (C1): 단계별 함수로 분리하고 SSE 이벤트는 제너레이터 합성으로 정리

  ```
  pipeline = orchestrator(ctx)
    ├─ stage_image_analysis(ctx)       # Step -1: 이미지 전처리
    ├─ stage_classify_and_select(ctx)  # Phase 1: 분류 + 문서 선택
    ├─ stage_select_pages(ctx)         # Phase 1-2: ToC 기반 페이지 선택
    ├─ stage_refine_text(ctx)          # Phase 2: 텍스트 정밀 탐색
    └─ stage_vision_answer(ctx)        # Phase 3: Vision 분석 + 저장
  ```

  - `collected_answer/reasoning/references`, `_save_conversation`을 `PipelineContext` 객체로 캡슐화
  - 각 stage는 독립적으로 단위 테스트 가능하도록 설계
- [ ] **블로킹 I/O 비동기화** (H2): GCS 동기 호출을 `asyncio.to_thread`로 감싸거나 동기/비동기 경계를 명확히 분리

### Phase 4 — 품질 기반 *(병행 가능)*
- [ ] `pytest` + `conftest.py` 도입, GCS/Gemini 모킹
- [ ] **순수 함수부터 단위 테스트** — `_normalize_page`, `_find_section_page_range`, `normalize_manufacturer`, `is_toc_meaningful`, `_quick_classify` 등 외부 의존 없는 함수 우선
- [ ] 프론트 타입을 `src/types/`로 추출, API 응답 `any` 제거 (M8)
- [ ] `page.tsx`의 SSE 스트리밍 로직을 `useChatStream` 커스텀 훅으로 분리 (M5)
- [ ] `Sidebar.tsx` 분해 — 검색/정렬/트리/팝오버를 하위 컴포넌트로

### Phase 5 — 확장성 / 부하 대응 *(인프라, 리팩토링과 병행)*

> **배경 시나리오**: 초기 사내 오픈 시 동시 **40~50명**이 1인당 **200~300개** 문서(개당 **10~50MB**)를 한꺼번에 업로드하는 피크 상정.

**부하 진단**

| 계층 | 평가 |
|------|------|
| **GCS 저장/업로드** | ✅ 문제없음. 총 ~400~750GB(서울 리전 월 $11~17), 브라우저→GCS **Direct 업로드**라 서버 메모리 우회 |
| **Gemini API** | ⚠️ 12,500문서 × 2~4호출 = 2.5만~5만 호출. 1티어로 완충되나 피크 시 rate limit 가능 → 큐로 평탄화 |
| **Cloud Run + BackgroundTasks** | 🔴 **진짜 병목.** 인메모리 백그라운드 작업이 인스턴스에 묶임/유실, CPU 미할당 시 중단, 동기 PDF 처리 블로킹·`/tmp`(tmpfs) 메모리 압박 |

**작업 항목**
- [ ] **단일 버킷 유지 확정** — per-user 버킷 미채택 (사용자 간 충돌은 경로 prefix로 이미 0, 과부하 방지 효과 없음, 버킷 생성 rate limit이라는 새 병목만 추가)
- [ ] **Cloud Run 배포 설정** — `CPU always allocated` ON, 메모리 2GB+, `min-instances ≥ 1`, `concurrency` 4~8 (`cloudbuild.yaml`/배포 명령 반영)
- [ ] **분석 파이프라인 BackgroundTasks → Cloud Tasks 큐 이전** — 인스턴스 유실 시 재시도, 처리율 조절로 Gemini rate limit 동시 완충, 진행상황 추적
- [ ] **동기 GCS/PyMuPDF I/O 비동기화** — H2와 통합 진행
- [ ] (선택) `metadata.json`/`conversation.json` 동시 쓰기에 generation precondition 낙관적 락

> ⚙️ 코드·설정 파일은 일괄 작성 가능하나, Cloud Tasks 큐 생성·IAM·Cloud Run 재배포는 GCP 인증이 필요하여 배포 단계는 수동 실행으로 병행한다.

---

## 4. 추천 시작점

**Phase 1 + Phase 2의 ToC 통합(C2)** 조합을 권장.
위험이 낮으면서 "복붙 코드 한쪽만 수정되는" 가장 실질적인 버그 위험을 제거하고, Phase 3의 큰 수술을 위한 정리가 된다.

## 5. 진행 원칙

- 각 Phase는 독립 커밋/PR 단위로 분리하여 회귀 추적 가능하게.
- Phase 3 착수 전 Phase 4의 순수 함수 테스트를 먼저 확보하면 안전망 역할.
- 기능 동작(특히 SSE 이벤트 계약)은 변경하지 않는다 — 순수 구조 리팩토링.

---

> ⚠️ 본 문서는 계획 단계이며, 실제 코드 변경은 별도 작업으로 진행한다.
