---
name: technote-dev-stack
description: TechNote(Vision_RAG)를 로컬에서 백엔드+프론트엔드 함께 띄우고, Google 로그인을 우회하는 개발용 토큰을 주입해 로그인된 화면까지 만들어줍니다. 사용자가 "로컬에서 띄워줘", "앱 실행", "브라우저로 확인", "화면 보여줘", "직접 눌러봐", "프론트 확인", "실제로 동작하나 봐줘", "dev 서버" 같은 말을 하거나, UI·업로드·채팅 흐름 변경을 눈으로 검증해야 할 때 반드시 사용하세요. 이 앱은 Google OAuth 로그인이 막혀 있어 그냥 띄우면 로그인 화면에서 멈추므로, 매번 토큰 주입 절차가 필요합니다.
---

# TechNote 로컬 풀스택 구동 + 개발용 로그인

브라우저로 직접 확인해야 할 때 쓰는 절차입니다. 그냥 서버만 띄우면 **로그인 화면에서 막힙니다** —
Google OAuth는 대신 자격증명을 입력할 수 없기 때문입니다. 개발용 JWT를 직접 발급해
localStorage에 심는 것이 이 스킬의 핵심입니다.

## 전제 — 이미 로컬용으로 배선돼 있습니다

확인만 하고 바꾸지 마세요. 값이 다르면 그때 사용자에게 알리고 물어보세요.

- `backend/.env` → `USE_LOCAL_STORAGE=True` (GCS 대신 로컬 파일시스템), `PDF_UPLOAD_DIR=./uploads`, `PORT=8000`
- `frontend/.env.local` → `NEXT_PUBLIC_API_URL=http://localhost:8000`
- 문서는 `backend/uploads/<doc_id>/`, 대화 기록은 그 옆 `conversations/<email>/`에 쌓입니다.
- 외부 의존성은 Gemini API 하나뿐입니다(`GEMINI_API_KEY`). GCS는 이 모드에서 아예 호출되지 않습니다.

## 1. 서버 띄우기

**Bash로 서버를 실행하지 마세요.** `.claude/launch.json`에 `backend`/`frontend` 설정이 있으니
preview_start로 띄웁니다. 백그라운드 프로세스가 세션에 묶여 관리되고, 로그도 읽을 수 있습니다.

```
preview_start {name: "backend"}    # venv/bin/uvicorn app.main:app --reload --port 8000
preview_start {name: "frontend"}   # npm run dev -p 8374
```

**백엔드를 먼저 띄우세요.** 프론트가 부팅 직후 `GET /documents`로 세션을 검증하기 때문에,
백엔드가 없으면 첫 화면에서 불필요한 오류 상태로 들어갑니다.

백엔드가 부팅에 실패하면 대개 `backend/.env` 문제입니다. `app/config.py`의 pydantic Settings가
선언되지 않은 키를 거부해서 `extra_forbidden`으로 죽습니다 — `preview_logs`로 확인하세요.

## 2. 개발용 로그인 주입

토큰을 앱 자신의 인증 코드로 발급합니다. 시크릿이 바뀌어도 따라가므로 하드코딩보다 안전합니다.

```bash
# backend/ 에서
venv/bin/python -c "
from datetime import timedelta
from app.services.auth_service import create_access_token
print(create_access_token(
    data={'email':'choibong975@gmail.com','name':'Dev','picture':''},
    expires_delta=timedelta(hours=24)))
"
```

로컬 백엔드는 `backend/.env`에 `JWT_SECRET`이 없어 `config.py`의 기본 시크릿을 쓰므로,
이렇게 발급한 토큰이 그대로 검증을 통과합니다.

그다음 프론트 탭에서 localStorage에 심습니다. localStorage는 오리진별이라 **반드시
프론트 페이지가 열린 상태에서** 실행해야 합니다:

```js
localStorage.setItem('vision-rag-auth-storage', JSON.stringify({
  state: {
    token: '<위에서 발급한 JWT>',
    user: { email: 'choibong975@gmail.com', name: 'Dev', picture: '' },
    isAuthenticated: true
  },
  version: 0
}));
location.reload();
```

키 이름과 `{state, version}` 형태는 `useAuthStore`의 zustand persist 설정에서 온 것입니다
(`partialize`가 token/user/isAuthenticated만 저장). 형태가 어긋나면 조용히 무시되고
로그인 화면으로 되돌아가므로, 리로드 후 사이드바에 문서 목록이 보이는지로 확인하세요.

주의: refresh token은 httpOnly 쿠키라 이 방식으로는 없습니다. 24시간 뒤 access token이 만료되면
갱신에 실패해 로그아웃되니, 그때는 토큰을 다시 발급해 심으면 됩니다.

## 3. 검증

수동 확인을 사용자에게 떠넘기지 말고 직접 확인해서 근거를 제시하세요.

1. `read_console_messages`, `preview_logs`로 오류부터 확인
2. `read_page`로 로그인 통과와 화면 구조 확인 (사이드바에 문서가 뜨면 인증 성공)
3. 바꾼 흐름을 `computer`/`form_input`으로 실제로 눌러보고 `read_page`로 결과 확인
4. 시각적 변경이면 `computer {action:"screenshot"}`으로 증거 첨부

`backend/uploads`에 문서가 없으면 웰컴/온보딩 화면이 뜹니다 — 버그가 아니라
`app/page.tsx`의 적응형 화면입니다. 채팅 흐름을 보려면 문서를 먼저 업로드하세요.

## 4. 정리

확인이 끝나면 `preview_stop`으로 서버를 내립니다. 계속 볼 거라면 켜둬도 되지만,
`--reload`가 파일 변경마다 재시작하므로 대규모 리팩터링 중에는 로그가 시끄러워집니다.

## 프론트엔드 코드를 고칠 때

`frontend/AGENTS.md`가 경고하듯 이 저장소의 Next.js는 통상 알려진 버전과 API·관례가 다를 수 있습니다.
프론트 코드를 작성하기 전에 `node_modules/next/dist/docs/`의 해당 가이드를 먼저 읽으세요.

UI 문구·확인창은 네이티브 `alert()`/`confirm()` 대신 `useUIStore`의 `toast`/`confirmDialog`를 씁니다
(프로젝트 `CLAUDE.md` 규칙).
