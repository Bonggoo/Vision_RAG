import React, { useEffect, useState } from "react";
import { useAuthStore } from "@/store/useAuthStore";
import { KeyRound } from "lucide-react";
import SparkleLogo from "./SparkleLogo";

declare global {
  interface Window {
    google?: any;
  }
}

// 백엔드 API로부터 불러올 설정값
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "1023361734160-rfo5n5kufp15b0h5efknm46kki58j77t.apps.googleusercontent.com";

export default function LoginView() {
  // 💡 Hydration 에러 방지: 마운트 상태 추가
  const [isMounted, setIsMounted] = useState(false);

  const { loginWithGoogleCredential, isLoading, errorMsg, clearError } = useAuthStore();

  // 💡 브라우저 마운트 완료 후 렌더링
  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return; // 마운트 후에만 실행

    // 에러 상태 초기 청소
    clearError();

    // 1. Google 1-Tap & Sign In Script 동적 로드
    const script = document.createElement("script");
    script.src = "https://accounts.google.com/gsi/client";
    script.async = true;
    script.defer = true;
    document.body.appendChild(script);

    script.onload = () => {
      if (window.google?.accounts?.id) {
        // 2. Google Identity Services 초기화
        window.google.accounts.id.initialize({
          client_id: GOOGLE_CLIENT_ID,
          callback: async (response: any) => {
            if (response.credential) {
              await loginWithGoogleCredential(response.credential);
              // 💡 reload() 제거: Zustand 상태 변경(isAuthenticated=true)이
              // React를 자동으로 리렌더하여 메인 화면으로 전환합니다.
              // reload()는 sessionStorage persist와 타이밍 충돌을 일으킵니다.
            }
          },
          auto_select: false, // 자동 로그인 차단 (계정 선택 유도)
        });

        // 3. 커스텀 버튼 렌더링
        const googleBtnRef = document.getElementById("google-login-btn");
        if (googleBtnRef) {
          window.google.accounts.id.renderButton(googleBtnRef, {
            theme: "filled_blue",
            size: "large",
            shape: "pill",
            width: 280,
            locale: "ko",
          });
        }
      }
    };

    return () => {
      if (document.body.contains(script)) {
        document.body.removeChild(script);
      }
    };
  }, [isMounted, loginWithGoogleCredential, clearError]);

  // 마운트 전에는 조건부 렌더링 방어막
  if (!isMounted) {
    return null;
  }

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-hidden bg-background px-4">
      {/* 🌌 다이내믹 오로라 네온 배경 효과 (라이트/다크 모두 은은하게 적용) */}
      <div className="absolute top-[-10%] left-[-20%] w-[60vw] h-[60vw] rounded-full bg-violet-500/15 dark:bg-violet-600/10 blur-[120px] animate-pulse" style={{ animationDuration: "8s" }} />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-blue-500/15 dark:bg-blue-500/10 blur-[120px] animate-pulse" style={{ animationDuration: "12s" }} />
      
      {/* 🖼️ 글래스모피즘 로그인 카드 */}
      <div className="relative z-10 w-full max-w-md backdrop-blur-3xl bg-card/40 border border-border/40 shadow-2xl rounded-[2rem] p-8 md:p-10 text-center flex flex-col items-center">
        {/* 아이콘 헤더 */}
        <div className="w-16 h-16 rounded-2xl bg-card border border-border/40 flex items-center justify-center shadow-lg mb-6 relative overflow-hidden">
          <div className="absolute inset-0 bg-gradient-to-br from-violet-500/5 to-indigo-500/5" />
          <SparkleLogo className="w-9 h-9 filter drop-shadow-[0_4px_12px_rgba(139,92,246,0.4)] relative z-10" />
        </div>

        {/* 로고 */}
        <h1 className="text-3xl md:text-4xl font-extrabold font-display text-transparent bg-clip-text bg-gradient-to-r from-violet-500 via-indigo-500 to-blue-500 tracking-tight mb-2">
          TechNote
        </h1>
        <p className="text-xs md:text-[13px] text-muted-foreground/80 font-mono tracking-widest uppercase mb-8 font-medium">
          AI-Powered Industrial Assistant
        </p>



        {/* 로딩 표시 */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-4">
            <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mb-3 shadow-lg shadow-violet-500/20" />
            <span className="text-xs font-medium text-muted-foreground/80">사용자 권한 검증 요청 중...</span>
          </div>
        ) : (
          /* 구글 로그인 버튼 컨테이너 */
          <div className="my-4 transition-transform duration-300 hover:scale-[1.02] active:scale-[0.98] drop-shadow-sm" id="google-login-btn" />
        )}

        {/* ❌ 정중한 에러 표시 영역 */}
        {errorMsg && (
          <div className="mt-6 w-full p-4 rounded-2xl border border-destructive/20 bg-destructive/5 text-center animate-shake backdrop-blur-md">
            <p className="text-xs font-bold text-destructive mb-1.5 flex items-center justify-center gap-1.5">
              <span className="text-sm">⚠️</span> 접근 권한 승인 실패
            </p>
            <p className="text-[11px] text-destructive/80 leading-relaxed font-medium">
              본 시스템에 등록되지 않은 구글 계정입니다. 서비스 이용 및 접근 권한 활성화가 필요하신 경우, <strong>시스템 관리자</strong>에게 계정 등록을 요청해 주세요.
            </p>
          </div>
        )}


      </div>
    </div>
  );
}
