# 컨텍스트 관리 벤치마킹 (Anthropic / OpenAI / Google)

작성일: 2026-08-07 · 대상: Vision_RAG (TechNote)

> ⚠️ **이 문서는 사전 조사 자료이며, 진단부(1장)의 상당 부분이 실측으로 반증되었습니다.**
> 코드 감사와 토큰 실측 결과 및 실제 적용 내역은
> [context-management-results.md](context-management-results.md) 를 보세요.
>
> 특히 주의할 점:
> - 이 문서가 참조하는 `agentic_graph.py` 는 **삭제된 파일**입니다(커밋 `f3c1784` 에서
>   `services/agentic/` 패키지로 분해). 1장의 모든 줄번호는 유효하지 않습니다.
> - 최우선으로 제시한 "암묵적 캐싱 미사용"(1장 8번 / 2장 A)은 **사실이 아니었습니다.**
>   측정해 보니 페이지 선택 단계에서 이미 89% 적중 중이었습니다.
> - 실제 병목은 이 문서가 언급하지 않은 **Phase 2 정밀탐색**(38,963토큰 / 적중 0%)이었습니다.
>
> 아래 본문은 기록 보존을 위해 원문 그대로 두었습니다.

---

## 1. 현재 상태 진단

| # | 위치 | 현상 | 문제 |
|---|---|---|---|
| 1 | `agentic_graph.py:281`, `:1249`, `agent_service.py:305` | `chat_history[-4:]` / `[-6:]` + `content[:200~300]` 하드컷이 **3곳에 중복 구현** | 로직 분산, 정책 변경 시 누락 위험 |
| 2 | 동일 | 문자 수 기준 절단 (토큰 아님) | 한글/영문 토큰 비율 차이로 예산 예측 불가, 문장 중간 절단 |
| 3 | 동일 | 오래된 턴은 **완전 폐기** (요약 없음) | 5턴째부터 "아까 그 MR-J5 알람" 같은 지시대명사 해석 실패 |
| 4 | `useChatStream.ts:96` | 프론트가 **전체 히스토리**를 매 턴 전송 → 백엔드는 4턴만 사용 | 불필요한 페이로드, 서버 저장본과 이중 진실원(source of truth) |
| 5 | `prompts.py:135` `text_fallback_prompt` | `context_section` + `question`이 **본문 텍스트보다 앞** | 프리픽스가 매 턴 달라져 Gemini 암묵적 캐시 히트 불가 |
| 6 | `agent_service.py:299` `_do_vision_analysis` | 질문/히스토리가 프롬프트에 먼저, PDF는 별도 파트 | 동일 페이지 후속 질문에서도 캐시 미스 |
| 7 | `agentic_graph.py:1242` | `full_text[:8000]` 고정 절단 | 페이지 수 무관 일괄 컷, 뒷부분 정보 손실 |
| 8 | 전역 | Gemini **명시적/암묵적 캐싱 미사용**, `usage.total_cached_tokens` 미계측 | 비용 최적화 여지 측정 불가 |

**잘 하고 있는 부분:** ToC 전체를 Phase 1에 넣지 않고 키워드 매칭 근거만 전달(`:261`), `previous_reference` / `previous_pages_section`으로 턴 간 연속성 유지, 문서 1개면 LLM 호출 스킵. 이건 Anthropic이 말하는 "just-in-time context"와 동일한 철학이라 방향은 맞다.

---

## 2. 벤치마킹 대상

### A. Gemini 암묵적 캐싱 — 프롬프트 프리픽스 정렬 ⭐ 최우선
> Gemini 2.5+ 전 모델 기본 활성. **공통 프리픽스 일치 시 캐시된 토큰 75~90% 할인.** 최소 토큰: Gemini 3.5 Flash 4096 / 2.5 Flash 2048. 권고: "크고 공통된 콘텐츠를 프롬프트 앞쪽에 배치".

**적용:**
1. 모든 프롬프트를 `[고정 시스템 지시] → [대용량 공통 콘텐츠: ToC / PDF / 본문] → [가변: 히스토리·이전참조] → [질문]` 순서로 재배열.
   - `text_fallback_prompt`: `context_section`/`question`을 **본문 뒤로** 이동 (현재 앞).
   - `_do_vision_analysis`: PDF 파트를 messages 배열 **첫 번째**로, 질문을 마지막으로.
   - `select_pages_prompt`: 이미 ToC가 앞 → ✅ 유지. 단 `previous_pages_section`이 질문 바로 앞이라 문제 없음.
2. `usage_metadata.cached_content_token_count`를 로깅에 추가해 히트율 계측.
3. 같은 문서로 연속 질문하는 세션이 우리 UX의 기본값이므로 히트율이 높게 나올 구조다.

**예상 효과:** ToC가 큰 매뉴얼(수백 페이지)에서 Phase 2 입력 토큰 비용 최대 90%↓. **난이도: 낮음 (프롬프트 순서 변경뿐).**

### B. Anthropic Compaction + 구조화된 노트(structured note-taking) ⭐
> 컨텍스트 한계 도달 시 오래된 히스토리를 **결정·미해결 문제·핵심 상태를 보존한 요약으로 치환**. Anthropic 내부 평가: context editing 단독 +29%, memory tool 결합 시 **+39%**.

**적용 — 세션 상태 요약 필드:**
```json
// conversations/{email}/{session_id}.json 에 추가
"context_summary": {
  "equipment": "MITSUBISHI MR-J5",
  "alarm_codes": ["AL.32", "AL.50"],
  "referenced_docs": [{"document_id": "...", "pages": [412, 413]}],
  "open_issues": ["과부하 원인 미확정"],
  "updated_at_turn": 12
}
```
- 턴 수가 임계치(예: 6턴)를 넘으면 Flash-Lite로 요약을 갱신(백그라운드 `task_queue.py` 활용).
- 프롬프트에는 `context_summary` + **최근 2턴 원문**만 투입 → 현재 4턴 슬라이스보다 토큰은 줄고 기억은 늘어남.
- 지시대명사("그거", "아까 그 알람") 해석 실패가 이 프로젝트의 가장 체감 큰 품질 이슈인데 여기서 직결로 해결된다.

**난이도: 중간.** `conversation_service.py` 스키마 + 요약 노드 1개 추가.

### C. OpenAI 서버사이드 컨텍스트 관리 (`context_management` / `previous_response_id`)
> 2026-02 Responses API에 서버 사이드 compaction 도입. `compact_threshold` 초과 시 서버가 컨텍스트를 압축하고 스트림에 compaction 아이템을 방출. 클라이언트는 `previous_response_id`만 넘기고 **새 사용자 메시지만 전송**.

**적용:** 프론트가 히스토리를 통째로 보내는 구조(#4)를 폐기 → 요청 바디는 `session_id` + `question`만. 백엔드가 `conversation_service`에서 히스토리를 로드하고 B의 요약 정책을 서버에서 단독 결정.

**부수 효과:** 페이로드 감소, 새로고침/멀티탭에서 히스토리 불일치 제거, 컨텍스트 정책이 서버 한 곳으로 통합(#1 중복 해소). **난이도: 중간 (프론트-백 계약 변경, `chat_history`는 deprecated 유지로 호환).**

### D. Anthropic Contextual Retrieval — 청크 문맥 프리펜딩
> 임베딩/BM25 인덱싱 **전에** 각 청크 앞에 설명 문맥(50~100토큰)을 붙임. 검색 실패율 **-49%**, 리랭킹 결합 시 -67%.

**적용 (벡터 DB 없이도 원리 이식 가능):**
1. **Phase 2 키워드 매칭**: 페이지 텍스트에 ToC 브레드크럼(`3장 트러블슈팅 > 3.2 알람 목록 > AL.32`)을 프리펜딩한 뒤 매칭 → 페이지 본문에 없는 상위 문맥 용어로도 히트.
2. **Phase 3 Vision**: 미니 PDF와 함께 `"이 페이지는 [문서명] > [챕터] > [섹션], 원문 p.412"` 텍스트 파트를 동봉. 모델이 페이지 번호/섹션을 근거로 인용할 수 있어 환각 감소 + 출처 표기 정확도↑.
3. 브레드크럼은 이미 `metadata.toc`에 있으므로 **추가 LLM 호출 0회**.

**난이도: 낮음~중간.** 비용 대비 효과가 가장 좋은 항목.

### E. Anthropic "Just-in-Time Context" + 툴 결과 정리(tool result clearing)
> 사전에 전부 로드하지 말고 에이전트가 필요할 때 가져오게 하고, 오래된 툴 결과는 컨텍스트에서 제거.

**적용:** 현재는 고정 3-phase 파이프라인. 중장기적으로 `read_page(n)`, `search_text(q)`, `read_toc()`를 **함수 호출 툴**로 노출해 모델이 필요한 만큼 반복 탐색하게 전환 가능. 다만 지금 구조가 지연/비용 예측이 쉽다는 장점이 있어 **전면 전환은 비권장** — Phase 2에서 페이지 확정 실패 시에만 툴 루프로 폴백하는 하이브리드가 현실적이다.

### F. Gemini File API + 명시적 캐싱 (`generateContent` 경로)
> 명시적 캐시는 참조 입력 토큰 90% 할인 보장(2.5+). 단 **Interactions API는 암묵적 캐싱만 지원**, 명시적 캐시는 `generateContent` API 사용 필요. 저장 비용(TTL 기준) 발생.

**적용:** 업로드 직후 ToC 추출 시 대형 PDF를 File API로 올리고 캐시 생성 → 메타데이터 추출·ToC 추출·재추출이 같은 캐시 참조. 다만 우리 조회 패턴은 "가끔 한 번"이라 TTL 저장비가 이득을 잡아먹을 수 있음. **A(암묵적)를 먼저 하고, 계측된 히트율을 보고 판단.**

### G. 토큰 기반 예산 관리
> `count_tokens` / `usage.total_cached_tokens` 기반 관리가 표준. 문자 수 컷은 안티패턴.

**적용:** `build_context_section(history, budget_tokens=...)` 유틸 하나로 #1·#2·#7 동시 해결. `full_text[:8000]`도 페이지 수 비례 토큰 예산으로 대체.

---

## 3. 우선순위 로드맵

| 순위 | 항목 | 효과 | 난이도 | 대상 파일 |
|---|---|---|---|---|
| 1 | **A. 프롬프트 프리픽스 정렬 + 캐시 히트율 계측** | 비용 ↓↓ | 낮음 | `prompts.py`, `agent_service.py` |
| 2 | **D. ToC 브레드크럼 프리펜딩** | 검색 정확도 ↑↑ | 낮음 | `agentic/toc.py`, `agentic_graph.py` |
| 3 | **G. 컨텍스트 빌더 단일화 (토큰 예산)** | 유지보수 ↑ | 낮음 | 신규 `services/agentic/context.py` |
| 4 | **B. 세션 요약(compaction)** | 멀티턴 품질 ↑↑ | 중간 | `conversation_service.py`, `agentic_graph.py` |
| 5 | **C. 서버사이드 히스토리 소유** | 일관성 ↑ | 중간 | `routers/chat.py`, `useChatStream.ts` |
| 6 | F / E | 조건부 | 높음 | — |

**검증:** 1~5 각 단계마다 `backend/evals/run_eval.py --judge`를 before/after로 돌려 routing/document/page 정확도와 토큰 사용량을 함께 기록. 특히 4번은 **멀티턴 골든 케이스**(지시대명사 후속 질문)를 eval 데이터셋에 추가해야 효과가 드러난다.

---

## 참고 문헌

- [Effective context engineering for AI agents — Anthropic](https://www.anthropic.com/engineering/effective-context-engineering-for-ai-agents)
- [Context engineering: memory, compaction, and tool clearing — Claude Cookbook](https://platform.claude.com/cookbook/tool-use-context-engineering-context-engineering-tools)
- [Contextual Retrieval in AI Systems — Anthropic](https://www.anthropic.com/engineering/contextual-retrieval)
- [Compaction — OpenAI API](https://developers.openai.com/api/docs/guides/compaction)
- [Conversation state — OpenAI API](https://developers.openai.com/api/docs/guides/conversation-state)
- [Context caching — Gemini API](https://ai.google.dev/gemini-api/docs/caching)
- [Gemini 2.5 models now support implicit caching — Google Developers Blog](https://developers.googleblog.com/gemini-2-5-models-now-support-implicit-caching/)
