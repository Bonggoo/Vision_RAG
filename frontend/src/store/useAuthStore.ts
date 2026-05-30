import { create } from "zustand";
import { persist } from "zustand/middleware";

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
  
  loginWithGoogleCredential: (credential: string) => Promise<boolean>;
  logout: () => void;
  clearError: () => void;
}

// 💡 백엔드 API 기본 주소 (lib/api.ts와 일치시킴)
const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const useAuthStore = create<AuthStore>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      isAuthenticated: false,
      isLoading: false,
      errorMsg: null,

      loginWithGoogleCredential: async (credential: string) => {
        set({ isLoading: true, errorMsg: null });
        try {
          const response = await fetch(`${API_BASE_URL}/api/auth/google`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
            },
            body: JSON.stringify({ credential }),
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
            errorMsg: error.message || "구글 로그인에 실패했습니다. 다시 시도해 주세요.",
          });
          return false;
        }
      },

      logout: () => {
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
    }),
    {
      name: "vision-rag-auth-storage",
      storage: {
        getItem: (name: string) => {
          if (typeof window === "undefined") return null;
          const value = sessionStorage.getItem(name);
          return value ? JSON.parse(value) : null;
        },
        setItem: (name: string, value: unknown) => {
          if (typeof window === "undefined") return;
          sessionStorage.setItem(name, JSON.stringify(value));
        },
        removeItem: (name: string) => {
          if (typeof window === "undefined") return;
          sessionStorage.removeItem(name);
        },
      },
    }
  )
);
