import React, { useEffect, useRef } from "react";
import { useAuthStore } from "@/store/useAuthStore";
import { KeyRound, ShieldCheck, HelpCircle } from "lucide-react";

declare global {
  interface Window {
    google?: any;
  }
}

// 백엔드 API로부터 불러올 설정값
const GOOGLE_CLIENT_ID = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "1023361734160-rfo5n5kufp15b0h5efknm46kki58j77t.apps.googleusercontent.com";

export default function LoginView() {
  const { loginWithGoogleCredential, isLoading, errorMsg, clearError } = useAuthStore();
  const googleBtnRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
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
              const success = await loginWithGoogleCredential(response.credential);
              if (success) {
                // 로그인 성공 시 상태 업데이트로 인해 메인 화면으로 전환됩니다.
                window.location.reload(); 
              }
            }
          },
          auto_select: false, // 자동 로그인 차단 (계정 선택 유도)
        });

        // 3. 커스텀 버튼 렌더링
        if (googleBtnRef.current) {
          window.google.accounts.id.renderButton(googleBtnRef.current, {
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
      document.body.removeChild(script);
    };
  }, [loginWithGoogleCredential, clearError]);

  return (
    <div className="relative min-h-screen w-full flex items-center justify-center overflow-hidden bg-[#0a0f1d] px-4">
      {/* 🌌 다이내믹 오로라 네온 배경 효과 */}
      <div className="absolute top-[-10%] left-[-20%] w-[60vw] h-[60vw] rounded-full bg-violet-600/10 blur-[120px] animate-pulse" style={{ animationDuration: "8s" }} />
      <div className="absolute bottom-[-10%] right-[-10%] w-[50vw] h-[50vw] rounded-full bg-blue-500/10 blur-[120px] animate-pulse" style={{ animationDuration: "12s" }} />
      
      {/* 🖼️ 글래스모피즘 로그인 카드 */}
      <div className="relative z-10 w-full max-w-md backdrop-blur-2xl bg-white/5 border border-white/10 shadow-[0_20px_50px_rgba(0,0,0,0.4)] rounded-3xl p-8 text-center flex flex-col items-center">
        {/* 아이콘 헤더 */}
        <div className="w-16 h-16 rounded-2xl bg-gradient-to-tr from-violet-600 to-blue-500 flex items-center justify-center shadow-lg shadow-violet-600/30 mb-6">
          <KeyRound className="w-8 h-8 text-white animate-bounce" style={{ animationDuration: "3s" }} />
        </div>

        {/* 로고 */}
        <h1 className="text-3xl font-extrabold text-transparent bg-clip-text bg-gradient-to-r from-violet-400 via-pink-400 to-blue-400 tracking-tight mb-2">
          💎 Vision RAG
        </h1>
        <p className="text-xs text-white/40 font-mono tracking-widest uppercase mb-6">
          Vectorless Agentic PDF Search
        </p>

        {/* 💡 시스템 안내 카드 */}
        <div className="w-full bg-white/5 border border-white/5 rounded-2xl p-4 mb-6 text-left">
          <div className="flex items-start gap-2.5 text-violet-400 text-sm font-semibold mb-1">
            <ShieldCheck className="w-5 h-5 flex-shrink-0" />
            <span>보안 인증 기반 시스템</span>
          </div>
          <p className="text-white/70 text-xs leading-relaxed">
            본 시스템은 기밀 유지 및 사내 자산 보안을 위해 
            <strong> 사전에 승인된 사용자 계정</strong>으로만 접근이 가능합니다. 
            권한을 획득하신 본인의 구글 계정으로 로그인해 주시기 바랍니다.
          </p>
        </div>

        {/* 로딩 표시 */}
        {isLoading ? (
          <div className="flex flex-col items-center justify-center py-4">
            <div className="w-8 h-8 border-4 border-violet-500 border-t-transparent rounded-full animate-spin mb-2" />
            <span className="text-xs text-white/50">사용자 권한 검증 요청 중...</span>
          </div>
        ) : (
          /* 구글 로그인 버튼 컨테이너 */
          <div className="my-4 transition-all duration-300 hover:scale-105" ref={googleBtnRef} id="google-login-btn" />
        )}

        {/* ❌ 정중한 에러 표시 영역 */}
        {errorMsg && (
          <div className="mt-6 w-full p-4 rounded-xl border border-red-500/20 bg-red-950/20 text-center animate-shake">
            <p className="text-xs font-semibold text-red-400 mb-1.5">
              ⚠️ 접근 권한 승인 실패
            </p>
            <p className="text-[11px] text-white/60 leading-relaxed">
              본 시스템에 등록되지 않은 구글 계정입니다. 서비스 이용 및 접근 권한 활성화가 필요하신 경우, <strong>시스템 관리자</strong>에게 계정 정보 등록을 요청해 주시기 바랍니다.
            </p>
          </div>
        )}

        {/* 카피라이트 */}
        <span className="text-[10px] text-white/20 mt-8 flex items-center gap-1">
          <HelpCircle className="w-3.5 h-3.5" />
          보안 계정 및 사내 문서 보호 정책 연동
        </span>
      </div>
    </div>
  );
}
