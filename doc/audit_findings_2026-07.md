# 🔍 전체 코드 감사 결과 — UI/UX · 보안 · 백엔드 (2026-07-18)

> **감사 범위**: 프론트엔드(UI/UX·접근성) + 백엔드(아키텍처·성능·정확성) + 보안 전 영역
> **감사 방식**: 프론트엔드는 코드 정독 + 브라우저 실사용 검증, 백엔드/보안은 서비스 전체 정독
> **이 문서의 목적**: 이번 감사에서 발견됐으나 **아직 처리하지 않은(deferred) 항목**의 추적. 이미 처리한 항목은 맨 아래 "✅ 이번에 처리 완료" 참고.

---

## ✅ 이번에 처리 완료 (2026-07-18)

아래 항목은 이 감사 직후 바로 수정하고 로컬에서 검증까지 마쳤습니다.

### A그룹 — 안전한 즉시 수정
1. **`session_id` 경로 순회 방어** — `conversations.py`의 `session_id`를 `str` → `UUID`로 강제, `ChatRequest.session_id`도 `Optional[UUID]`로 변경. 로컬 스토리지 모드에서 조작된 `session_id`가 파일 경로를 탈출하던 취약점 차단. (검증: 조작 문자열 → 404/422, 정상 UUID → 통과)
2. **ConfirmDialog Enter 키 오작동** — 전역 keydown Enter 핸들러가 포커스와 무관하게 항상 "확인"을 실행하던 버그 제거. 이제 포커스된 버튼의 네이티브 동작에 위임. (검증: 삭제 확인창에서 취소 버튼 포커스 후 Enter → 삭제 안 됨)
3. **세션 만료 시 무안내 로그아웃** — 리프레시 토큰까지 만료(401)되어 강제 로그아웃될 때 안내 토스트 추가.
4. **아이콘 전용 버튼 접근성 라벨** — 메시지 전송/응답 중단/이미지 제거/메뉴 열기/사이드바 닫기/대화 삭제 버튼에 `aria-label` 추가.
5. **죽은 코드 정리** — `agentic_graph.py`의 미사용 sync import 제거, 레거시 마이그레이션 스크립트 3종을 `scripts/archive/`로 이동(재실행 경고 README 포함).

### B그룹 — 부작용 있어 검증 동반한 수정
6. **GCS 업로드 실패를 성공(200)으로 응답하던 버그** — `pdf_service.process_document_upload()`가 GCS 쓰기 실패를 `except`로 삼키고 성공 응답하던 것을, `metadata_service.store_document_file_async()` 헬퍼로 일원화하여 실패 시 예외 전파. (Cloud Run 로컬 `/tmp`는 재활용 시 소멸하므로 GCS 쓰기 실패 = 데이터 유실)
7. **동기 Gemini 호출의 이벤트 루프 블로킹 (4곳)** — `upload.py`(2곳: `_run_analysis_pipeline`의 `build_toc`, `extract_toc_with_range`), `documents.py`(`reindex_document`), `pdf_service.py`(`process_document_upload`의 `build_toc`)를 `asyncio.to_thread`로 래핑. (검증: 업로드→ToC추출→채팅→대화저장 전 플로우 정상)

> 위 7개 처리 후: `pytest` 143 passed / 2 skipped, `tsc --noEmit` 0 errors, 브라우저 실사용 검증 완료.

### C그룹 — Critical + Low 보안 (2026-07-18, PR #16)
8. **C-1 `/internal/analyze` 무인증 노출** — 배포 환경에 `INTERNAL_TASK_SECRET`이 설정돼 있음을 확인 후, `main.py`에 미설정 시 부팅 차단(fail-closed) 가드 추가(`JWT_SECRET` 패턴). `L-1` 상수시간 비교(`hmac.compare_digest`)도 함께 처리, `None` 헤더 안전 처리.

### D그룹 — Medium + Low 일괄 (2026-07-18)
9. **M-1 GOOGLE_CLIENT_ID fail-closed** — 배포값 설정 확인 후 `main.py`에 미설정 시 부팅 차단 가드 추가(aud 검증 우회 방지).
10. **M-3 `get_document()` owner 폴백 제거** — owner_email이 주어졌는데 소유자 스코프 미스면 전체 사용자 검색으로 폴백하지 않고 `None` 반환(타 사용자 메타데이터 유출 함정 제거).
11. **M-4 예외 원문 노출 제거** — `upload.py`·`documents.py`의 500 핸들러 3곳, `document_conversion.py`의 LibreOffice stderr 노출을 서버 로깅 + 일반 메시지로 교체.
12. **M-5 업로드 크기/페이지 상한** — `MAX_UPLOAD_MB=100`, `MAX_PDF_PAGES=3000` 설정 추가(관대한 기본값). preflight·동기·비동기 업로드 경로 모두에 적용. (검증: 101MB→413, 50MB→통과)
13. **M-6 파이프라인 종합 타임아웃** — `PIPELINE_TIMEOUT=240s` 설정, 채팅 SSE 래퍼에 데드라인 체크 추가(런어웨이 누적 지연 방지).
14. **M-7 대화 목록 캐시** — `get_conversations()`에 60초 TTLCache + 생성/저장/삭제/제목변경 시 무효화(documents와 동일 패턴). (검증: 캐시 히트 + 무효화 반영 확인)
15. **M-9 hydration mismatch 경고 제거** — `<html>`에 `suppressHydrationWarning` 추가. (검증: 콘솔 에러 0건)
16. **M-10 대화 목록 키보드 접근** — 대화 항목에 `role="button"`·`tabIndex`·`onKeyDown`·`aria-current` 추가. (검증: 키보드 접근 가능)
17. **M-11 닫힌 모바일 드로어 접근 차단** — 닫힘 시 `inert`+`aria-hidden`. (검증: 닫힘 시 내부 버튼 포커스 불가, 열림 시 정상 복원)
18. **L-5 다크모드 상태 이중 관리 통합** — `Header`가 localStorage를 재차 읽어 재적용하던 로직 제거, `layout.tsx` 사전 스크립트가 적용한 DOM 상태를 미러링만. (검증: 토글 정상)
19. **L-6 일괄 삭제 부분 실패 집계** — for 루프에 try/catch + 성공/실패 카운트 후 결과 토스트.

> D그룹 처리 후: `pytest` 143 passed / 2 skipped, `tsc --noEmit` 0 errors, 브라우저 실사용 검증(M-5/7/9/10/11, L-5) 완료.

---

## 🔴 Critical — ✅ 처리 완료 (PR #16, 위 8번 참고)

### ~~C-1. `/internal/analyze` 무인증 노출 위험~~ → **해결됨**
`main.py` fail-closed 가드 + `hmac.compare_digest` 비교로 수정 완료. 배포 환경에 `INTERNAL_TASK_SECRET` 설정 확인됨.

---

## 🟠 High — 별도 작업으로 진행 권장 (패치 한 줄로 안 끝남)

### H-1. Rate limiting 전무
- **위치**: 앱 전역 (`/chat/stream`, `/upload`, `/upload/analyze`, `/documents/reclassify`, `/auth/*`)
- **내용**: 요청 제한 미들웨어가 전혀 없음. 인증 사용자(또는 C-1 조합 시 무인증)가 반복 호출로 Gemini 과금 폭주 또는 Cloud Run 동시성(`concurrency=8`) 고갈 유발 가능.
- **방향**: `slowapi` 등으로 사용자/IP 단위 제한, 또는 Cloud Armor/API Gateway 정책. "사용자당 분당 N회" 정책 결정 필요.

### H-2. 업로드 파일 크기 상한 없음
- **위치**: `pdf_service.py:168`(`file.read()` 크기 미검증), `upload.py:83-101`(Signed PUT URL에 `x-goog-content-length-range` 제약 없음)
- **내용**: 임의 크기 파일 업로드 시 2Gi 인스턴스 메모리 고갈 또는 GCS 저장비용 무제한 증가. GCS 직접 업로드 경로는 앱 코드를 아예 안 거침.
- **방향**: preflight 체크에 크기 상한 + Signed URL에 `x-goog-content-length-range` + 서버 측 `UploadFile` 크기 검증. 프론트 에러 메시지도 함께.

### H-3. 리프레시 토큰 서버 측 폐기(revocation) 부재
- **위치**: `auth_service.py:54-59,121-146`, `auth.py:56-87`
- **내용**: 리프레시 토큰이 순수 stateless JWT(30일)라 denylist/allowlist 없음. `/auth/logout`은 쿠키만 지우고 토큰 자체는 무효화 안 함. 토큰 유출 시(XSS 등) 로그아웃해도 최대 30일 유효.
- **방향**: 서버 측 토큰 저장소(jti + 폐기 목록, 또는 rotation-family 추적) 도입. 현재 완전 stateless 방식을 얼마나 바꿀지 설계 논의 필요. (관련: [security_roadmap.md](./security_roadmap.md) Phase 1)

---

## 🟡 Medium

> ✅ **처리 완료**: M-1, M-3, M-4, M-5, M-6, M-7, M-9, M-10, M-11 (위 "처리 완료" D그룹 참고). 아래는 참고용 상세.
> ⏳ **미처리**: M-2(설계 필요), M-8(의도된 동일 모델 설정 — 조치 불필요).

### 보안
- **M-1. `GOOGLE_CLIENT_ID` 미설정 시 OAuth `aud` 검증 스킵** — `auth_service.py:20-24`. 빈 값이면 `audience=None`이 되어 다른 앱용 구글 ID 토큰도 통과. 주석은 "차단"이라 하지만 실제로는 아님. → `JWT_SECRET`처럼 미설정 시 fail-closed. (프로덕션에 값이 설정돼 있다면 방어적 코드일 뿐)
- **M-2. `JWT_SECRET` 기본값 방어가 `USE_LOCAL_STORAGE=True`로 우회됨** — `main.py:20-25`. 실배포에 `USE_LOCAL_STORAGE=True`가 남으면 하드코딩 기본 시크릿이 조용히 활성화 + 더미 유저 우회까지 겹침. → `ENVIRONMENT` 같은 독립 변수로 프로덕션 판정, 또는 스토리지 모드와 무관하게 기본값 금지.
- **M-3. `get_document()`가 owner 미스 시 전체 사용자 검색으로 폴백** — `metadata_service.py:208-229`. 현재는 호출부마다 `verify_document_owner()`로 재검증해 악용 불가하나, 이 검증을 빼먹는 코드가 추가되면 즉시 타 사용자 메타데이터 유출. → owner-scope 미스 시 `None` 반환, 관리자용은 명시적 `allow_unscoped=True`.
- **M-4. 예외 원문(`str(e)`)이 클라이언트에 노출** — `upload.py:51,221,305`, `documents.py:253`, `document_conversion.py:314-315`(LibreOffice stderr 300자 포함). 내부 경로/라이브러리 에러 노출. → 서버 로깅 후 일반 메시지 반환.
- **M-5. PDF 페이지 수/구조 상한 없이 PyMuPDF/Vision 처리** — `pdf_service.py`, `upload.py`. `fitz.open` 및 페이지별 썸네일에 하드 상한 없음. → 처리 전 페이지 수/바이트 상한 검사.

### 백엔드 아키텍처
- **M-6. 파이프라인 종합 타임아웃 없음** — 단계별 90초 캡은 있으나 `run_agentic_pipeline` 전체를 감싸는 `asyncio.wait_for` 없음. 느린 Gemini 응답 시 단일 SSE 연결이 수 분간 지속 가능(정상 종료는 됨, 상한만 없음).
- **M-7. `get_conversations()` 캐싱 없음** — `conversation_service.py:100-117`. documents는 60초 TTLCache가 있는데 대화 목록은 없어서 사이드바 열 때마다 N+1 순차 다운로드(최신 20개 반환하지만 전체 blob을 먼저 받음). → documents와 동일한 TTLCache 미러링.
- **M-8. `GEMINI_MODEL_NAME` == `GEMINI_FLASH_MODEL_NAME`** — `config.py:6-7` 둘 다 `gemini-3.1-flash-lite`. 아키텍처 문서상 "Flash-Lite vs Vision" 티어가 실제로는 동일 모델로 붕괴. 의도한 것인지 확인 + 설정 검증 추가 권장.

### UI/UX
- **M-9. 다크모드 hydration mismatch 콘솔 경고** — `layout.tsx:58` `<html lang="ko">`에 `suppressHydrationWarning` 없음. `<head>`의 사전 다크모드 스크립트가 DOM을 직접 건드려 매 로드 hydration mismatch 발생(dev 콘솔 경고, 프로덕션 빌드에선 미출현). → `<html>`에 `suppressHydrationWarning` 한 줄. (표준 Next.js 다크모드 패턴)
- **M-10. 대화 목록 항목 키보드 접근 불가** — `Sidebar.tsx:306`. 대화 전환용 항목이 `<div onClick>`만 있고 `tabIndex`/`role="button"`/`onKeyDown` 없음. 키보드 사용자는 대화 전환 불가. (문서 항목은 버튼이라 문제 없음)
- **M-11. 닫힌 모바일 드로어가 접근성 트리에 잔존** — `Sidebar.tsx:505`. 닫힘을 `translate-x-full`(transform)로만 처리, `aria-hidden`/`inert` 없음. 시각적으로 닫혀도 키보드 Tab/스크린리더가 화면 밖 버튼(대화 삭제, 로그아웃 등)에 계속 접근 가능. → 닫힘 상태에 `inert` 또는 `aria-hidden` 부여.

---

## 🟢 Low

> ✅ **처리 완료**: L-1(PR #16), L-5, L-6. ⏳ **미처리**: L-2(CSRF·규모 큼), L-3(Secret Manager→[security_roadmap.md](./security_roadmap.md)), L-4(조치 대상 아님), L-7(의도된 동작).

- **L-1. 비상수시간 시크릿 비교** — `internal.py:30` `!=` 사용. 타이밍 side-channel(실효성 낮음). → `hmac.compare_digest`. ✅ **완료(PR #16)**
- **L-2. `/api/auth/refresh` CSRF 토큰 없음** — `auth.py:56-79`. SameSite 쿠키 + CORS allowlist에만 의존. 영향 제한적이나 방어심화 차원에서 CSRF 토큰 권장.
- **L-3. 시크릿을 Secret Manager 아닌 평문 env로 주입** — `cloudbuild.yaml:20-21`. `GEMINI_API_KEY`/`JWT_SECRET`/`INTERNAL_TASK_SECRET`/`GOOGLE_CLIENT_ID`가 `--set-env-vars` 평문. IAM 뷰어·배포 로그에 노출. → `--set-secrets` + Secret Manager. (관련: [security_roadmap.md](./security_roadmap.md) Phase 2)
- **L-4. GCS 버킷명에 내부 프로젝트 ID 노출** — `config.py:11`. 시크릿은 아니나 에러 메시지로 새면 minor 정보 노출.
- **L-5. 다크모드 상태 이중 관리** — `layout.tsx` 인라인 스크립트 vs `Header.tsx:19-36`. 지금은 동기화되나 한쪽만 수정 시 어긋날 구조. → 단일 소스로 통합.
- **L-6. 일괄 삭제 부분 실패 무시** — `Sidebar.tsx:209-223` `handleBatchDelete`. for 루프에 try/catch 없어 중간 실패 시 나머지 미삭제인데 성공 토스트만 뜰 수 있음. → 실패 카운트 집계 후 결과 토스트.
- **L-7. 클라이언트 조기 연결 종료 시 부분 답변 미저장** — `chat.py:44-50` + `agentic_graph.py:1214-1216`. 스트림 중 연결 끊기면 `GeneratorExit`로 `finish()`/`save_conversation()` 미호출. 사용자는 부분 답변을 받았는데 기록엔 안 남음. 의도된 동작인지 확인 필요.

---

## 📋 테스트 커버리지 갭 (pytest)

- **0% 커버리지**: `agent_service.py`(Gemini 호출 래퍼·재시도), `conversation_service.py`(오늘 수정분 포함), `task_queue.py`, `auth_service.py`
- **`agentic_graph.py`**: 순수 유틸 함수만 테스트, 핵심 파이프라인(`run_agentic_pipeline`/`_stage_resolve_document`/`_stage_answer`)·SSE 이벤트 시퀀스 미테스트
- **`metadata_service.py`**: 경로 헬퍼만 테스트, CRUD·TTL 캐시·로컬/GCS 분기 미테스트
- **`documents.py` 라우터**: `GET`/`DELETE`만 커버, `PATCH`·`/reclassify`·`/{id}/toc`·`/{id}/reindex`·`/{id}/download`·`/{id}/download-url` 미테스트

---

## ✅ 감사에서 "이상 없음"으로 확인된 영역 (참고)

- **문서 IDOR**: 모든 document 라우트가 `verify_document_owner_async`를 일관 적용 (get/patch/delete/toc/reindex/download/download-url)
- **Conversation IDOR (GCS 모드)**: 저장 경로가 JWT 파생 `user_email`로 네임스페이스 — 안전 (로컬 모드는 위 A-1로 처리 완료)
- **SSRF / Command Injection**: 사용자 제어 outbound 요청 없음, subprocess는 인자 리스트 방식(파일명 직접 미사용, 확장자는 화이트리스트)
- **JWT 알고리즘 혼동**: 서버에서 HS256 고정
- **CORS**: 명시적 origin allowlist, 와일드카드 없음
- **`.env` 시크릿**: git 미추적 확인, 하드코딩 API 키 없음
- **의존성 버전**: 특별히 오래된 것 없음 (PyJWT 2.13.0, cryptography 48.0.0, fastapi 0.136.1 등)
- **SSE 스트림 종료**: 모든 종료 경로에서 `done` 이벤트 도달, 스트림 행(hang) 위험 없음
- **Gemini 비용 상한**: 요청당 호출 횟수 고정·소량, 무한 루프 없음
- **`document_conversion.py`**: 모든 블로킹 작업을 `asyncio.to_thread`로 올바르게 래핑 (모범 사례)
