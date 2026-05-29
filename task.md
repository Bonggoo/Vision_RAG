# 📋 To Do List (Vision RAG)

## 향후 작업 (Next Tasks)
- [x] 답변 품질 테스트 프로그램 개발 및 실행 🧪
  - [x] doc/질문.md, doc/질문2.md 파싱 유틸리티 구현
  - [x] 백엔드 API (/chat/stream) 연동 테스트 클라이언트 개발
  - [x] 테스트 실행 및 실시간 진행 로깅, 시간 측정 기능
  - [x] 테스트 품질 비교/분석을 위한 JSON 및 마크다운 종합 리포트 생성 완료 (최종 성공률 93.33% 달성)
  - [x] CLI 환경에서 간편히 실행 가능한 옵션 제공 (질문 파일 선택, 샘플링 개수, 동시성 등)
- [/] 답변 품질 개선 및 예외 방어 🛠️
  - [/] 대형 매뉴얼 스캔 시 httpx.ReadError 예외 방어 및 PDF 페이지 슬라이싱 최적화
  - [ ] 답변 품질 고도화 (알람코드, 표, 도면 인식률)
- [ ] 챗 서비스 활용 가이드라인 배포

## 완료된 작업 (Completed Tasks)
- [x] 장비 알람 이미지 분석 RAG 기능 구현 완료 🚀
  - [x] 백엔드: ChatRequest 스펙 확장 및 이미지 분석(Gemini Vision) 비동기 함수 구현
  - [x] 백엔드: agentic_graph.py 이미지 기반 자동 문서 매칭 및 질문 리라이팅 전처리 연동
  - [x] 프론트엔드: useChatStore 및 ChatMessage 이미지 보존 및 렌더링 추가
  - [x] 프론트엔드: ChatInput 모바일 카메라/갤러리 사진 첨부 및 썸네일 미리보기 UI 구현
  - [x] 프론트엔드: page.tsx 이미지 Base64 취합 및 SSE API 전송 연동

## 완료된 작업 (Completed Tasks)
- [x] 문서 관리 고도화 및 기존 문서 마이그레이션 (총 10개 기능 + 마이그레이션)
  - [x] 1. 백엔드: 커스텀 예외 정의 (`app/exceptions.py`)
  - [x] 2. 백엔드: AI 기반 제조사/모델 시리즈 자동 분류 기능 (`app/services/agent_service.py` 수정)
  - [x] 3. 백엔드: 중복 방지(SHA-256) 및 빈 파일(0바이트) 검증 기능 추가 (`app/services/pdf_service.py` 수정)
  - [x] 4. 백엔드: 메타데이터 관리 서비스 확장 및 업로드 응답 스키마 수정 (`app/services/metadata_service.py`, `app/schemas/response.py`)
  - [x] 5. 백엔드: 업로드 라우터 예외 처리 및 문서 다운로드/메타데이터 수정 API 구현 (`app/routers/upload.py`, `app/routers/documents.py` 수정)
  - [x] 6. 백엔드: 기존 업로드 문서에 대한 제조사/모델 시리즈 일괄 마이그레이션 스크립트 작성 및 실행
  - [x] 7. 프론트엔드: API 클라이언트(다운로드, 메타 수정, 중복 처리) 및 Zustand 스토어 확장 (`src/lib/api.ts`, `src/store/useDocumentStore.ts` 수정)
  - [x] 8. 프론트엔드: 드래그 앤 드롭 업로드 및 다중 파일 순차 업로드 UI/진행률 구현 (`src/components/layout/Sidebar.tsx` 수정)
  - [x] 9. 프론트엔드: 사이드바 검색 필터 및 제조사 > 모델 시리즈 2단 트리 그룹핑 UI 구현 (`src/components/layout/Sidebar.tsx` 수정)
  - [x] 10. 프론트엔드: 문서 개별 다운로드 및 인라인 메타데이터 편집 팝오버 UI 구현 (`src/components/layout/Sidebar.tsx` 수정)
  - [x] 11. 프론트엔드: 대화 기록 마크다운 내보내기 기능 구현 (`src/components/chat/ExportButton.tsx` 신설, `page.tsx` 연동)
  - [x] 12. 전체 빌드 검증, 로컬 테스트 및 Cloud Run/Vercel 배포
  - [x] 13. 변경사항 Git 커밋 및 PR 생성 (Conventional Commits 준수)
- [x] PWA 지원 추가 (앱 설치, 전체화면, 오프라인 캐싱)
- [x] 모바일 크롬 입력창 위치 수정 (dvh + viewport-fit)
- [x] 헤더 safe-area-inset-top 패딩 추가
- [x] Gemini 모델 404 에러 수정 (flash-lite 통일)
- [x] Cloud Run 환경변수 최신화 (GEMINI_MODEL_NAME 추가)
- [x] Vercel (프론트엔드) + Cloud Run (백엔드) 배포 완료
- [x] Phase 1~3 하이브리드 추론 파이프라인 완성
- [x] Gemini 3.1 Flash-Lite 연동
- [x] 프리미엄 UI 및 멀티턴 대화 구현
- [x] 프로젝트 문서(README, PRD, API Contract) 최신화
- [x] GitHub 원격 저장소 연동

