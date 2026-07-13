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
python -m evals.run_eval --generate 20    # 실제 매뉴얼에서 매번 다른 20문항 생성해 실행
python -m evals.run_eval --dataset evals/claude_dataset.yaml --equiv   # Claude 작성 500문항 (독립 출제)
```

> `claude_dataset.yaml`: 실제 매뉴얼 53종 ToC에서 균등 샘플링한 500문항을 **Claude가 작성**한
> 고정 세트. Gemini가 출제·응답을 모두 맡는 `--generate`의 자기일관성 편향이 없는 독립 벤치마크로,
> 전보식 ~30%가 섞여 있고 `--only cld-0`처럼 부분 실행이 가능합니다. `--equiv`(동등 문서 인정)와
> 함께 돌리는 것을 권장합니다.

결과는 콘솔 요약 + `evals/results/<타임스탬프>.json`으로 저장됩니다 (git 제외).

## 질문 자동 생성 (`--generate N`)

`dataset.yaml`의 손으로 쓴 케이스 대신, **실행할 때마다** 실제 보유 매뉴얼(원격은
`GET /documents`, `--local`은 GCS 메타데이터)에서 문서 N개를 고르게 뽑고 그
ToC 섹션 제목을 근거로 Gemini가 자연스러운 질문을 새로 합성합니다. 뽑힌
(문서, 페이지)가 곧 정답이 되어 `routing`/`document`/`pages`는 그대로
채점되지만, 미리 써둔 답이 없어 `keywords`/`judge`는 건너뜁니다.

```bash
python -m evals.run_eval --generate 20
```

**채점 신뢰도가 축마다 다릅니다:**
- `routing` — 신뢰도 높음 (거의 항상 20/20)
- `document` — 신뢰도 높음. **`--generate`에서는 문서 동등성 판정(아래)이 켜져
  중복/판본 문서나 모델 비종속 일반 질문으로 인한 '가짜 실패'를 자동으로 걸러내므로,
  남는 실패는 대개 진짜 라우팅 오류(다른 모델·다른 장비 선택)입니다.**
- `pages` — **참고용으로만 보세요.** ToC 항목 위치를 정답으로 쓰는 근사치라,
  특히 방대한 매뉴얼(수백~1000+ 페이지)에서 실제 관련 내용이 챕터 시작점보다
  한참 뒤에 있으면 오차가 커집니다. 문서 크기에 비례해 허용 오차를 넉넉히
  주지만(최소 8, 최대 40페이지) 그래도 노이즈가 있어 `--min-pass`로 강하게
  게이트하지 않는 걸 권장합니다.

### 문서 동등성 판정 (`--generate` 전용, 가짜 실패 필터)

생성 질문은 일부러 모델명을 생략해 만들기 때문에(현장 사용자 재현), 소스 문서
1개만 정답으로 채점하면 두 부류가 구조적으로 실패로 찍힙니다:

1. **중복/판본 문서** — 예: `MELSEC-Q 시리얼 통신 모듈`과 `시리얼 커뮤니케이션
   모듈(기본편)`은 사실상 같은 제품의 다른 판본. 둘 중 뭘 골라도 정답.
2. **모델 비종속 일반 질문** — 예: "RS-485 종단 저항 부착 방식?"은 RS-485를
   다루는 어떤 매뉴얼로도 답할 수 있음.

이를 걸러내기 위해, `document` precision(자동선택)이 소스와 어긋나면 Gemini Flash가
"선택된 문서로도 이 질문에 정확히 답할 수 있는가"를 판정해 **동등하면 통과로 인정**
합니다(detail에 `동등 문서 인정` 표기). 단 **질문 텍스트가 특정 모델번호를 명시하고
그 모델 고유 사양을 물으면 불인정**(예: 질문의 `F388A`를 `F381`로 답 → `실오답 확인`
표기 후 FAIL 유지)이라, 진짜 검색 오류 신호는 보존됩니다.

또한 `document` detail에는 **소스 문서가 되묻기 후보 메뉴에 떴는지(=검색 recall)**가
`되묻기 후보에 소스 포함/누락`으로 함께 표기됩니다 — precision(자동선택 정확도)과
recall(후보 노출 여부)을 분리해 진단할 수 있습니다.

무작위 샘플링이라 실행마다 다른 질문 조합이 나오고, 문서별로 균등 분산되도록
샘플링합니다(ToC가 방대한 문서 하나가 표본을 독식하지 않도록).

**문체 혼합:** 생성 문항의 30%는 **전보식(terse)** — 급한 현장 기술자가 검색창에
치듯 키워드만 나열한 입력(예: `"2051 서보 알람"`, `"L7NH 시리즈 제품 구성 확인"`) —
으로, 나머지 70%는 문장형으로 생성됩니다. 결과의 `style` 필드로 구분되며 리포트
말미에 문체별 통과율이 분리 집계됩니다. 키워드가 극도로 적은 실사용 입력에서도
라우팅/문서선택이 버티는지 매 실행마다 함께 측정하기 위함입니다.

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
| `document` | reference 이벤트의 문서명에 기대 문자열 포함 (`--generate`에선 동등 문서도 인정 — 위 참고) |
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
