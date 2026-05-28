# 📋 To Do List (Vision RAG)

## 향후 작업 (Next Tasks)
- [x] 프리미엄 라이트/다크 테마 및 스위처 UI/UX 리디자인
  - [x] globals.css 리디자인 (라이트: 프로스트 화이트 & 다크: 스페이스 블랙 OKLCH 변수 분리 및 테마 전환 트랜지션 추가)
  - [x] Header.tsx 및 layout.tsx 수정 (Sun/Moon 테마 토글 버튼 추가 및 초기 테마 플리커링 방지 스크립트 적용)
  - [x] page.tsx 리디자인 (테마별 오로라 그래디언트 차별화, 기능 카드 테마별 마이크로 인터랙션)
  - [x] ChatMessage.tsx 리디자인 (테마별 유저/AI 글래스 버블 분기 처리, 참조 이미지 호버 고도화)
- [x] Git 원격 브랜치 푸시 및 GitHub Pull Request 생성 완료 (#2)
- [ ] PDF 업로드 흐름 UX 개선 (모바일)
- [x] 프론트엔드 UI/UX 모바일 대응 및 버그 수정
  - [x] iOS PWA/웹앱 상단 헤더 safe-area-inset-top 겹침 현상 대응 (`Header.tsx` & `globals.css` 수정)
  - [x] 모바일 채팅창 입력 줌인 방지 (`ChatInput.tsx` 글자 크기 16px 대응)
  - [x] 라이트 모드 유저 메시지 버블 글자 색상 수정 (`ChatMessage.tsx` text-slate-900 적용)
- [x] 백엔드 PDF 문서 제목 추출 알고리즘 개선
  - [x] `agent_service.py`에 Gemini Vision 기반 비동기 제목 추출 함수 추가
  - [x] `pdf_service.py` 제목 추출 로직 비동기화 및 Gemini Vision 우선 적용 (실패 시 기존 로직 fallback)
- [x] 검증 및 빌드 확인
  - [x] 로컬 제목 추출 기능 수동 테스트 진행 및 결과 검증 (페스토 그리퍼 PDF 테스트 통과)
  - [x] 프론트엔드 빌드 검증 (`npm run build` 통과)
  - [x] Git 원격 브랜치 커밋 및 PR 생성 (수정 후 재생성 완료)
- [x] 헤더 safe-area 마운트 및 콘텐츠 잘림 현상 보완 (`Header.tsx` 재수정)
- [x] 2차 UX 피드백 반영 및 에이전트 라우팅 고도화
  - [x] 업로드 완료 시 사이드바가 닫히지 않도록 수정 (`Sidebar.tsx` handleFileUpload 수정)
  - [x] 라이트 모드일 때 새 대화 시작 버튼 글자 색상 수정 (`Sidebar.tsx` btn-primary 텍스트 오버라이드)
  - [x] 모바일에서 문서 수정/삭제 아이콘 항시 노출 (`Sidebar.tsx` opacity 반응형 클래스 변경)
  - [x] 모바일에서는 사이드바가 열렸을 때만 15초 주기 조건부 폴링 기능 구현 (`Sidebar.tsx` useEffect 최적화)
  - [x] 백엔드 단순 일상 대화("안녕" 등) 분류 및 가이드 대화 라우팅 추가 (`agentic_graph.py` 수정)
- [x] 3차 UX 피드백 반영 및 검증
  - [x] 메시지 전송 버튼 비활성화 시 금지 커서 제거 (`ChatInput.tsx` 수정)
  - [x] 프론트엔드 빌드 검증 (`npm run build` 통과)
- [x] 검증 및 빌드 확인
  - [x] 로컬 제목 추출 및 안녕 라우팅 테스트 진행 (안녕 일반대화 라우팅 테스트 완료)
  - [x] 프론트엔드 빌드 검증 (`npm run build` 통과)
  - [x] Git 원격 브랜치 커밋 및 PR 생성 (PR #4 생성 및 머지 완료)
- [ ] 답변 품질 개선 (알람코드, 표, 도면 인식률)
- [ ] 여러 PDF 문서 관리 (삭제, 정렬 등)

## 완료된 작업 (Completed Tasks)
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

