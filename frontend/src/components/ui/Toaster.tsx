"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { useUIStore, type Toast, type ToastType } from "@/store/useUIStore";

const TOAST_STYLE: Record<ToastType, { icon: React.ElementType; iconColor: string }> = {
  success: { icon: CheckCircle2, iconColor: "text-[var(--success)]" },
  error: { icon: XCircle, iconColor: "text-destructive" },
  info: { icon: Info, iconColor: "text-muted-foreground" },
  warning: { icon: AlertTriangle, iconColor: "text-[var(--warning)]" },
};

function ToastItem({ toast, onClose }: { toast: Toast; onClose: (id: string) => void }) {
  const [leaving, setLeaving] = useState(false);
  const { icon: Icon, iconColor } = TOAST_STYLE[toast.type];

  // 부드러운 퇴장을 위해 실제 제거 전에 leaving 상태로 전환
  const dismiss = () => {
    setLeaving(true);
    setTimeout(() => onClose(toast.id), 200);
  };

  useEffect(() => {
    if (toast.duration <= 0) return;
    const timer = setTimeout(dismiss, toast.duration);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [toast.id, toast.duration]);

  return (
    <div
      role="status"
      aria-live="polite"
      onClick={dismiss}
      className={`pointer-events-auto flex items-start gap-2.5 w-full
        rounded-lg border border-border bg-popover
        px-3.5 py-3 cursor-pointer
        transition-all duration-200 ${leaving ? "opacity-0 -translate-y-1" : "animate-in"}`}
      style={{ boxShadow: "var(--shadow-lg)" }}
    >
      <Icon className={`w-4 h-4 shrink-0 mt-0.5 ${iconColor}`} aria-hidden="true" />
      <div className="flex-1 min-w-0">
        {toast.title && (
          <p className="text-[13px] font-medium text-foreground leading-snug mb-0.5">{toast.title}</p>
        )}
        <p className="text-[13px] text-muted-foreground leading-snug break-words whitespace-pre-line">
          {toast.message}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          dismiss();
        }}
        aria-label="알림 닫기"
        className="btn-ghost shrink-0 p-1 -mt-0.5 -mr-1 rounded-md"
      >
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

export default function Toaster() {
  const toasts = useUIStore((s) => s.toasts);
  const removeToast = useUIStore((s) => s.removeToast);

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed left-1/2 -translate-x-1/2 z-[100] flex flex-col gap-2 w-[92vw] max-w-sm pointer-events-none"
      style={{ top: "calc(env(safe-area-inset-top, 0px) + 12px)" }}
    >
      {toasts.map((toast) => (
        <ToastItem key={toast.id} toast={toast} onClose={removeToast} />
      ))}
    </div>
  );
}
