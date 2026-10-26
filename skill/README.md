# Manual Navigator

설비 PDF 매뉴얼(서보, PLC, 인버터, 모션컨트롤러 등)에 대한 질문을 AI 에이전트가 기술자처럼
답하게 하는 Agent Skill입니다. 목차를 보고, 알람 코드를 검색해 해당 페이지로 가서, 그 페이지만
직접 읽고, 원문 페이지를 인용해 답합니다. 벡터 DB도, 서버도, API 키도 필요 없습니다.

- **판단 규칙**: 알람이 상위·하위 장비(위치결정모듈, 모션컨트롤러, 엔코더) 쪽에서 나왔을 가능성을
  따지고, 모델이 불분명하면 되묻고, 폴더에 없는 브랜드는 없다고 말하고, 읽은 페이지 밖의 내용은
  지어내지 않습니다.
- **목차 없는 PDF**: 스캔본이나 북마크 없는 매뉴얼은 에이전트가 인쇄된 목차를 읽어 목차를 만들고,
  사용자가 동의하면 PDF에 북마크로 저장합니다. 원본 내용은 그대로이고 `--undo`로 바이트 단위까지
  되돌릴 수 있습니다. 저장된 목차는 어떤 PDF 뷰어에서도 보입니다.

## 구성

```
manual-navigator/          ← 스킬 본체 (이 폴더를 설치)
├── SKILL.md               작업 순서와 판단 규칙
├── references/build-toc.md  목차 없는 매뉴얼 처리 절차 (필요할 때만 읽힘)
├── scripts/manual.py      toc / find 명령 (pypdf만 사용)
└── evals/                 평가 문항 10개 + 가상 샘플 매뉴얼 생성기
tests/                     manual.py 단위 테스트
```

## 설치

1. Python 3.9 이상에서 `pip install pypdf`
2. `manual-navigator/` 폴더를 에이전트의 스킬 폴더에 복사합니다.
   - Claude Code: 개인용 `~/.claude/skills/manual-navigator/`, 프로젝트용 `<프로젝트>/.claude/skills/manual-navigator/`
   - Agent Skills 표준(SKILL.md)을 지원하는 다른 도구: 각 도구 문서의 스킬 폴더 위치에 복사
3. 배포할 때 `evals/`는 빼도 됩니다. 스킬 동작에는 필요 없습니다.

에이전트가 PDF 페이지(또는 페이지 이미지)를 직접 볼 수 있어야 합니다. Claude Code에서 검증했고,
다른 도구는 아직 검증하지 않았습니다.

## 사용

매뉴얼이 있는 폴더에서 평소처럼 물어보면 됩니다.

> AS200 서보에 AL.21 알람이 떴는데 원인이 뭐야? 매뉴얼은 manuals 폴더에 있어.

스크립트를 직접 쓸 수도 있습니다. 페이지 번호는 항상 PDF 물리 페이지(1부터)입니다.

```bash
python scripts/manual.py toc manuals/                    # 매뉴얼 목록: 페이지 수, 목차 상태, 제목
python scripts/manual.py toc manuals/X.pdf --depth 2     # 목차 (인쇄 페이지 번호가 다르면 괄호로 표시)
python scripts/manual.py find "AL.21" manuals/           # 코드 검색: 페이지, 목차 경로, 앞뒤 문맥
python scripts/manual.py toc manuals/X.pdf --write < toc.txt   # 목차를 북마크로 저장 (한 줄에 "레벨 | 페이지 | 제목")
python scripts/manual.py toc manuals/X.pdf --undo        # 저장한 목차 제거, 원본 파일로 복구
```

`find`는 코드 표기 차이를 흡수합니다. `AL.21`로 찾으면 `AL21`, `AL-21`, 하위 코드 `AL.21.1`은 찾고
`AL.210`은 찾지 않습니다. 한국어 검색어의 조사는 떼고 찾습니다.

## 제한

- 스캔본(텍스트 층이 없는 PDF)은 `find`로 검색할 수 없습니다. 목차와 페이지 보기로 찾습니다.
- 검색은 매번 PDF 텍스트를 새로 읽습니다. 샘플 572페이지 전체 검색에 약 7초가 걸렸습니다.
  매뉴얼이 수백 권이면 파일명으로 후보를 좁힌 뒤 검색하세요.
- 암호가 걸렸거나 전자서명된 PDF, 읽기 전용 파일에는 북마크를 쓰지 않고, 옆에 `<이름>.toc.txt`로 저장합니다.
- 스크립트는 네트워크에 접속하지 않습니다. 다만 에이전트가 읽은 페이지 내용은 그 에이전트의
  AI 모델 제공자에게 전송됩니다.

## 테스트

```bash
pip install pypdf reportlab pillow pytest
pytest tests                                              # 단위 테스트
python manual-navigator/evals/make_samples.py /tmp/manuals --truth /tmp/truth.json   # 가상 샘플 매뉴얼 6권
```

샘플 매뉴얼은 모두 가상 브랜드(Acme, Globex, Initech)입니다. 한글 글꼴이 필요하며 자동으로 찾지
못하면 `MANUAL_SAMPLE_FONT`에 .ttf/.ttc 경로를 지정하세요. 스캔본 생성에는 poppler의 `pdftoppm`이
필요합니다.

`evals/`의 각 문항 폴더는 `claude plugin eval` 형식입니다. Claude Code가 있으면
`manual-navigator/` 폴더에서 `claude plugin eval . --allow-tools Write,Edit,Bash --scaffold`로
스킬 사용·미사용 비교를 직접 돌릴 수 있습니다(실제 과금되는 실행입니다).
