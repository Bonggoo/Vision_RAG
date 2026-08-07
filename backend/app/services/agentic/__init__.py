"""Agentic Search 파이프라인 패키지.

기존 단일 파일 `agentic_graph.py`(1,282줄)를 역할별로 분해한 것입니다.

  sse.py            SSE 이벤트 직렬화
  classification.py 규칙 기반 질문 분류 (LLM 호출 전 선별)
  toc.py            목차 페이지 정규화 · 섹션 범위 계산
  doc_filter.py     질문 키워드 기반 1차 문서 후보 필터 (순수 함수)
  llm_steps.py      단계별 LLM 호출 (문서 선택 · 페이지 선택 · 정밀 탐색 · 폴백)
  context.py        파이프라인 실행 컨텍스트 (SSE 수집 · 대화 저장)
  pipeline.py       stage 조립 및 오케스트레이션

외부에서는 `run_agentic_pipeline` 만 쓰면 됩니다.
"""
from .pipeline import run_agentic_pipeline

__all__ = ["run_agentic_pipeline"]
