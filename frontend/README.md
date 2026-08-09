# TechNote — Frontend

Next.js (App Router) + Tailwind + Zustand PWA. TechNote(Vision_RAG)의 채팅 UI로,
백엔드의 Agentic PDF RAG 파이프라인에 SSE로 붙습니다.

프로젝트 전반의 구조·규칙은 저장소 루트의 `CLAUDE.md`를 보세요.

> **주의:** 이 저장소의 Next.js는 널리 알려진 버전과 API·관례가 다를 수 있습니다.
> 코드를 쓰기 전에 `node_modules/next/dist/docs/`의 해당 가이드를 먼저 확인하세요 (`AGENTS.md`).

## 개발 서버

```bash
npm install
npm run dev
```

http://localhost:8374 에서 열립니다 (`next dev -p 8374`).

**백엔드를 먼저 띄우세요.** 부팅 직후 `GET /documents`로 세션을 검증하기 때문에,
백엔드가 없으면 첫 화면부터 오류 상태로 들어갑니다.

```bash
cd ../backend && source venv/bin/activate && uvicorn app.main:app --reload
```

API 주소는 `.env.local`의 `NEXT_PUBLIC_API_URL`(로컬 기본값 `http://localhost:8000`)로 지정합니다.
Google OAuth는 로컬에서 막혀 있어 그냥 띄우면 로그인 화면에서 멈춥니다 — 개발용 토큰 주입 절차는
`.claude/skills/technote-dev-stack/SKILL.md`에 있습니다.

## 스크립트

| 명령 | 설명 |
|---|---|
| `npm run dev` | 개발 서버 (포트 8374) |
| `npm run build` | 프로덕션 빌드 (배포 시 정적 export) |
| `npm run start` | 빌드 결과 서빙 |
| `npm run lint` | ESLint |

## 구조

- `src/app/page.tsx` — 문서 유무에 따라 웰컴/온보딩과 채팅 화면을 전환하는 진입점
- `src/components/layout/` — Sidebar, ChatInput 등 레이아웃 구성요소
- `src/store/` — Zustand 스토어 (`useAuthStore`, `useDocumentStore`, `useChatStore`, `useUIStore`)
- `src/app/globals.css` — 디자인 토큰. 라이트/다크 모두 claude.ai 색상 스케일을 따릅니다
  (`bg-100`=배경 · `bg-000`=표면 · `bg-200`=사이드바 · `bg-300`=호버)

폰트는 `next/font/google`로 Inter, Noto Sans KR, Source Serif 4, JetBrains Mono를 로드합니다.

네이티브 `alert()`/`confirm()`은 쓰지 않습니다. `useUIStore`의 `toast` / `confirmDialog`를 쓰세요.

## 배포

**별도로 배포하지 않습니다.** 통합 오리진 구조라, `master`에 푸시하면 백엔드의
Cloud Build 파이프라인이 이 앱을 정적 export 해서 백엔드 컨테이너에 담아 함께 올립니다
(`backend/cloudbuild.yaml` 0단계). 배포된 서비스에서 `/`는 이 프론트엔드를, `/api/*`는
백엔드를 같은 도메인에서 서빙하며, 그 덕분에 iOS에서 로그인 세션이 유지됩니다.

`frontend/**` 변경만으로도 트리거가 걸립니다. 자세한 내용은 루트 `CLAUDE.md`의 Deployment 절 참고.
