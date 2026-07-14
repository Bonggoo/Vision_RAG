import { create } from "zustand";

/**
 * 전역 UI 스토어 — 토스트 알림 & 확인 다이얼로그.
 *
 * 네이티브 alert()/confirm() 을 대체합니다. React 컴포넌트 밖(스토어/유틸)에서도
 * `toast.*` / `confirmDialog()` 헬퍼로 호출할 수 있도록 getState() 기반으로 노출합니다.
 */

export type ToastType = "success" | "error" | "info" | "warning";

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
  /** 선택적 굵은 제목 (없으면 message 만 표시) */
  title?: string;
  /** 자동 소멸 시간(ms). 0 이면 수동 닫기 전까지 유지 */
  duration: number;
}

export interface ToastOptions {
  title?: string;
  duration?: number;
}

export interface ConfirmOptions {
  title: string;
  /** 본문 설명 (선택) */
  description?: string;
  confirmText?: string;
  cancelText?: string;
  /** 삭제 등 파괴적 동작이면 확인 버튼을 위험(빨강) 스타일로 */
  danger?: boolean;
  /** 확인 버튼 앞에 붙는 이모지/아이콘 텍스트 */
  icon?: string;
}

interface ConfirmState {
  options: ConfirmOptions;
  resolve: (ok: boolean) => void;
}

interface UIStore {
  toasts: Toast[];
  confirmState: ConfirmState | null;

  addToast: (toast: Omit<Toast, "id" | "duration"> & { duration?: number }) => string;
  removeToast: (id: string) => void;
  confirm: (options: ConfirmOptions) => Promise<boolean>;
  resolveConfirm: (ok: boolean) => void;
}

/** 짧은 유니크 ID (외부 의존성 없이) */
function genId(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`;
}

/** 타입별 기본 노출 시간 */
const DEFAULT_DURATION: Record<ToastType, number> = {
  success: 3200,
  info: 3200,
  warning: 4200,
  error: 5000,
};

export const useUIStore = create<UIStore>((set, get) => ({
  toasts: [],
  confirmState: null,

  addToast: ({ type, message, title, duration }) => {
    const id = genId();
    const toast: Toast = {
      id,
      type,
      message,
      title,
      duration: duration ?? DEFAULT_DURATION[type],
    };
    set((state) => ({ toasts: [...state.toasts, toast] }));
    return id;
  },

  removeToast: (id) => {
    set((state) => ({ toasts: state.toasts.filter((t) => t.id !== id) }));
  },

  confirm: (options) => {
    // 이미 열려 있던 확인창이 있으면 취소 처리 후 새 창을 띄움
    const prev = get().confirmState;
    if (prev) prev.resolve(false);
    return new Promise<boolean>((resolve) => {
      set({ confirmState: { options, resolve } });
    });
  },

  resolveConfirm: (ok) => {
    const current = get().confirmState;
    if (current) {
      current.resolve(ok);
      set({ confirmState: null });
    }
  },
}));

/* ─────────────────────── 편의 헬퍼 (컴포넌트 밖에서도 사용 가능) ─────────────────────── */

export const toast = {
  success: (message: string, options?: ToastOptions) =>
    useUIStore.getState().addToast({ type: "success", message, ...options }),
  error: (message: string, options?: ToastOptions) =>
    useUIStore.getState().addToast({ type: "error", message, ...options }),
  info: (message: string, options?: ToastOptions) =>
    useUIStore.getState().addToast({ type: "info", message, ...options }),
  warning: (message: string, options?: ToastOptions) =>
    useUIStore.getState().addToast({ type: "warning", message, ...options }),
};

/** Promise<boolean> 를 반환하는 확인 다이얼로그. true = 확인, false = 취소 */
export const confirmDialog = (options: ConfirmOptions): Promise<boolean> =>
  useUIStore.getState().confirm(options);
