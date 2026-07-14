"use client";

import React, { useEffect, useRef } from "react";
import { useUIStore } from "@/store/useUIStore";

export default function ConfirmDialog() {
  const confirmState = useUIStore((s) => s.confirmState);
  const resolveConfirm = useUIStore((s) => s.resolveConfirm);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  const options = confirmState?.options;

  // 키보드 지원: Esc = 취소, Enter = 확인. 열릴 때 확인 버튼에 포커스.
  useEffect(() => {
    if (!confirmState) return;
    confirmBtnRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        resolveConfirm(false);
      } else if (e.key === "Enter") {
        e.preventDefault();
        resolveConfirm(true);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [confirmState, resolveConfirm]);

  if (!confirmState || !options) return null;

  const {
    title,
    description,
    confirmText = "확인",
    cancelText = "취소",
    danger = false,
    icon,
  } = options;

  return (
    <div
      className="fixed inset-0 z-[110] flex items-center justify-center p-4 animate-fade"
      role="dialog"
      aria-modal="true"
      aria-label={title}
    >
      {/* 백드롭 (클릭 시 취소) */}
      <div
        className="absolute inset-0 bg-black/45 backdrop-blur-sm"
        onClick={() => resolveConfirm(false)}
      />

      {/* 다이얼로그 카드 */}
      <div className="relative z-10 w-full max-w-sm rounded-3xl border border-border/50 bg-card/95 backdrop-blur-2xl shadow-2xl p-6 animate-slide-up">
        <div className="flex flex-col gap-2 text-center">
          {icon && <div className="text-3xl mx-auto mb-1">{icon}</div>}
          <h3 className="text-[16px] font-bold text-foreground font-display leading-snug">{title}</h3>
          {description && (
            <p className="text-[13px] text-muted-foreground/90 leading-relaxed whitespace-pre-line">
              {description}
            </p>
          )}
        </div>

        <div className="flex gap-2.5 mt-6">
          <button
            onClick={() => resolveConfirm(false)}
            className="btn-secondary flex-1 py-2.5 px-4 rounded-full text-[13px] font-semibold text-muted-foreground hover:text-foreground transition-all"
          >
            {cancelText}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={() => resolveConfirm(true)}
            className={`flex-1 py-2.5 px-4 rounded-full text-[13px] font-bold text-white transition-all shadow-md focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-offset-card ${
              danger
                ? "bg-destructive hover:opacity-90 shadow-destructive/20 focus:ring-destructive/50"
                : "btn-primary focus:ring-primary/50"
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
