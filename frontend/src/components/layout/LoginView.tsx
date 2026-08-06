"use client";

import React, { useEffect } from "react";
import { useAuthStore } from "@/store/useAuthStore";
import { useMounted } from "@/hooks/useMounted";
import SparkleLogo from "./SparkleLogo";

declare global {
  interface Window {
    google?: {
      accounts?: {
        id?: {
          initialize: (config: Record<string, unknown>) => void;
          renderButton: (el: HTMLElement, options: Record<string, unknown>) => void;
        };
      };
    };
  }
}

const GOOGLE_CLIENT_ID =
  process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID ||
  "1023361734160-rfo5n5kufp15b0h5efknm46kki58j77t.apps.googleusercontent.com";

export default function LoginView() {
  const isMounted = useMounted();
  const { loginWithGoogleCredential, isLoading, errorMsg, clearError } = useAuthStore();

  useEffect(() => {
    if (!isMounted) return;
    clearError();

    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;

    script.onload = () => {
      const gsi = window.google?.accounts?.id;
      if (!gsi) return;

      gsi.initialize({
        client_id: GOOGLE_CLIENT_ID,
        callback: async (response: { credential?: string }) => {
          // Zustand 상태 변경만으로 React 가 메인 화면을 다시 그린다 (reload 금지 — persist 와 충돌)
          if (response.credential) await loginWithGoogleCredential(response.credential);
        },
        auto_select: false, // 자동 로그인 차단 (계정 선택 유도)
      });

      const target = document.getElementById("google-login-btn");
      if (target) {
        gsi.renderButton(target, {
          theme: document.documentElement.classList.contains("dark") ? "filled_black" : "outline",
          size: "large",
          shape: "rectangular",
          width: 280,
          locale: "ko",
        });
      }
    };

    document.body.appendChild(script);
    return () => {
      if (document.body.contains(script)) document.body.removeChild(script);
    };
  }, [isMounted, loginWithGoogleCredential, clearError]);

  if (!isMounted) return null;

  return (
    <main className="min-h-screen w-full flex items-center justify-center bg-background px-4">
      <div className="w-full max-w-sm text-center animate-slide-up">
        <SparkleLogo className="w-9 h-9 mx-auto mb-5 text-primary" />

        <h1 className="font-display text-[30px] tracking-tight mb-1.5">TechNote</h1>
        <p className="text-[13.5px] text-muted-foreground mb-8">
          산업용 매뉴얼을 읽고 답해주는 AI 어시스턴트
        </p>

        <div className="flex justify-center min-h-[44px]">
          {isLoading ? (
            <span className="flex items-center gap-2 text-[13px] text-muted-foreground">
              <span
                className="w-4 h-4 rounded-full border-2 border-border border-t-foreground animate-spin"
                aria-hidden="true"
              />
              로그인 확인 중
            </span>
          ) : (
            <div id="google-login-btn" />
          )}
        </div>

        {errorMsg && (
          <div
            role="alert"
            className="mt-6 p-4 rounded-lg border border-destructive/30 bg-destructive/5 text-left"
          >
            <p className="text-[13px] font-medium text-destructive mb-1">접근 권한이 없습니다</p>
            <p className="text-[12.5px] text-muted-foreground leading-relaxed">
              등록되지 않은 구글 계정입니다. 이용이 필요하시면 시스템 관리자에게 계정 등록을 요청해
              주세요.
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
