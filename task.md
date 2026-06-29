# 📋 To Do List (Vision RAG / TechNote)

> 최종 갱신: 2026-06-29

---

## 진행 중인 작업 (In Progress)

없음. 모든 리팩토링 트랙 완료.

---

## 향후 작업 (Next Tasks)

### 🔴 즉시 처리 — GCP 수동 설정 (Phase 5 배포 완성)

Cloud Tasks 코드는 이미 배포됐지만, GCP 인프라 설정이 되어야 실제로 동작합니다.

- [ ] **Cloud Tasks API 활성화**
  ```bash
  gcloud services enable cloudtasks.googleapis.com
  ```
- [ ] **분석 큐 생성** (asia-northeast3 서울 리전)
  ```bash
  gcloud tasks queues create vision-rag-analysis \
    --location=asia-northeast3 \
    --max-concurrent-dispatches=5 \
    --max-attempts=3
  ```
- [ ] **Cloud Build 트리거 변수 추가** (GCP 콘솔 → Cloud Build → 트리거 → 편집)
  - `_CLOUD_TASKS_QUEUE` = `projects/{project_id}/locations/asia-northeast3/queues/vision-rag-analysis`
  - `_CLOUD_RUN_URL` = `https://vision-rag-backend-xxx.a.run.app` (Cloud Run 서비스 URL)
  - `_INTERNAL_TASK_SECRET` = 랜덤 문자열 (예: `openssl rand -hex 32`)
- [ ] 설정 완료 후 **master 재푸시**(또는 Cloud Build 수동 트리거)하여 새 환경변수로 재배포

---

### 🟠 단기 — 실 사용자 투입 전 준비

- [ ] **사전 스모크 테스트** — 재배포 후 OAuth 로그인 → 문서 업로드 → 채팅 골든패스 확인
- [ ] **에러 모니터링** — Cloud Logging 알람 설정 (5xx 에러, Gemini 할당량 초과 감지)

---

### 🟡 중기 — 기능 고도화

- [ ] **다양한 문서 포맷 지원** — `.docx`, `.xlsx`, `.pptx` 업로드 → PDF 변환 후 기존 파이프라인 통과
- [ ] **유저 피드백 수집** — 답변 좋아요/싫어요 버튼 → GCS 로그 적재 → 품질 개선 데이터로 활용
- [ ] **관리자 대시보드** — 업로드 문서 수, 일별 대화 수, 오류율 등 운영 지표 페이지

---

### 🔵 장기 — 고도화 아이디어

- [ ] **Memory (암묵지 자산화)** — 대화에서 사용자 코멘트·노하우를 추출해 개인 지식 베이스로 축적
- [ ] **FAQ 챗봇** — 자주 묻는 질문 사전 등록 → 대기 없이 즉시 매칭 답변
- [ ] **멀티모달 확장** — 도면, 회로도 등 이미지-텍스트 혼합 매뉴얼 처리 강화

---

## 완료된 작업 (Completed)

- [x] 🔧 코드 구조 리팩토링 전 Phase 완료 (`doc/refactoring_plan.md` 참조)
  - [x] Phase 1: dead code 제거, 라우터 이중 `Depends` 정리, `lifespan` 전환, `.gitignore` 정리
  - [x] Phase 2: ToC 통합(`build_toc`), 프롬프트 외부화(`app/prompts.py`), GCS glob 제거
  - [x] Phase 3 (C1): `run_agentic_pipeline` 596줄 → `_PipelineContext` + 4 stage + orchestrator(~58줄)
  - [x] 프론트 M8: 공유 타입 추출 (`src/types/`)
  - [x] 프론트 M5: `useChatStream` 훅 분리, `Sidebar.tsx` → `sidebar/` 하위 컴포넌트 분해
  - [x] H2: 동기 GCS I/O → `asyncio.to_thread` 래퍼 (8파일, 전 async 호출처)
  - [x] Phase 4: `pytest` 단위 테스트 63개 (`tests/unit/`)
  - [x] Phase 5: Cloud Tasks 큐 + Cloud Run (`--cpu=2`, `--memory=2Gi`, `--min-instances=1`, `--no-cpu-throttling`) + `JWT_SECRET` 치환변수 보안 수정
- [x] 🐛 채팅 기능 잔여 버그 수정 (GCS 저장, IME 중복 방지)
- [x] 📑 이름순 정렬 시 영어 우선 배치 정렬 알고리즘 수정
- [x] 📑 사이드바 문서 정렬 방식(최신순/이름순) 필터 UI 및 2단 트리 정렬
- [x] 🌐 커스텀 도메인 연결 (Cloud Run URL 노출 해결)
- [x] 🛡️ Refresh Token HttpOnly 쿠키 전환
- [x] 📛 앱 이름/브랜딩 변경 (Vision RAG → TechNote 테크노트)
- [x] 🎨 UI 전면 리디자인 (글래스모피즘/다크모드)
- [x] 🛡️ 보안 개선 (JWT 기본값 차단, CORS 제한, 민감 정보 제거)
- [x] 📑 문서 최신화 (PRD, API Contract, README, 로드맵 등)
- [x] 👥 멀티테넌시 (사용자별 문서·대화 격리)
- [x] ⚡ 답변 품질·속도 최적화 (93.33% 달성, ~3~5초 절감)
- [x] 🔐 구글 OAuth & 화이트리스트 보안 인증 체계 구축
- [x] 🧪 답변 품질 테스트 프로그램 개발 및 실행 (93.33% 리포트)
- [x] 📱 현장 장비 알람 이미지 RAG 기능 구현
- [x] 📂 문서 관리 고도화 (삭제·다운로드·메타 수정·재분류·드래그앤드롭)
- [x] 📲 PWA 지원 (홈 화면 설치, 오프라인 캐싱)
- [x] 🗂️ 대화 GCS 영속 저장 및 대화 목록·관리 기능
- [x] 🔍 되묻기(Clarification) 및 대화 맥락 유지(Previous Reference)
