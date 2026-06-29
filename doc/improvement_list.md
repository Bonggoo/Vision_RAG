# 📑 Vision RAG 개선 및 고도화 요구사항 정의서 (최신화)

본 문서는 프로젝트의 개선 요구사항에 대한 반영 현황 및 향후 고도화 로드맵을 정의합니다.

---

## 1. 🔒 보안과 사용자 (Security & Users) - ✅ 완료
* **[x] 로그인 과정 자연스럽게**
  * `useAuthStore` 기반의 자체 JWT Access/Refresh 토큰 갱신 로직을 설계하여 무중단 사용자 경험 구현
  * 비로그인 상태 가드 리다이렉트 처리 완료
* **[x] 구글 OAuth 계정 정리 및 연동**
  * 프로덕션 서버와 로컬 환경 간 구글 API 및 JWT 인증 키 설정 통합 및 환경변수 최신화
* **[x] 화이트리스트 및 권한 관리 시스템 구현**
  * 화이트리스트 기반 접근 제어 API 구현 완료
  * 사용자 이메일(`owner_email`) 단위의 데이터베이스 격리 필터(멀티테넌시)를 백엔드와 프론트엔드 전체에 적용하여 보안 강화 완료

## 2. ⚡ 코어 기능 (Core Performance) - ✅ 완료
* **[x] 대화 품질 테스트 진행**
  * **AI 자동 평가 및 벤치마크**: `doc/질문.md` 기반 대화 품질 테스트 프로그램을 실행하여 최종 성공률 **93.33%** 리포트 확정
  * **수동 & 출력 검증**: httpx ReadError 방어 코드 및 PDF 페이지 슬라이싱 최적화 등을 교차 검증 완료
* **[x] 성능 및 기능 개선**
  * **속도 개선**: Step 0 + Phase 0+1을 1회 LLM 호출로 병합하고 Phase 2를 비동기화하여 응답 지연을 **~3초 이상 대폭 절감**
  * **매뉴얼 코드 반영**: AI 답변 중 근거가 되는 타겟 페이지를 탐색하여 썸네일 레퍼런스 이미지(Base64)와 함께 페이지 정보 명시
  * **대화 중 모바일 이미지 전송**: 대화창 내부에서 현장 장비 알람 이미지를 카메라/갤러리로 첨부하여 Gemini Vision으로 RAG 분석하는 전처리 파이프라인 구축 완료
* **[x] 추론 정확도 고도화**
  * **되묻기(Clarification)**: 1차 문서 선택 확신도가 낮거나 상위 2개 문서 간 점수 차이가 모호한 경우, SSE `clarification` 이벤트로 사용자에게 장비 선택 UI를 띄우고, 선택 시 질문을 자동 보강하여 정밀 재탐색 수행
  * **대화 맥락 유지(Previous Reference)**: 직전 답변의 참조 문서 ID와 페이지를 다음 `ChatRequest`에 포함하여, 꼬리 질문 시 동일 매뉴얼 내 탐색 정확도 향상
  * **1차 필터링 강화**: 문서 메타데이터(파일명, 제조사, 모델명)를 1차 LLM 필터에 포함하고, 한-영 기술 용어 동의어 매핑 적용하여 토큰 비용 90% 이상 절감
* **[x] 대화 세션 GCS 영속 저장**
  * 로컬스토리지 `persist` 의존성을 완전 제거하고 GCS(`users/{email}/conversations/{session_id}.json`)에 대화 히스토리 저장
  * 대화 목록 조회, 생성, 삭제, 상세 로딩, 제목 수정 기능(`/conversations/` 라우터) 구현 완료
  * 첫 메시지 스트리밍 `done` 수신 시 백엔드에서 자동 GCS 영속화

## 3. 📂 파일 관리 기능 (File Management) - ✅ 완료
* **[x] 문서 관리 및 편집 기능 고도화**
  * 사이드바 팝오버를 통해 업로드된 문서를 개별 **삭제**, **다운로드**(RFC 5987 준수), **메타데이터(파일명, 제조사, 모델) 인라인 수정** 기능 전면 제공
  * 제조사 및 모델 시리즈 미분류 문서 일괄 Vision 재분류 API 구현 완료
* **[x] 업로드 개선 및 프로그레스 바 적용**
  * 다중 파일 드래그 앤 드롭 지원 및 Rate Limit 방지를 위한 순차적(Queue) 업로드 처리
  * 업로드 진행 시 바이트 단위 실시간 프로그레스 바 및 상태 배지(analyzing 등) 연동 완료

## 4. 🎨 UX (사용자 경험 & UI) - ✅ 완료
* **[x] 앱 명칭 및 디자인 수정**
  * 글래스모피즘이 적용된 고품격 다크 모드(네이비/퍼플 컬러) 및 레이아웃 도입
  * 모바일 크롬 입력창 위치 이슈 대응(dvh/viewport-fit) 및 헤더 Safe Area 패딩 처리를 통한 모바일 가독성 100% 확보
* **[x] '테크노트(TechNote)' 서비스 브랜딩 도입**
  * 로고, 색상 팔레트 및 다크모드 레이아웃 고도화를 통한 테크노트 브랜딩 완료


## 5. 🔧 코드 구조 리팩토링 (Code Refactoring) - ✅ 전 Phase 완료
> 세부 로드맵 및 진행 현황: [`doc/refactoring_plan.md`](./refactoring_plan.md)

* **[x] Phase 1·2 — 정리 및 중복 제거** (커밋 `13f224b`)
  * dead code 제거, 라우터 이중 `Depends` 정리, `@app.on_event`→`lifespan` 전환, 루트 스크래치 `.gitignore` 정리
  * ToC 추출 로직 통합(`pdf_service.build_toc` — 복붙 일원화), LLM 프롬프트 외부화(`app/prompts.py`), `owner_email` 전달로 GCS glob 조회 제거
* **[x] Phase 3 (C1) — 거대 함수 분해** (커밋 `c9c4503`)
  * `run_agentic_pipeline`(596줄)을 `_PipelineContext` + 4개 stage(image/general/resolve/answer) + orchestrator(~58줄)로 분해, SSE 이벤트 계약 불변
* **[x] 프론트 M5·M8** (커밋 `13f224b`, `c9c4503`)
  * 공유 타입 추출(`src/types/`), `page.tsx` SSE 로직 → `useChatStream` 훅 분리, `Sidebar.tsx` → `sidebar/` 하위 컴포넌트 분해
* **[x] H2 — 블로킹 GCS I/O 비동기화** (커밋 `6073b36`)
  * `metadata_service`·`conversation_service` 전 public 함수에 `asyncio.to_thread` `_async` 래퍼 추가, 8개 파일 모든 async 호출처 교체
* **[x] Phase 4 — `pytest` 단위 테스트 63개** (커밋 `73de5a1`)
  * `tests/unit/` 신설, `conftest.py` GCS/Gemini 더미 격리, `_normalize_page`·`_find_section_page_range`·`_sse_event`·`_quick_classify`·`normalize_manufacturer`·`is_toc_meaningful`·`gcs_doc_prefix` 등 순수 함수 커버리지
* **[x] Phase 5 — Cloud Tasks + Cloud Run 성능 설정** (커밋 `a3745ab`)
  * `BackgroundTasks` → `task_queue.enqueue_analysis()` (Cloud Tasks / asyncio 폴백), `/internal/analyze` 콜백 엔드포인트, `cloudbuild.yaml` `--cpu=2 --memory=2Gi --min-instances=1 --concurrency=8 --no-cpu-throttling`, `JWT_SECRET` 하드코딩 → `$_JWT_SECRET` 치환변수

## 6. 🗺️ 향후 로드맵 (Next Roadmap)

> 우선순위 순 정렬. 세부 진행 현황은 `task.md` 참조.

### 🔴 즉시 — GCP 수동 설정 (Phase 5 완성)
- **[ ] Cloud Tasks 인프라 설정** — 큐 생성, Cloud Build 트리거 변수 3개 추가 (`_CLOUD_TASKS_QUEUE` / `_CLOUD_RUN_URL` / `_INTERNAL_TASK_SECRET`)
- **[ ] 재배포 후 스모크 테스트** — 실 사용자 투입 전 골든패스(로그인→업로드→채팅) 검증

### 🟠 단기 — 운영 안정화
- **[ ] 화이트리스트 외부화** — 허용 이메일 목록을 코드 밖(GCS JSON 또는 환경변수)으로 분리하여 재배포 없이 관리
- **[ ] 에러 모니터링** — Cloud Logging 알람 (5xx·Gemini 할당량 초과) 설정

### 🟡 중기 — 기능 고도화
- **[ ] 다양한 문서 포맷 지원** — `.docx`, `.xlsx`, `.pptx` → PDF 변환 후 기존 RAG 파이프라인 통과
- **[ ] 유저 피드백 수집** — 답변 좋아요/싫어요 → GCS 로그 → 품질 개선 데이터로 환류
- **[ ] 관리자 대시보드** — 문서 수, 일별 대화 수, 오류율 등 운영 지표

### 🔵 장기 — 고도화
- **[ ] Memory (암묵지 자산화)** — 대화에서 사용자 코멘트·노하우 추출 → 개인 지식 베이스 축적
- **[ ] FAQ 챗봇** — 자주 묻는 질문 사전 등록 → 대기 없이 즉시 매칭 답변
- **[ ] 멀티모달 강화** — 도면·회로도 등 이미지-텍스트 혼합 매뉴얼 처리 고도화

