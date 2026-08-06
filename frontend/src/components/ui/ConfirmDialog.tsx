"use client";

import React, { useEffect, useRef } from "react";
import { useUIStore } from "@/store/useUIStore";

export default function ConfirmDialog() {
  const confirmState = useUIStore((s) => s.confirmState);
  const resolveConfirm = useUIStore((s) => s.resolveConfirm);
  const confirmBtnRef = useRef<HTMLButtonElement>(null);

  const options = confirmState?.options;

  // 키보드 지원: Esc = 취소. 열릴 때 확인 버튼에 포커스.
  // Enter는 전역 처리하지 않음 — 취소 버튼에 포커스가 있어도 확인이 실행되는 사고 방지.
  // (포커스된 버튼의 네이티브 Enter 동작(click)에 맡긴다)
  useEffect(() => {
    if (!confirmState) return;
    confirmBtnRef.current?.focus();

    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault();
        resolveConfirm(false);
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
      <div className="overlay-scrim absolute inset-0" onClick={() => resolveConfirm(false)} />

      {/* 다이얼로그 카드 */}
      <div
        className="relative z-10 w-full max-w-sm rounded-xl border border-border bg-popover p-5 animate-slide-up"
        style={{ boxShadow: "var(--shadow-lg)" }}
      >
        <div className="flex flex-col gap-1.5">
          {icon && <span className="text-2xl mb-0.5">{icon}</span>}
          <h3 className="text-[15.5px] font-medium text-foreground leading-snug">{title}</h3>
          {description && (
            <p className="text-[13px] text-muted-foreground leading-relaxed whitespace-pre-line">
              {description}
            </p>
          )}
        </div>

        <div className="flex justify-end gap-2 mt-5">
          <button
            onClick={() => resolveConfirm(false)}
            className="btn-secondary py-2 px-4 rounded-lg text-[13px]"
          >
            {cancelText}
          </button>
          <button
            ref={confirmBtnRef}
            onClick={() => resolveConfirm(true)}
            className={`py-2 px-4 rounded-lg text-[13px] font-medium transition-colors ${
              danger
                ? "bg-destructive text-[var(--destructive-foreground)] hover:brightness-95"
                : "btn-primary"
            }`}
          >
            {confirmText}
          </button>
        </div>
      </div>
    </div>
  );
}
