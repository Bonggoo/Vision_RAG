# 📋 TechNote 개선 프로젝트 — 진행 현황 및 잔여 작업 마스터 보드

> **최종 업데이트**: 2026-07-18  
> **총 15개 항목 중 14개 완료 · 1개 남음 (다음 테스크로 진행 예정)**  
> **최근 추가 완료(보드 외)**: 인앱 토스트/확인창, 적응형 웰컴 온보딩, 세션 갱신 회복력, 대화 기록 로컬 스토리지 지원, 전체 코드 감사 후속 수정(A·B그룹 7건) — 아래 참고
> **🔍 코드 감사 잔여 항목**: 2026-07-18 UI/UX·보안·백엔드 전면 감사에서 발견된 미처리 항목은 별도 문서 참고 → [audit_findings_2026-07.md](./audit_findings_2026-07.md)

---

## 🔲 잔여 작업 (1개)

### 🟢 P3 — 품질 향상 (다음 순서 진행 예정)

#### 1. 참조 페이지 PDF 보기 방식
> **목표**: AI 답변 하단에 표시되는 참조 페이지 썸네일을 클릭했을 때, 단순 이미지 모달 팝업이 아닌 실제 고해상도 PDF 뷰어로 연결하여 텍스트 검색 및 드래그가 가능하도록 개선합니다.

* **현 상태**:
  * 현재는 `render_page_thumbnail`을 통해 150 DPI의 저용량 PNG 이미지를 전달받아 모달 이미지 뷰어로 띄우는 구조입니다. (글씨가 다소 흐릿하고 텍스트 드래그가 안 됨)
* **개선 방향 (결정됨 — 방향 B)**:
  * 백엔드에 구현되어 있는 `download_document_url()` (GCS Signed URL 발급 API)을 호출하여 PDF 직접 보기 링크를 가져옵니다.
  * 브라우저 기본 PDF 뷰어나 혹은 임베디드 뷰어로 해당 PDF를 열고, `#page=N` 해시 파라미터를 추가하여 참조 페이지(`p.N`)로 즉시 자동 스크롤되도록 연결합니다.
  * 예: `https://storage.googleapis.com/.../original.pdf#page=45`
* **작업 내용**:
  * [ ] 프론트엔드: 참조 썸네일 클릭 시, 해당 문서의 `download-url` API 비동기 호출
  * [ ] 프론트엔드: 반환된 URL 뒤에 `#page={pageNumber}`를 붙여 새 탭 또는 iframe으로 로드하는 뷰어 모달 구현
* **예상 공수**: 2~3일

---

## 📅 추천 차기 액션 플랜

```
[다음 단계] 
  ├── 1. 참조 페이지 클릭 시 GCS Signed URL + #page=N 뷰어 연동 (2~3일)
  └── 2. 마일스톤: 등록 문서 200개 돌파 시 1단계(문서선택)를 'ToC 임베딩 벡터 검색 RAG'로 전환 준비
```

---

## 🗺️ 향후 로드맵 (Next Roadmap)

> 우선순위 순. 기능 요구사항 완료 현황은 아래 "완료된 작업 내역" 참고, 보안 중장기 계획은 [security_roadmap.md](./security_roadmap.md), 감사 발견 잔여 항목은 [audit_findings_2026-07.md](./audit_findings_2026-07.md) 참고.

### 🔴 즉시 — GCP 수동 설정 (Cloud Tasks 인프라 완성)
Cloud Tasks 연동 코드는 배포됐으나, 아래 GCP 인프라 설정이 있어야 실제 비동기 큐로 동작합니다. (미설정 시 `asyncio.create_task` 로컬 폴백으로 동작)

- [ ] **Cloud Tasks API 활성화** — `gcloud services enable cloudtasks.googleapis.com`
- [ ] **분석 큐 생성** (asia-northeast3)
  ```bash
  gcloud tasks queues create vision-rag-analysis \
    --location=asia-northeast3 --max-concurrent-dispatches=5 --max-attempts=3
  ```
- [ ] **Cloud Build 트리거 변수 추가** (GCP 콘솔 → Cloud Build → 트리거 → 편집)
  - `_CLOUD_TASKS_QUEUE` = `projects/{project_id}/locations/asia-northeast3/queues/vision-rag-analysis`
  - `_CLOUD_RUN_URL` = Cloud Run 서비스 URL
  - `_INTERNAL_TASK_SECRET` = 랜덤 문자열 (`openssl rand -hex 32`) — ⚠️ [audit_findings_2026-07.md](./audit_findings_2026-07.md) C-1 참고: 이 값이 비어 있으면 `/internal/analyze`가 무인증 노출됨
- [ ] 설정 후 master 재푸시(또는 수동 트리거)로 새 환경변수 재배포

### 🟠 단기 — 운영 안정화
- [ ] **재배포 후 스모크 테스트** — OAuth 로그인 → 문서 업로드 → 채팅 골든패스 검증
- [ ] **에러 모니터링** — Cloud Logging 알람 (5xx 에러, Gemini 할당량 초과)

### 🟡 중기 — 기능 고도화
- [x] ~~**다양한 문서 포맷 지원**~~ — `.docx`/`.xlsx`/`.pptx`/텍스트/이미지 → PDF 변환 후 기존 파이프라인 통과 (PR #14 완료, `document_conversion.py`)
- [ ] **유저 피드백 수집** — 답변 좋아요/싫어요 → GCS 로그 적재 → 품질 개선 데이터로 환류
- [ ] **관리자 대시보드** — 문서 수, 일별 대화 수, 오류율 등 운영 지표 페이지

### 🔵 장기 — 고도화 아이디어
- [ ] **Memory (암묵지 자산화)** — 대화에서 사용자 코멘트·노하우 추출 → 개인 지식 베이스 축적
- [ ] **FAQ 챗봇** — 자주 묻는 질문 사전 등록 → 즉시 매칭 답변
- [ ] **멀티모달 강화** — 도면·회로도 등 이미지-텍스트 혼합 매뉴얼 처리 고도화

---

## 📎 완료된 작업 내역 (14/15)

### 🚀 아키텍처 및 핵심 추론 개선 (최근 완료)

#### 1. ToC 2단계 분리 검색 및 되묻기(Clarification) 도입
* **내용**: 
  * 1단계: 메타데이터(ToC 제외) 기반 1차 문서 필터링 진행 (~2,500 토큰으로 대폭 감소, 비용 90% 이상 절감)
  * 확신도(Confidence) 점수가 낮거나 1, 2위 간 점수차가 모호한 경우, SSE `clarification` 이벤트를 발행하여 사용자에게 되묻기 UI를 띄움
  * 사용자가 되묻기 카드를 선택하면 장비 정보를 질문 텍스트 뒤에 덧붙여(리라이팅) RAG 맥락을 자동 보강하며 정밀 재탐색 수행
  * 2단계: 선택된 문서의 ToC 전체를 토큰 잘림 없이 전달하여 페이지 추론 정확도 극대화

#### 2. 대화 내역 GCS 영속성 저장
* **내용**:
  * 로컬스토리지 `persist` 의존성을 완전 제거하고, 로그인된 사용자의 이메일을 기반으로 `users/{email}/conversations/{session_id}.json` GCS 경로에 대화 히스토리를 저장 및 로드
  * 대화 세션 목록 조회, 생성, 삭제, 단건 대화 상세 로딩, 대화 제목 수정 기능 구현 완료
  * 첫 메시지 스트리밍 정상 완료(`done` 수신) 시 백엔드에서 대화를 GCS에 자동 영속화

#### 3. 대화 맥락 유지 강화 (Previous Reference)
* **내용**:
  * 직전 답변의 참조 문서 ID와 페이지 번호를 `ChatRequest` 스펙에 포함하여 프론트엔드에서 전송
  * 백엔드 문서 분류 프롬프트에 이전 참조 정보를 가중치 힌트로 추가하여, 같은 장비에 대한 꼬리 질문 시 엉뚱한 매뉴얼을 탐색하는 문제 원천 차단

---

### 🛠️ 기타 완료된 인프라 및 UI 항목

* **대용량 업로드 고도화**: `Preflight` 사전 검증 + `GCS Direct Upload` + `Cloud Tasks` 비동기 AI 분석 파이프라인 전면 구축 완료 ([async_upload_roadmap.md](./async_upload_roadmap.md))
* **보안 및 환경 설정**: JWT 쿠키 무효화 및 `USE_LOCAL_STORAGE` 모드 안전 검증 도입 완료 ([security_roadmap.md](./security_roadmap.md))
* **문서 목록 조회 ETag 최적화**: 304 Not Modified 캐싱을 도입하여 목록 갱신 지연 현상 해결
* **UI/UX 개선**: 
  * 사이드바 토글 접기/펼치기 지원
  * AI 목차 추천 UI 카드 및 웰컴/빈 화면 예시 질문 카드 추가
  * 되묻기 시 발생 가능한 빈 말풍선 렌더링 예외 처리

---

### 🎨 UX 고도화 (2026-07 추가 완료 · PR #10~#13)

* **인앱 토스트/확인창 도입**: 네이티브 `alert()/confirm()`를 전역 `useUIStore` 기반 토스트 + 확인 다이얼로그로 대체. `toast.*()` / `confirmDialog()` 헬퍼는 React 컴포넌트 밖(스토어·유틸)에서도 호출 가능하며 `components/ui/`의 `Toaster`/`ConfirmDialog`가 `layout.tsx`에 마운트됨. 파괴적 동작(삭제)은 위험(빨강) 스타일로 확인.
* **업로드 결과 통합 안내**: `lib/upload.ts`의 `processUploadFiles()`를 사이드바·웰컴 온보딩 공용 핸들러로 분리, 성공/중복/실패 건수를 요약해 토스트로 안내하고 목록을 새로고침.
* **적응형 웰컴 온보딩**: 보유 문서가 없을 때 `page.tsx`가 온보딩/업로드 유도 화면을 노출. 문서 로딩 중 온보딩↔질문 화면이 번갈아 깜빡이던 플래시 제거.
* **세션 갱신 회복력**: `useAuthStore` 리프레시가 서버 일시 오류(5xx/네트워크)일 땐 기존 세션을 유지하고, 실제 만료(401)에서만 강제 로그아웃하도록 개선. 문서 재분석 요청에 누락됐던 인증 헤더도 보강.

---

### 🔧 대화 기록 로컬 스토리지 + 코드 감사 후속 수정 (2026-07-18)

* **대화 기록 로컬 스토리지 지원**: `conversation_service.py`의 CRUD 6종에 `USE_LOCAL_STORAGE` 분기 추가(다른 서비스와 동일 패턴). GCS 없이 오프라인으로 대화 기능 전체 테스트 가능. 저장 위치는 `backend/conversations/{email}/{session_id}.json`. 함께 `save_message_async` 시그니처 불일치 버그(약 3주간 대화 메시지가 조용히 저장 실패하던 문제) 수정.
* **전체 코드 감사(UI/UX·보안·백엔드) 후속 즉시 수정 7건** — 상세는 [audit_findings_2026-07.md](./audit_findings_2026-07.md)의 "✅ 이번에 처리 완료" 참고:
  * `session_id` 경로 순회 방어(`str`→`UUID`), ConfirmDialog Enter 오작동 수정, 세션 만료 안내 토스트, 아이콘 버튼 `aria-label`, 죽은 코드/레거시 마이그레이션 스크립트 정리
  * GCS 업로드 실패를 성공으로 응답하던 데이터 유실 버그 수정, 동기 Gemini 호출 4곳 `asyncio.to_thread` 래핑
* **감사 잔여 항목**: Critical 1건(`/internal/analyze` 무인증) + High 3건(rate limiting, 업로드 크기 상한, 리프레시 토큰 폐기) 등은 배포 환경 확인·설계 논의가 필요해 [audit_findings_2026-07.md](./audit_findings_2026-07.md)로 이관.

---

### 📚 요구사항 완료 현황 (카테고리별 요약)

이전에 `improvement_list.md` / `task.md`로 분산 관리하던 요구사항 현황을 여기로 통합했습니다.

* **🔒 보안·사용자** — 자체 JWT Access/Refresh 무중단 갱신, 구글 OAuth 통합, 화이트리스트 폐지(공개 서비스 전환, 커밋 `6321e4d`), `owner_email` 멀티테넌시 격리
* **⚡ 코어 기능** — 대화 품질 벤치마크 93.33%, Step0+Phase0/1 1회 LLM 병합·Phase2 비동기화로 ~3초 절감, 썸네일 레퍼런스, 모바일 이미지 RAG, 되묻기·Previous Reference, 1차 필터 토큰 90%↓, 대화 영속 저장
* **📂 파일 관리** — 삭제/다운로드(RFC 5987)/메타 인라인 수정/Vision 재분류, 다중 드래그앤드롭 순차 업로드 + 실시간 프로그레스
* **🎨 UX** — 글래스모피즘 다크모드, 모바일 dvh/safe-area, 테크노트 브랜딩, 인앱 토스트/확인창, 적응형 온보딩
* **🔧 리팩토링 (전 Phase 완료)** — 세부: [refactoring_plan.md](./refactoring_plan.md)
  * Phase 1·2 정리/중복제거(`13f224b`), Phase 3 거대함수 분해 `run_agentic_pipeline` 596→58줄(`c9c4503`), 프론트 M5·M8 타입/훅/컴포넌트 분해, H2 블로킹 GCS I/O 비동기화(`6073b36`), Phase 4 pytest 63개(`73de5a1`), Phase 5 Cloud Tasks+Cloud Run(`a3745ab`)
