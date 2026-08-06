"use client";

import React, { useState } from "react";
import { ChevronDown } from "lucide-react";

/** 접이식 추론 과정 블록 */
export default function ReasoningBlock({ steps }: { steps: string[] }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!steps || steps.length === 0) return null;

  return (
    <div className="mb-3">
      <button
        onClick={() => setIsOpen((v) => !v)}
        aria-expanded={isOpen}
        className="btn-ghost inline-flex items-center gap-1.5 px-2 py-1 -ml-2 rounded-md text-[12px]"
      >
        <ChevronDown
          className={`w-3.5 h-3.5 transition-transform ${isOpen ? "" : "-rotate-90"}`}
        />
        <span>추론 과정 {steps.length}단계</span>
      </button>

      {isOpen && (
        <ol className="mt-2 ml-1 pl-3.5 border-l border-border space-y-1.5 animate-in">
          {steps.map((step, i) => (
            <li key={i} className="text-[12.5px] text-muted-foreground leading-relaxed">
              {step}
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
