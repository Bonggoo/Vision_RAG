# Cloud Run 서비스 복구 가이드

2026-10-02에 프로젝트를 멈추면서 Cloud Run 서비스 `vision-rag-backend`를 삭제하고, GCS 버킷을 비웠고, Gemini API 키를 폐기했다.
이 문서는 다시 시작할 때 따라 하기 위한 기록이다. **비밀 값은 일절 적지 않았다.**

- 프로젝트: `gen-lang-client-0031404090`, 리전: `asia-northeast3`
- 마지막 배포 URL: `https://vision-rag-backend-1023361734160.asia-northeast3.run.app`

## 삭제된 것 / 남은 것

| 항목 | 상태 |
|---|---|
| Cloud Run 서비스 `vision-rag-backend` | **삭제됨** |
| GCS 버킷 3개 (`vision-rag-uploads-…`, `…_cloudbuild`, `run-sources-…`) | **삭제됨** — 업로드된 PDF와 대화 기록은 복구 불가 |
| Gemini API 키 | **폐기** → 새 키 필요 |
| Cloud Build 트리거 `deploy-vision-rag-backend` | **삭제됨** — 복구 시 새로 만들어야 하며, 비밀 값도 함께 사라짐 |
| Artifact Registry `cloud-run-source-deploy`, `gcr.io` (이미지) | **삭제됨** — 복구 시 빌드가 이미지를 다시 만든다 |
| Cloud Tasks 큐 `vision-rag-analysis` | 남아 있음 |

이미지 저장소(`gcr.io`)는 첫 빌드의 푸시 때 자동으로 다시 생성된다. 안 되면 `gcloud artifacts repositories create gcr.io --repository-format=docker --location=us`로 만든다.

## 복구 순서

### 1. 새 Gemini API 키 발급
Google AI Studio에서 발급한다. `backend/.env`의 `GEMINI_API_KEY`도 새 값으로 바꾼다.

### 2. 새 비밀 값 생성
`JWT_SECRET`, `INTERNAL_TASK_SECRET`은 임의의 긴 문자열이면 된다. 새로 만들면 기존 로그인 세션은 모두 무효가 된다(문제 없음).
```bash
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
```

### 3. GCS 버킷 재생성
이름은 코드 기본값(`backend/app/config.py`의 `GCS_BUCKET_NAME`)과 같아야 한다.
```bash
gcloud storage buckets create gs://vision-rag-uploads-gen-lang-client-0031404090 --location=asia-northeast3
```
브라우저가 직접 업로드(Signed URL)하므로 **버킷 CORS 설정이 필요**하다. 삭제 전 설정은 기록해 두지 못했으므로, 허용 오리진(서비스 URL)·메서드(`PUT`, `GET`)·헤더(`Content-Type`)를 새로 지정한다.

### 4. 빌드 트리거 정비
- 트리거가 삭제됐으므로 새로 만든다. GitHub `Bonggoo/Vision_RAG`, 브랜치 `^master$`, 빌드 설정 `backend/cloudbuild.yaml`, 포함 파일 `backend/**`, `frontend/**`로 만들고 아래 6개 치환 변수를 채운다. `_GOOGLE_CLIENT_ID`는 Google Cloud Console의 OAuth 클라이언트에서, `_CLOUD_TASKS_QUEUE`는 큐의 전체 경로, `_CLOUD_RUN_URL`은 위 서비스 URL을 쓴다.
- 치환 변수의 이름 목록: `_GEMINI_API_KEY`, `_GOOGLE_CLIENT_ID`, `_JWT_SECRET`, `_CLOUD_TASKS_QUEUE`, `_CLOUD_RUN_URL`, `_INTERNAL_TASK_SECRET`

### 5. Cloud Tasks 큐 확인
큐 `vision-rag-analysis`(asia-northeast3)가 없으면 만든다. 값은 `_CLOUD_TASKS_QUEUE`와 맞춘다.

### 6. 배포
```bash
gcloud builds triggers run deploy-vision-rag-backend --branch=master
```
빌드는 약 6~7분. 서비스가 없어도 `gcloud run deploy`가 새로 만든다. `cloudbuild.yaml`이 아래 설정을 재현한다.
`--allow-unauthenticated`, cpu 2, memory 2Gi, min-instances 0, max-instances 20, concurrency 8, timeout 900s, `--cpu-throttling`, 포트 8080.

### 7. 확인
```bash
curl -s -o /dev/null -w '%{http_code}\n' https://vision-rag-backend-1023361734160.asia-northeast3.run.app/api/health
```
200이면 정상. 헬스체크는 `/api/health`이다(`/healthz`는 Cloud Run 예약).

## 주의

- 트리거가 삭제된 상태라 `master`에 푸시해도 배포되지 않는다. 트리거를 다시 만드는 순간부터 자동 배포가 시작된다.
- 업로드 문서와 대화 기록은 복구되지 않으므로, 재시작하면 문서를 다시 업로드해야 한다.
- Google OAuth 클라이언트(`GOOGLE_CLIENT_ID`)에 등록된 오리진/리디렉션은 서비스 URL이 같으면 수정하지 않아도 된다.
- 로컬 개발은 `USE_LOCAL_STORAGE=True`로 GCS 없이 실행할 수 있다(`technote-dev-stack` 스킬 참고).
