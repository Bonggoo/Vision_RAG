"use client";

import React from "react";
import { ArrowRight } from "lucide-react";
import type { ClarificationState } from "@/types/chat";

interface ClarificationCardProps {
  state: ClarificationState;
  onSelectQuestion: (question: string) => void;
  onSelectDocument: (documentId: string) => void;
}

/** 질문이 모호할 때 AI가 되묻는 카드 — 추천 질문 + 문서 후보 선택 */
export default function ClarificationCard({
  state,
  onSelectQuestion,
  onSelectDocument,
}: ClarificationCardProps) {
  const questions = state.suggested_questions ?? [];
  const hasQuestions = questions.length > 0;
  const hasCandidates = state.candidates.length > 0;
  // 일치하는 문서를 못 찾은 경우 — 후보 퍼센트는 전부 바닥값이라 정보가 없고,
  // 훑어보면 '그래도 관련 있음'으로 오독되므로 숨기고 문서 목록만 남긴다.
  const isNoMatch = state.mode === "no_match";
  const listLabel = isNoMatch ? "보유 문서 중에서 선택" : hasQuestions ? "직접 문서 선택" : null;

  return (
    <section
      aria-label="추가 정보 요청"
      className="surface-panel p-4 md:p-5 space-y-4 animate-in"
    >
      <p className="text-[14px] text-foreground leading-relaxed">{state.content}</p>

      {hasQuestions && (
        <div className="space-y-1.5">
          <p className="text-[12px] text-muted-foreground">추천 질문</p>
          {questions.map((q, idx) => (
            <button
              key={idx}
              onClick={() => onSelectQuestion(q)}
              className="w-full flex items-center justify-between gap-3 text-left px-3.5 py-2.5 rounded-lg
                border border-border hover:border-border-strong hover:bg-accent transition-colors group"
            >
              <span className="text-[13.5px]">{q}</span>
              <ArrowRight className="w-3.5 h-3.5 text-muted-foreground/50 group-hover:text-foreground transition-colors shrink-0" />
            </button>
          ))}
        </div>
      )}

      {hasCandidates && (
        <div className="space-y-1.5">
          {listLabel && <p className="text-[12px] text-muted-foreground">{listLabel}</p>}
          {state.candidates.map((cand) => (
            <button
              key={cand.document_id}
              onClick={() => onSelectDocument(cand.document_id)}
              className="w-full flex items-center justify-between gap-3 text-left px-3.5 py-3 rounded-lg
                border border-border hover:border-border-strong hover:bg-accent transition-colors"
            >
              <span className="flex-1 min-w-0">
                <span className="block text-[13.5px] font-medium truncate">
                  {cand.manufacturer} {cand.model_series}
                </span>
                <span className="block text-[12px] text-muted-foreground truncate mt-0.5">
                  {cand.title}
                </span>
              </span>
              {/* 관련도 0(후보 보충용으로 채워진 문서)도 '0%'로 보이면 오해를 부르므로 숨긴다 */}
              {!isNoMatch && cand.confidence > 0 && (
                <span className="text-[11px] font-mono-util text-muted-foreground shrink-0">
                  {(cand.confidence * 100).toFixed(0)}%
                </span>
              )}
            </button>
          ))}
        </div>
      )}
    </section>
  );
}
