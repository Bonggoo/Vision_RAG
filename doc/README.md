# 📖 TechNote (Vision RAG) 문서 인덱스

이 폴더의 문서를 성격별로 분류한 인덱스입니다. 처음이라면 **PRD → API_Contract → remaining_tasks** 순서를 권장합니다.

> **최종 정리**: 2026-07-18 — 중복되던 작업 추적 문서 3종(`task.md` 루트, `improvement_list.md`)을 `remaining_tasks.md`로 통합했습니다.

---

## 🧭 명세 / 계약 (Spec)
살아있는 참조 문서 — 코드와 함께 유지보수됩니다.

| 문서 | 내용 |
|------|------|
| [PRD.md](./PRD.md) | 제품 요구사항 정의서 (목표·사용자·범위) |
| [API_Contract.md](./API_Contract.md) | Backend(FastAPI) ↔ Frontend(Next.js) 통신 규약 |
| [질문.md](./질문.md) | 대화 품질 평가용 골든 질문셋 (`backend/evals`에서 사용) |

## 📋 현황 / 계획 (Status & Planning)
지금 무엇이 되어 있고 다음에 무엇을 할지 — **여기서 시작하세요.**

| 문서 | 내용 |
|------|------|
| [remaining_tasks.md](./remaining_tasks.md) | **마스터 보드** — 잔여 작업 + 완료 현황(카테고리별) + 향후 로드맵 |
| [audit_findings_2026-07.md](./audit_findings_2026-07.md) | 전체 코드 감사(UI/UX·보안·백엔드) 결과 — 처리 완료분 + 잔여 항목 |
| [security_roadmap.md](./security_roadmap.md) | 중장기 보안 개선 로드맵 (쿠키화·Secret Manager·컨테이너 격리) |

## 📐 설계 결정 (ADR)
| 문서 | 내용 |
|------|------|
| [near_duplicate_document_handling.md](./near_duplicate_document_handling.md) | 유사(중복) 문서 처리 설계 — L1 채택 |

## 📦 구현 완료 보고서 (Implementation History)
이미 반영된 기능의 상세 아키텍처·결정 기록. 이력 보존용이며 신규 작업 시 배경 참고.

| 문서 | 내용 |
|------|------|
| [refactoring_plan.md](./refactoring_plan.md) | 코드 구조 리팩토링 로드맵 (전 Phase 완료) |
| [async_upload_roadmap.md](./async_upload_roadmap.md) | 대용량 비동기 GCS 다이렉트 업로드 파이프라인 (완료) |
| [gcs_signed_url_roadmap.md](./gcs_signed_url_roadmap.md) | GCS Signed URL 다운로드 + 한글 파일명 핫픽스 (완료) |

## 🛠️ 운영 / 인프라 가이드
| 문서 | 내용 |
|------|------|
| [custom_domain_mapping.md](./custom_domain_mapping.md) | Cloud Run + Vercel 커스텀 도메인 연결 가이드 |

## 📣 기타
| 문서 | 내용 |
|------|------|
| [content_plan.md](./content_plan.md) | 데모 영상·기술 블로그 콘텐츠 플랜 (포트폴리오) |
