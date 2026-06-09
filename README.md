# 📑 TechNote (테크노트)

> **Vectorless Agentic Vision RAG** — 벡터 DB 없이 AI 에이전트가 매뉴얼을 탐색하는 차세대 검색 시스템

산업용 매뉴얼(PDF)을 AI가 **인간처럼 목차를 읽고 → 해당 페이지를 찾아가서 → 원본을 그대로 분석**하여 답변합니다.

---

## ✨ 주요 기능

| 기능 | 설명 |
|------|------|
| **3단계 하이브리드 추론** | Phase 0+1(문서 선택+ToC) → Phase 2(텍스트 정밀 탐색) → Phase 3(Vision 분석) 통합 |
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
| **PWA 지원** | 홈 화면 설치, 전체화면 모드, 오프라인 캐싱 (갤럭시/iOS 모두 지원) |
| **프리미엄 UI** | 딥 네이비/바이올렛 다크모드, 글래스모피즘, 모바일 최적화 레이아웃 |

---

## 🏗 아키텍처

```text
┌─────────────┐    ┌──────────────────────────────┐    ┌──────────────┐
│  사용자 질문   │───▶│  Phase 0+1: 문서 선택 + ToC 추론  │───▶│  섹션 특정     │
│  (Query)    │    │  (Flash-Lite, 텍스트 기반)       │    │  (Target)    │
└─────────────┘    └──────────────────────────────┘    └──────┬───────┘
                                                              │
                                                              ▼
┌─────────────┐    ┌──────────────────────────────┐    ┌──────────────┐
│  Phase 3    │◀───│  Vision LLM 분석              │◀───│  Phase 2:    │
│  최종 답변    │    │  (미니 PDF → 시각 정보 직접 분석)  │    │  텍스트 정밀   │
│  (마크다운)   │    │  (Flash-Lite 통일, 비용 최적화)  │    │  페이지 탐색   │
└─────────────┘    └──────────────────────────────┘    └──────────────┘
```

---

## 🛠 기술 스택

| 레이어 | 기술 |
|--------|------|
| **Frontend** | Next.js 15.2 + React 19 + Zustand 5 + TailwindCSS 4 |
| **Backend** | Python 3.10+ / FastAPI 0.136 |
| **PDF 처리** | PyMuPDF 1.27 (fitz) — ToC 추출, 미니 PDF, 썸네일 |
| **AI Model** | Gemini 3.1 Flash-Lite (추론/탐색/Vision 전 구간 통합 적용) |
| **Orchestration** | LangChain Core 1.4 + LangChain Google GenAI 4.2 |
| **Security & Auth** | JWT Access & Refresh Token + Google OAuth |
| **Storage** | Google Cloud Storage (GCS) |
| **배포** | Vercel (프론트) + Cloud Run (백엔드) |
| **PWA** | 수동 Service Worker + Web App Manifest |

---

## 🚀 설치 및 실행

### 1. 환경 변수 설정

```bash
# backend/.env
GEMINI_API_KEY=your_gemini_api_key
# 아래는 선택사항 (기본값 있음)
# GEMINI_MODEL_NAME=gemini-3.1-flash-lite
# ALLOWED_ORIGINS=http://localhost:3000
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
# → http://localhost:3000
```

---

## 📡 API 개요

| 메서드 | 엔드포인트 | 기능 | 인증 |
|--------|-----------|------|------|
| `POST` | `/api/auth/google` | 구글 OAuth ID Token 검증 및 백엔드 JWT 발급 | 필요 없음 |
| `POST` | `/api/auth/refresh` | JWT Refresh Token을 통한 신규 Access Token 재발급 | 필요 없음 |
| `POST` | `/upload` | [동기식] PDF 업로드 + ToC 추출 (20MB 미만 소형 파일용) | **필수** |
| `POST` | `/upload/preflight` | [비동기식] 업로드 사전 검증 (SHA-256 중복 체크 및 GCS Signed URL 발급) | **필수** |
| `POST` | `/upload/analyze` | [비동기식] 업로드 완료 후 백그라운드 AI 분석(ToC + Vision 분류) 트리거 | **필수** |
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

---

## 📁 프로젝트 구조

```
TechNote/
├── backend/
│   ├── app/
│   │   ├── main.py                   # FastAPI 앱 + CORS + 라우터 등록
│   │   ├── config.py                 # 환경 변수 설정 (Pydantic Settings)
│   │   ├── exceptions.py             # 커스텀 예외 정의
│   │   ├── routers/
│   │   │   ├── auth.py               # 구글 OAuth & 토큰 재발급 라우터
│   │   │   ├── chat.py               # 질의·응답 SSE 스트리밍 라우터
│   │   │   ├── documents.py          # 문서 관리 CRUD 라우터
│   │   │   └── upload.py             # 업로드 및 ToC 재추출 라우터
│   │   ├── services/
│   │   │   ├── auth_service.py       # 구글 ID Token 검증 및 JWT 발급 서비스
│   │   │   ├── agentic_graph.py      # 3단계 하이브리드 추론 파이프라인
│   │   │   ├── agent_service.py      # Gemini LLM 호출 (ToC, Vision)
│   │   │   ├── metadata_service.py   # 문서 메타데이터 CRUD (로컬 & GCS)
│   │   │   └── pdf_service.py        # PDF 처리 + ToC 추출 전략
│   │   ├── schemas/
│   │   │   ├── request.py            # 요청 스키마 (ChatRequest 등)
│   │   │   └── response.py           # 응답 스키마 (UploadResponse 등)
│   │   └── utils/                    # 로거 및 유틸리티
│   └── requirements.txt
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx              # 메인 페이지 (웰컴 + 채팅)
│   │   │   ├── login/                # 글래스모피즘 구글 로그인 페이지
│   │   │   ├── layout.tsx            # 루트 레이아웃 (메타, 폰트)
│   │   │   └── globals.css           # 디자인 시스템 (oklch, 글래스모피즘)
│   │   ├── components/
│   │   │   ├── chat/ChatMessage.tsx   # 채팅 메시지 (마크다운, 참조 이미지)
│   │   │   ├── layout/               # Sidebar, Header, ChatInput
│   │   │   └── ServiceWorkerRegister.tsx  # PWA Service Worker 등록
│   │   ├── store/
│   │   │   ├── useAuthStore.ts       # 구글 로그인 사용자 정보 및 JWT 토큰 보관
│   │   │   ├── useChatStore.ts       # 채팅 세션 상태 (persist)
│   │   │   └── useDocumentStore.ts   # 문서 목록 상태
│   │   └── lib/api.ts                # JWT 인증 연동 API 클라이언트
│   └── package.json
└── doc/
    ├── PRD.md                        # 제품 요구사항 정의서
    ├── API_Contract.md               # API 규약
    ├── async_upload_roadmap.md       # 대용량 비동기 GCS 업로드 아키텍처 보고서
    ├── gcs_signed_url_roadmap.md     # GCS Signed URL 고속 다운로드 보고서
    ├── improvement_list.md           # 개선 및 고도화 요구사항 정의서
    └── security_roadmap.md           # 중장기 보안 개선 로드맵 보고서
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

---

## 📝 라이선스

MIT License
