"use client";

import React, { useEffect, useState } from "react";
import { CheckCircle2, XCircle, Info, AlertTriangle, X } from "lucide-react";
import { useUIStore, type Toast, type ToastType } from "@/store/useUIStore";

const TOAST_STYLE: Record<
  ToastType,
  { icon: React.ElementType; accent: string; iconColor: string }
> = {
  success: { icon: CheckCircle2, accent: "before:bg-emerald-500", iconColor: "text-emerald-500" },
  error: { icon: XCircle, accent: "before:bg-destructive", iconColor: "text-destructive" },
  info: { icon: Info, accent: "before:bg-primary", iconColor: "text-primary" },
  warning: { icon: AlertTriangle, accent: "before:bg-amber-500", iconColor: "text-amber-500" },
};

function ToastItem({ toast, onClose }: { toast: Toast; onClose: (id: string) => void }) {
  const [leaving, setLeaving] = useState(false);
  const { icon: Icon, accent, iconColor } = TOAST_STYLE[toast.type];

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
      className={`pointer-events-auto relative flex items-start gap-3 w-full overflow-hidden
        rounded-2xl border border-border/50 bg-popover/95 backdrop-blur-xl
        pl-4 pr-3 py-3 shadow-xl cursor-pointer
        before:absolute before:left-0 before:top-0 before:bottom-0 before:w-1 ${accent}
        transition-all duration-200 ${leaving ? "opacity-0 translate-y-[-8px] scale-[0.97]" : "animate-in"}`}
    >
      <Icon className={`w-5 h-5 shrink-0 mt-0.5 ${iconColor}`} />
      <div className="flex-1 min-w-0 pt-0.5">
        {toast.title && (
          <p className="text-[13px] font-bold text-foreground leading-snug mb-0.5">{toast.title}</p>
        )}
        <p className="text-[13px] text-foreground/85 leading-snug break-words whitespace-pre-line">
          {toast.message}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          dismiss();
        }}
        aria-label="알림 닫기"
        className="shrink-0 p-1 -mt-0.5 -mr-1 rounded-full text-muted-foreground/50 hover:text-foreground hover:bg-accent/50 transition-colors"
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
