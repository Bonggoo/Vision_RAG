# 질문 품질 자동 평가 (Evals)

골든 데이터셋(`dataset.yaml`)의 질문을 파이프라인에 흘려보내고 SSE 이벤트를
파싱해 자동 채점하는 루틴입니다. **되묻기(문서 후보 제시) → 문서 선택 →
최종 답변**까지의 멀티턴 플로우도 자동으로 검증합니다.

실행 대상은 두 가지:

| 모드 | 설명 |
|---|---|
| **remote** (기본) | Cloud Run 배포 서버에 HTTP로 `POST /chat/stream` — 실제 서비스 그대로 테스트 |
| **local** (`--local`) | `run_agentic_pipeline`을 프로세스 내 직접 호출 — 서버·배포 없이 코드 검증 |

## 실행

```bash
cd backend
source venv/bin/activate
python -m evals.run_eval                  # 원격 (dataset defaults.base_url = Cloud Run)
python -m evals.run_eval --local          # 로컬 파이프라인 직접 호출
python -m evals.run_eval --only greeting  # id 부분 일치 필터
python -m evals.run_eval --judge          # LLM-as-judge 채점 포함
python -m evals.run_eval --min-pass 0.8   # CI/루틴용: 통과율 미달 시 exit 1
```

결과는 콘솔 요약 + `evals/results/<타임스탬프>.json`으로 저장됩니다 (git 제외).

## 원격 인증 설정 (최초 1회)

`/chat/stream`은 JWT가 필요합니다. 러너는 아래 우선순위로 토큰을 마련합니다:

1. `--token <JWT>` 또는 `EVAL_ACCESS_TOKEN` — 배포 프론트에 로그인 후 개발자도구에서 복사한 access token (30분 만료라 임시용)
2. `EVAL_JWT_SECRET` — **권장**. 프로덕션 JWT_SECRET을 알려주면 러너가 토큰을 자체 발급 (환경변수 또는 `evals/.env`)
3. 위 둘 다 없으면 로컬 기본 `settings.JWT_SECRET`으로 발급 시도 (프로덕션 시크릿과 다르면 401)

> ⚠️ `EVAL_JWT_SECRET`은 **`evals/.env`**(git 제외)에 넣으세요, `backend/.env`가 아닙니다.
> `app/config.py`의 pydantic Settings는 `backend/.env`의 모든 키를 엄격 검증해서,
> 선언되지 않은 키가 섞이면 앱 부팅 자체가 `extra_forbidden` 에러로 실패합니다.

프로덕션 시크릿 확인 후 `evals/.env`에 추가:

```bash
gcloud run services describe vision-rag-backend \
  --region <리전> --format='value(spec.template.spec.containers[0].env)' | tr ';' '\n' | grep JWT_SECRET
# backend/evals/.env 파일 생성/수정:
# EVAL_JWT_SECRET=<위에서 확인한 값>
```

## 채점 축

expected에 **명시한 항목만** 검사하며, 모두 통과해야 케이스 PASS입니다:

| 검사 | 판정 기준 |
|---|---|
| `routing` | 최종 분기가 기대와 일치 (technical / general / clarification) |
| `clarification` | (`expect_clarification` 명시 시) 1턴에 되묻기 발생 + 후보 리스트에 기대 문서 포함 |
| `document` | reference 이벤트의 문서명에 기대 문자열 포함 |
| `pages` | 참조 페이지가 기대 페이지 ±`page_tolerance` 이내 |
| `keywords` | 답변의 키워드 포함률 ≥ `min_keyword_recall` |
| `judge` (옵션) | 기준 답변 대비 Gemini 채점 ≥ `min_judge_score` (1~5점) |

## 되묻기 → 문서 선택 플로우

1턴 응답이 clarification(문서 후보 리스트)이고 기대 최종 결과가 답변이면,
러너가 프론트엔드의 사용자 선택을 재현합니다:

1. 후보 중 `select_document`(없으면 `expected.document`)와 부분 일치하는 문서 선택
2. `document_id`를 지정하고 1턴 대화를 `chat_history`로 붙여 재질문
3. 2턴의 최종 답변을 채점

`expected.type: clarification`인 케이스는 되묻기에서 멈추는 게 정답이므로 자동 선택하지 않습니다.
케이스 작성 예시는 `dataset.yaml`의 주석 템플릿 참고.

## 정기 루틴으로 돌리기 (Claude Desktop 등)

CLI 하나로 완결되고 exit code를 반환하므로 그대로 자동화에 쓸 수 있습니다:

```bash
cd ~/Workspace/Vision_RAG/backend && venv/bin/python -m evals.run_eval --judge --min-pass 0.8
```

- Claude Desktop 예약 작업(루틴)에 "위 명령을 실행하고 FAIL 케이스를 요약해줘"로 등록
- 전제: `EVAL_JWT_SECRET`이 `evals/.env`에 있어야 무인 실행 가능
- 배포 파이프라인(Cloud Build 등)에서 `--min-pass`로 게이트로도 사용 가능
