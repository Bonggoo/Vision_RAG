---
name: technote-deploy-check
description: TechNote(Vision_RAG) 백엔드를 master에 푸시한 뒤 Cloud Build → Cloud Run 배포가 실제로 반영됐는지 확인합니다. 사용자가 "배포됐나 확인해줘", "푸시했는데 반영됐어?", "배포 상태", "빌드 성공했나", "서버 살아있나", "롤백해야 하나", "이거 푸시하면 배포되나?" 같은 말을 하거나, backend/ 변경을 master에 푸시한 직후일 때 반드시 사용하세요. 배포 트리거가 backend/** 경로 변경에만 반응해서 "푸시했는데 왜 그대로냐"는 혼동이 자주 생기므로, 배포 여부가 조금이라도 걸리면 사용합니다.
---

# TechNote 배포 반영 확인

`master`에 푸시하면 Cloud Build가 백엔드 이미지를 빌드해 Cloud Run에 새 리비전으로 올립니다.
여기서 확인할 것은 "빌드가 성공했나"만이 아니라 **내 커밋이 실제로 서비스되고 있나**입니다.

## 먼저 알아야 할 함정: 트리거는 `backend/**` + `frontend/**`에 반응합니다

배포 트리거 `deploy-vision-rag-backend`의 설정 (2026-07-21 통합 오리진 전환 이후):

- 저장소 `Bonggoo/Vision_RAG`, 브랜치 `^master$`, 빌드 파일 `backend/cloudbuild.yaml`
- **`includedFiles: backend/**, frontend/**`**

프론트엔드(Next.js)는 이제 Vercel이 아니라 **이 파이프라인이 정적 export하여 백엔드
컨테이너에 같이 담아 배포**합니다(통합 오리진 — iOS 로그인 유지 문제 해결을 위한 구조).
그래서 `frontend/`만 고쳐도 이 트리거가 돕니다. `backend/`도 `frontend/`도 안 건드린
커밋(문서 등)일 때만 빌드가 안 도는 게 정상입니다. "푸시했는데 배포가 안 떴다" 싶으면:

```bash
git show --stat --oneline HEAD | head -20
```

빌드 단계도 프론트 빌드(`node:20`, `npm ci && next build`)가 먼저 돌고 나서 기존
docker build/push/deploy가 이어지므로, 아래 5분대 소요 시간에 1~2분 정도 더 걸립니다.

## 확인 순서

### 1. 푸시된 커밋 확인

```bash
git log --oneline -1 origin/master
```

로컬이 앞서 있으면 아직 푸시 전입니다. 푸시 자체는 사용자가 명시적으로 요청했을 때만 하세요.

### 2. 빌드 상태

```bash
gcloud builds list --limit 3 --format="value(id,status,substitutions.COMMIT_SHA,createTime)"
```

맨 위 항목의 `COMMIT_SHA`가 방금 푸시한 커밋과 앞 7자리라도 일치하는지 확인합니다.
일치하는 빌드가 아예 없으면 트리거가 안 걸린 것이니 위의 `backend/**` 조건을 다시 보세요.

**빌드는 보통 5분 남짓 걸립니다**(최근 5회 5.1~5.6분). `WORKING` 상태면 기다렸다 다시 확인하되,
셸을 붙잡고 스트리밍하지 말고 주기적으로 폴링하세요 — 명령 타임아웃에 걸립니다.

실패했다면 원인을 봅니다:

```bash
gcloud builds log <BUILD_ID> 2>&1 | tail -40
```

### 3. 서비스에 반영됐는지

```bash
gcloud run services describe vision-rag-backend --region asia-northeast3 \
  --format="value(status.url,status.latestReadyRevisionName)"
```

빌드가 SUCCESS인데 리비전이 그대로면 배포 단계에서 멈춘 것입니다(3단계 `gcloud run deploy`).

### 4. 헬스체크 — 콜드스타트를 장애로 오인하지 마세요

```bash
curl -s -w "\nHTTP %{http_code} in %{time_total}s\n" \
  https://vision-rag-backend-sfsbvktuia-du.a.run.app/api/health
```

`{"message":"Vision RAG API Server is running"}` + HTTP 200이면 정상입니다.

⚠️ **`/healthz`는 절대 쓰지 마세요.** Cloud Run(Knative) 인프라가 이 경로를 자체 내부
헬스체크용으로 예약해서, 컨테이너까지 도달하지 않고 Google 자체 404 페이지로 가로챕니다
(실측으로 확인함 — 로그에 요청 자체가 안 찍힘). 헬스체크는 반드시 `/api/health`로.

루트(`/`)는 이제 **정적 프론트엔드(index.html)를 서빙**합니다(통합 오리진 구조).
200 응답은 오지만 예전처럼 JSON 헬스 메시지가 아니라 HTML이 오니, "떠 있다"는
확인용으로만 참고하고 정확한 헬스체크는 `/api/health`를 쓰세요.

`--min-instances=0`이라 유휴 상태 뒤 첫 요청은 **10초 안팎이 정상**입니다(실측 9.2초).
느리다고 장애로 보고하지 말고, 한 번 더 호출해 두 번째 응답이 빠른지로 판단하세요.
`/api/health`도 인증이 면제돼 있어 토큰이 필요 없습니다.

### 5. 실제 동작 스모크

헬스체크는 프로세스가 떴다는 것만 말해줍니다. 파이프라인이 도는지는 따로 확인하세요:

```bash
# backend/ 에서 — 배포된 백엔드를 대상으로 소규모 실행
venv/bin/python -m evals.run_eval --only greeting
```

`evals/.env`의 `EVAL_JWT_SECRET`으로 토큰을 자체 발급합니다. 여기서 401이 나면 배포된
`JWT_SECRET`과 어긋난 것이니, 서비스 장애가 아니라 시크릿 설정 문제로 보고하세요.

라우팅·검색 로직을 건드린 배포라면 스모크만으로는 부족합니다. 품질 회귀 확인은
`technote-eval` 스킬로 이어가세요 — 축별 해석 규칙이 거기 있습니다.

## 보고 형식

```
- 커밋: <sha> <제목>
- 빌드: SUCCESS (N분) / 또는 미실행 사유
- 리비전: vision-rag-backend-000NN-xxx
- 헬스: HTTP 200 (N초, 콜드스타트 여부)
- 스모크: N/N 통과
→ 배포 정상 반영 / 또는 문제 지점
```

## 문제가 있을 때

빌드가 깨졌거나 새 리비전이 오류를 내면 **되돌리기부터 제안**하고, 원인 분석은 그다음입니다.
프로덕션이 깨진 채로 디버깅하지 마세요.

```bash
# 직전 정상 리비전 확인
gcloud run revisions list --service vision-rag-backend --region asia-northeast3 --limit 5

# 트래픽 되돌리기 (실행 전 사용자 확인 필수)
gcloud run services update-traffic vision-rag-backend --region asia-northeast3 \
  --to-revisions=<이전_리비전>=100
```

트래픽 전환은 사용자에게 영향을 주는 되돌리기 어려운 작업입니다. 어떤 리비전으로 되돌릴지
근거와 함께 제시하고 **사용자 승인을 받은 뒤에** 실행하세요. 배포·푸시도 마찬가지로
사용자가 요청했을 때만 합니다.
