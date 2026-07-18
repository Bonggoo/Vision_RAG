# 📑 TechNote (테크노트)

> **Vectorless Agentic Vision RAG** — 벡터 DB 없이 AI 에이전트가 매뉴얼을 탐색하는 차세대 검색 시스템

산업용 매뉴얼(PDF)을 AI가 **인간처럼 목차를 읽고 → 해당 페이지를 찾아가서 → 원본을 그대로 분석**하여 답변합니다.

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **3단계 하이브리드 추론** | Phase 0+1(문서 선택+ToC) → Phase 2(텍스트 정밀 탐색) → Phase 3(Vision 분석) 통합 |
| **되묻기 (Clarification)** | 문서 선택 확신도가 낮을 때 SSE `clarification` 이벤트로 사용자에게 장비 선택 UI를 띄워 정밀 재탐색 |
| **대화 GCS 영속 저장** | 대화 히스토리를 GCS(`users/{email}/conversations/`)에 영속화하여 기기 간 세션 이어보기 지원 |
| **대화 맥락 유지** | 직전 답변의 참조 문서 ID·페이지를 다음 질문에 힌트로 전달하여 꼬리 질문 정확도 향상 |
| **구글 OAuth & JWT 보안** | 구글 로그인 및 검증을 거쳐 백엔드 API를 완벽하게 보호하는 JWT Access/Refresh 인증 시스템 |
| **사용자 격리 (멀티테넌시)** | 유저 이메일(`owner_email`) 기반의 매뉴얼 문서 격리 및 대화 세션 분리 적용 |
| **현장 장비 알람 이미지 RAG** | 스마트폰 카메라/갤러리로 촬영된 현장 장비 이미지(Base64) 전송 및 Gemini Vision 전처리 RAG 연동 |
| **대용량 비동기 GCS 업로드** | Pre-flight 해시 사전 중복 검증, 브라우저 ↔ GCS Direct 업로드(서버 메모리 보호) 및 FastAPI BackgroundTasks 비동기 분석 |
| **GCS Signed URL 다운로드** | UTF-8 한글 명세(RFC 5987) 준수 및 고속 서명 다운로드 링크(Signed URL) 제공 |
| **Vision 기반 ToC 자동 보강** | PDF 목차 페이지를 자동 탐색하여 3레벨 계층 목차 추출 (최대 291개 항목) |
| **AI 제조사/모델 자동 분류** | 업로드 시 Gemini Vision을 통해 표지를 분석하여 제조사 및 모델 시리즈를 자동 매핑 |
| **사이드바 2단 아코디언 트리** | 제조사 > 모델 시리즈 2단 아코디언 트리 제공 (문서가 3개 이하일 땐 스마트 플랫 리스트로 자동 대응) |
| **인라인 메타데이터 수정** | 사이드바에서 문서명, 제조사, 모델을 실시간 수정 가능 (기존 제조사 리스트 자동완성 추천 제공) |
| **SHA-256 중복 업로드 방지** | 파일 내용의 해시값을 대조하여 이미 등록된 파일 재업로드 원천 차단 (409 Conflict) |
| **빈 파일 검증** | 0바이트 파일 업로드 시 범용적이고 직관적인 경고 메시지 표출 |
| **실시간 문서 검색** | 사이드바 상단 검색창에서 문서명, 제조사, 모델을 실시간 검색 필터링 |
| **대화 마크다운 내보내기** | 활성 대화의 메시지 및 추론 과정(Reasoning Steps)까지 구조화된 마크다운(.md) 파일로 즉시 다운로드 |
| **적응형 웰컴 온보딩** | 보유 문서가 없는 신규 사용자에게 온보딩/업로드 유도 화면을 노출하고, 문서 로딩 중에도 온보딩↔질문 화면 플래시 없이 매끄럽게 전환 |
| **인앱 토스트 & 확인창** | 네이티브 `alert()/confirm()`를 대체하는 전역 토스트 알림 + 확인 다이얼로그 (성공/실패/중복 업로드 결과를 구조화해 안내, 파괴적 동작은 위험 스타일) |
| **세션 갱신 회복력** | 토큰 리프레시 서버가 일시 오류(5xx/네트워크)일 때 강제 로그아웃하지 않고 기존 세션을 유지, 실제 만료(401)에서만 로그아웃 |
| **PWA 지원** | 홈 화면 설치, 전체화면 모드, 오프라인 캐싱 (갤럭시/iOS 모두 지원) |
| **프리미엄 UI** | 딥 네이비/바이올렛 다크모드, 글래스모피즘, 모바일 최적화 레이아웃 |

---

## 🏗 아키텍처

```text
┌─────────────┐    ┌──────────────────────────────┐    ┌──────────────┐
│  사용자 질문   │───▶│  Phase 0+1: 문서 선택 + ToC 추론  │───▶│  섹션 특정     │
│  (Query)    │    │  (Flash-Lite, 텍스트 기반)       │    │  (Target)    │
└─────────────┘    └──────────────────────────────┘    └──────┬───────┘
                          │ (확신도 낮을 시)                      │
                          ▼                                    │
                   ┌──────────────┐                           ▼
                   │  되묻기 UI    │    ┌──────────────────────────────┐
                   │ (Clarif.)   │    │  Phase 2: 텍스트 정밀 탐색      │
                   └──────────────┘    │  (비동기, 최대 50페이지)        │
                                       └──────────────┬───────────────┘
                                                      │
                                                      ▼
┌─────────────┐    ┌──────────────────────────────┐    ┌──────────────┐
│  Phase 3    │◀───│  Vision LLM 분석              │◀───│  미니 PDF     │
│  최종 답변    │    │  (미니 PDF → 시각 정보 직접 분석)  │    │  추출         │
│  (마크다운)   │    │  (Flash-Lite 통일, 비용 최적화)  │    │              │
└─────────────┘    └──────────────────────────────┘    └──────────────┘
```

---

## 🛠 기술 스택

| 레이어 | 기술 |
|--------|------|
| **Frontend** | Next.js 16.2 + React 19 + Zustand 5 + TailwindCSS 4 |
| **Backend** | Python 3.10+ / FastAPI 0.136 |
| **PDF 처리** | PyMuPDF 1.27 (fitz) — ToC 추출, 미니 PDF, 썸네일 |
| **AI Model** | Gemini Flash-Lite (`google-genai` SDK — 추론/탐색/Vision 전 구간 통합) |
| **Orchestration** | LangChain Core 1.4 + LangChain Google GenAI 4.2 + LangGraph 1.2 |
| **Security & Auth** | JWT Access & Refresh Token + Google OAuth |
| **Storage** | Google Cloud Storage (GCS) — 문서 및 대화 세션 모두 저장 |
| **배포** | Vercel (프론트) + Cloud Run (백엔드, asia-northeast3) |
| **PWA** | 수동 Service Worker + Web App Manifest |

---

## 🚀 설치 및 실행

### 1. 환경 변수 설정

```bash
# backend/.env
GEMINI_API_KEY=your_gemini_api_key
GCS_BUCKET_NAME=your_gcs_bucket_name
GOOGLE_CLIENT_ID=your_google_oauth_client_id
JWT_SECRET=your_jwt_secret_key

# 아래는 선택사항 (기본값 있음)
# GEMINI_MODEL_NAME=gemini-2.0-flash-lite
# ALLOWED_ORIGINS=http://localhost:3000

# frontend/.env.local
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_GOOGLE_CLIENT_ID=your_google_oauth_client_id
```

### 2. 백엔드 실행

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

### 3. 프론트엔드 실행

```bash
cd frontend
npm install
npm run dev
# → http://localhost:8374
```

---

## 📡 API 개요

| 메서드 | 엔드포인트 | 기능 | 인증 |
|--------|-----------|------|------|
| `POST` | `/api/auth/google` | 구글 OAuth ID Token 검증 및 백엔드 JWT 발급 | 필요 없음 |
| `POST` | `/api/auth/refresh` | JWT Refresh Token을 통한 신규 Access Token 재발급 | 필요 없음 |
| `POST` | `/api/auth/logout` | 로그아웃 (Refresh Token 쿠키 파기) | **필수** |
| `POST` | `/upload` | [동기식] PDF 업로드 + ToC 추출 (소형 파일용) | **필수** |
| `POST` | `/upload/preflight` | [비동기식] SHA-256 중복 체크 및 GCS Signed URL 발급 | **필수** |
| `POST` | `/upload/analyze` | [비동기식] 업로드 완료 후 백그라운드 AI 분석 트리거 | **필수** |
| `POST` | `/upload/toc` | 스캔 PDF 목차 범위 지정 재추출 | **필수** |
| `GET` | `/documents` | 로그인 사용자가 소유한 문서 목록 조회 | **필수** |
| `GET` | `/documents/{id}` | 문서 상세 정보 | **필수** |
| `PATCH` | `/documents/{id}` | 메타데이터(파일명, 제조사, 모델) 수정 | **필수** |
| `DELETE` | `/documents/{id}` | 문서 삭제 | **필수** |
| `GET` | `/documents/{id}/download` | [서버 중개] 문서 PDF 직접 다운로드 | **필수** |
| `GET` | `/documents/{id}/download-url` | [고속] GCS Signed URL 다운로드 서명 링크 발급 | **필수** |
| `POST` | `/documents/reclassify` | 미분류 문서 일괄 Gemini Vision 재분류 (백그라운드) | **필수** |
| `GET` | `/documents/{id}/toc` | ToC 전체 조회 | **필수** |
| `POST` | `/documents/{id}/reindex` | Vision 기반 ToC 재추출 | **필수** |
| `POST` | `/chat/stream` | 질의·응답 및 첨부 이미지 분석 (SSE 스트리밍) | **필수** |
| `POST` | `/conversations/` | 새 대화 세션 생성 | **필수** |
| `GET` | `/conversations/` | 대화 세션 목록 조회 | **필수** |
| `GET` | `/conversations/{session_id}` | 대화 세션 상세 조회 | **필수** |
| `DELETE` | `/conversations/{session_id}` | 대화 세션 삭제 | **필수** |
| `PATCH` | `/conversations/{session_id}/rename` | 대화 제목 변경 | **필수** |

---

## 📁 프로젝트 구조

```
TechNote/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI 앱 + lifespan + CORS + 라우터 등록
│   │   ├── config.py                 # 환경 변수 설정 (Pydantic Settings)
│   │   ├── exceptions.py             # 커스텀 예외 정의
│   │   ├── prompts.py                # LLM 프롬프트 모음 (외부화)
│   │   ├── routers/
│   │   │   ├── auth.py               # 구글 OAuth & 토큰 재발급 라우터
│   │   │   ├── chat.py               # 질의·응답 SSE 스트리밍 라우터
│   │   │   ├── conversations.py      # 대화 세션 CRUD 라우터 (GCS 영속)
│   │   │   ├── documents.py          # 문서 관리 CRUD 라우터
│   │   │   └── upload.py             # 업로드 및 ToC 재추출 라우터
│   │   ├── services/
│   │   │   ├── auth_service.py       # 구글 ID Token 검증 및 JWT 발급 서비스
│   │   │   ├── agentic_graph.py      # 3단계 파이프라인 (PipelineContext + stage 분해)
│   │   │   ├── agent_service.py      # Gemini LLM 호출 (ToC, Vision)
│   │   │   ├── conversation_service.py # GCS 기반 대화 세션 저장/조회
│   │   │   ├── metadata_service.py   # 문서 메타데이터 CRUD (GCS)
│   │   │   └── pdf_service.py        # PDF 처리 + ToC 추출 전략(build_toc)
│   │   ├── schemas/
│   │   │   ├── request.py            # 요청 스키마 (ChatRequest 등)
│   │   │   └── response.py           # 응답 스키마 (UploadResponse 등)
│   │   └── utils/                    # 로거 및 유틸리티
│   ├── Dockerfile                    # Cloud Run 배포용 컨테이너 이미지
│   ├── cloudbuild.yaml               # GitHub → Cloud Run 자동 배포
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx              # 메인 페이지 (로그인 가드 + 채팅, useChatStream 훅)
│   │   │   ├── layout.tsx            # 루트 레이아웃 (메타, 폰트)
│   │   │   └── globals.css           # 디자인 시스템 (oklch, 글래스모피즘)
│   │   ├── components/
│   │   │   ├── chat/                 # ChatMessage(마크다운/참조 이미지), ExportButton
│   │   │   ├── layout/               # Header, ChatInput, LoginView, SparkleLogo
│   │   │   │   └── sidebar/          # Sidebar 분해 (DocSearchBar/SortToggle/DocItem/DocTree)
│   │   │   └── ui/                   # Toaster·ConfirmDialog (전역 토스트/확인창, layout에 마운트)
│   │   ├── hooks/useChatStream.ts    # SSE 스트리밍 파싱 훅 (page.tsx에서 분리)
│   │   ├── types/                    # 공유 타입 (chat/sse/api)
│   │   ├── store/
│   │   │   ├── useAuthStore.ts       # 구글 로그인 사용자 정보 및 JWT 토큰 보관 (리프레시 일시 오류 관용)
│   │   │   ├── useChatStore.ts       # 채팅 세션 상태 (GCS 연동)
│   │   │   ├── useDocumentStore.ts   # 문서 목록 상태
│   │   │   └── useUIStore.ts         # 전역 UI 상태 (toast.* / confirmDialog() 헬퍼)
│   │   └── lib/
│   │       ├── api.ts                # JWT 자동 갱신 + 401 재시도 API 클라이언트
│   │       └── upload.ts             # 업로드 공통 처리 (사이드바+웰컴 온보딩 공용, 결과 토스트)
│   └── package.json
├── doc/
│   ├── README.md                     # 📖 문서 인덱스 (여기부터 시작)
│   ├── PRD.md                        # 제품 요구사항 정의서
│   ├── API_Contract.md               # API 규약
│   ├── remaining_tasks.md            # 잔여 작업 + 완료 현황 + 향후 로드맵 마스터 보드
│   ├── audit_findings_2026-07.md     # 전체 코드 감사(UI/UX·보안·백엔드) 결과
│   ├── refactoring_plan.md           # 코드 구조 리팩토링 로드맵 및 진행 현황 (완료)
│   ├── security_roadmap.md           # 중장기 보안 개선 로드맵
│   ├── async_upload_roadmap.md       # 대용량 비동기 업로드 파이프라인 설계 (완료)
│   ├── gcs_signed_url_roadmap.md     # GCS Signed URL 다운로드 설계 (완료)
│   ├── near_duplicate_document_handling.md # 유사(중복) 문서 처리 ADR (L1 채택)
│   ├── custom_domain_mapping.md      # 커스텀 도메인 매핑 가이드
│   ├── content_plan.md               # 데모 영상·기술 블로그 콘텐츠 플랜
│   └── 질문.md                        # 대화 품질 평가용 골든 질문셋
├── backend/evals/                    # 질문 품질 자동 평가 하네스 (골든/생성/Claude 500문항)
└── gcs_cors.json                     # GCS CORS 설정
```

---

## 📊 테스트 결과

| 질문 | 결과 |
|------|------|
| 원점결정 버퍼메모리 주소 | ✅ `1500+100n` / `4300+100n` + Cd.3 |
| 알람코드 104 의미 | ✅ 하드웨어 스트로크 리미트+ |
| 알람코드 2505 분류 | ✅ 서보앰프 에러 (2000~2999) |
| 버퍼메모리 2800 기능 | ✅ 19번축 Pr.91 임의 데이터 모니터 |
| 멀티턴: "그 근처 주소들" | ✅ 2791~2803 주변 주소 목록 |
| 전체 벤치마크 | ✅ 93.33% 성공률 |

---

## 📝 라이선스

MIT License
