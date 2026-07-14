import { create } from "zustand";
import { persist } from "zustand/middleware";
import { useChatStore } from "@/store/useChatStore";

interface UserProfile {
  email: string;
  name: string;
  picture: string;
}

interface AuthStore {
  token: string | null;
  user: UserProfile | null;
  isAuthenticated: boolean;
  isLoading: boolean;
  errorMsg: string | null;
  /** 앱 시작 시 세션 검증 완료 여부 (false면 로딩 스피너 표시) */
  isSessionVerified: boolean;
  
  loginWithGoogleCredential: (credential: string) => Promise<boolean>;
  logout: () => Promise<void>;
  clearError: () => void;
  /** 앱 시작 시 호출: 저장된 토큰이 실제로 유효한지 서버에 확인 */
  verifySession: () => Promise<void>;
}

// 💡 백엔드 API 기본 주소 (lib/api.ts와 일치시킴)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const useAuthStore = create<AuthStore>()(
  persist(
    (set, get) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      errorMsg: null,
      isSessionVerified: false,

      loginWithGoogleCredential: async (credential: string) => {
        set({ isLoading: true, errorMsg: null });
        try {
          const response = await fetch(`${API_BASE_URL}/api/auth/google`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ credential }),
            credentials: "include", // 쿠키를 수신하기 위해 credentials 포함
          });

          if (!response.ok) {
            const errData = await response.json();
            throw new Error(errData.detail || "인증 실패: 권한이 없거나 만료된 토큰입니다.");
          }

          const data = await response.json();
          
          set({
            token: data.access_token,
            user: {
              email: data.email,
              name: data.name,
              picture: data.picture,
            },
            isAuthenticated: true,
            isLoading: false,
            isSessionVerified: true,
            errorMsg: null,
          });
          return true;
        } catch (error: any) {
          console.error("🔒 Google OAuth Login Error:", error);
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            isLoading: false,
            isSessionVerified: true,
            errorMsg: error.message || "구글 로그인에 실패했습니다. 다시 시도해 주세요.",
          });
          return false;
        }
      },

      logout: async () => {
        // 채팅 세션 전체 초기화 (로그아웃 시 대화 기록 삭제)
        useChatStore.getState().clearAllSessions();

        try {
          // 백엔드 세션 파괴 (Refresh Token 쿠키 삭제)
          await fetch(`${API_BASE_URL}/api/auth/logout`, {
            method: "POST",
            credentials: "include",
          });
        } catch (error) {
          console.error("🔒 Failed to notify logout to backend:", error);
        }

        set({
          token: null,
          user: null,
          isAuthenticated: false,
          isLoading: false,
          errorMsg: null,
        });
      },

      clearError: () => {
        set({ errorMsg: null });
      },

      verifySession: async () => {
        const { isAuthenticated, token } = get();

        // localStorage에 로그인 상태가 없으면 검증 불필요
        if (!isAuthenticated || !token) {
          set({ isSessionVerified: true });
          return;
        }

        try {
          // 1차: 저장된 Access Token으로 서버 확인
          const res = await fetch(`${API_BASE_URL}/documents`, {
            headers: { "Authorization": `Bearer ${token}` },
            credentials: "include",
          });

          if (res.ok) {
            // ✅ 토큰 유효 — 정상 진입
            set({ isSessionVerified: true });
            return;
          }

          if (res.status !== 401) {
            // 서버 일시 오류(콜드스타트 등) — 로그아웃하지 않고 기존 세션 유지, 이후 요청에서 재시도
            console.warn(`🔒 세션 확인 일시 실패(HTTP ${res.status}) — 기존 세션 유지`);
            set({ isSessionVerified: true });
            return;
          }

          // 2차: Access Token 만료 → Refresh Token(쿠키)으로 갱신 시도
          const refreshRes = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
            method: "POST",
            credentials: "include",
          });

          if (refreshRes.ok) {
            const data = await refreshRes.json();
            // ✅ 갱신 성공 — 새 토큰 저장
            set({
              token: data.access_token,
              isSessionVerified: true,
            });
            return;
          }

          if (refreshRes.status !== 401) {
            // 리프레시 서버 일시 오류 — 리프레시 토큰 자체는 무효로 확인된 게 아니므로 세션 유지
            console.warn(`🔒 세션 갱신 일시 실패(HTTP ${refreshRes.status}) — 기존 세션 유지`);
            set({ isSessionVerified: true });
            return;
          }

          // ❌ 리프레시 토큰까지 만료/무효(401) → 세션 만료, 로그아웃
          console.warn("🔒 세션 만료: 로그인 화면으로 이동합니다.");
          set({
            token: null,
            user: null,
            isAuthenticated: false,
            isSessionVerified: true,
          });
        } catch (error) {
          // 네트워크 오류 등 — 일단 기존 상태 유지 (오프라인 대비)
          console.error("🔒 세션 검증 실패 (네트워크 오류):", error);
          set({ isSessionVerified: true });
        }
      },
    }),
    {
      name: "vision-rag-auth-storage",
      // isSessionVerified는 persist 대상에서 제외 (앱 시작마다 재검증)
      partialize: (state) => ({
        token: state.token,
        user: state.user,
        isAuthenticated: state.isAuthenticated,
      }),
      storage: {
        getItem: (name: string) => {
          if (typeof window === "undefined") return null;
          const value = localStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name: string, value: unknown) => {
          if (typeof window === "undefined") return;
          localStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name: string) => {
          if (typeof window === "undefined") return;
          localStorage.removeItem(name);
        },
      },
    }
  )
);
