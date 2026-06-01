"use client";

import React, { useEffect, useState } from "react";
import { Menu, FileText, Sparkles, Sun, Moon, LogOut } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useAuthStore } from "@/store/useAuthStore";
import ExportButton from "@/components/chat/ExportButton";

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  // 💡 Hydration 에러 방지: 마운트 상태 추가 (모든 hooks 바로 아래)
  const [isMounted, setIsMounted] = useState(false);

  const { sessions, activeSessionId } = useChatStore();
  const { user, logout } = useAuthStore();
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  // 💡 마운트 전 렌더링 완벽히 차단 (방어막이 모든 hooks 바로 아래)
  if (!isMounted) {
    return null;
  }

  // 💡 브라우저 마운트 완료 후 렌더링
  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (!isMounted) return; // 마운트 후에만 실행

    // 💡 안전한 localStorage 접근 (브라우저 환경 검증)
    if (typeof window === "undefined" || typeof localStorage === "undefined") {
      return;
    }

    try {
      // 초기 테마 로드
      const savedTheme = localStorage.getItem("theme");
      const isDark = savedTheme === "dark" || (!savedTheme && document.documentElement.classList.contains("dark"));
      setTheme(isDark ? "dark" : "light");
      if (isDark) {
        document.documentElement.classList.add("dark");
      } else {
        document.documentElement.classList.remove("dark");
      }
    } catch (error) {
      console.error("Theme loading error:", error);
    }
  }, [isMounted]);

  const toggleTheme = () => {
    // 💡 안전한 테마 토글 (브라우저 환경 검증)
    if (typeof window === "undefined" || typeof localStorage === "undefined") {
      return;
    }

    try {
      const nextTheme = theme === "dark" ? "light" : "dark";
      setTheme(nextTheme);
      if (nextTheme === "dark") {
        document.documentElement.classList.add("dark");
        localStorage.setItem("theme", "dark");
      } else {
        document.documentElement.classList.remove("dark");
        localStorage.setItem("theme", "light");
      }
    } catch (error) {
      console.error("Theme toggle error:", error);
    }
  };

  return (
    <header className="header-blur header-safe-area sticky top-0 z-30 w-full">
      <div className="h-14 w-full flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onMenuClick}
            className="md:hidden p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-accent/50 rounded-lg transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="hidden md:flex items-center gap-2">
            <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-indigo-600 flex items-center justify-center shadow-sm">
              <span className="text-white text-[10px] font-bold">V</span>
            </div>
            <h1 className="font-semibold text-[15px] tracking-tight">Vision RAG</h1>
          </div>

          {/* 모바일에서 제목 표시 */}
          <h1 className="md:hidden font-semibold text-[15px] tracking-tight">Vision RAG</h1>
        </div>

        {/* 활성 대화 표시 및 우측 제어 */}
        <div className="flex items-center gap-3">
          {activeSession && (
            <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground bg-accent/30 px-3 py-1.5 rounded-full">
              <Sparkles className="w-3.5 h-3.5 text-primary/70" />
              <span className="max-w-[150px] truncate">{activeSession.title}</span>
            </div>
          )}

          <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
            <Sparkles className="w-3.5 h-3.5 text-primary/50" />
            <span className="hidden sm:inline">Gemini 3.1 Flash-Lite</span>
          </div>

          {/* 대화 내보내기 버튼 */}
          {activeSession && <ExportButton />}

          {/* 테마 토글 버튼 (마이크로 모션 제공) */}
          <button
            onClick={toggleTheme}
            aria-label="테마 전환"
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent/40 rounded-lg border border-border/20 transition-all duration-300 hover:scale-105 active:scale-95"
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4 text-amber-400 rotate-0 transition-transform duration-500" />
            ) : (
              <Moon className="w-4 h-4 text-violet-600 -rotate-12 transition-transform duration-500" />
            )}
          </button>

          {/* 💡 구글 프로필 & 로그아웃 버튼 */}
          {user && (
            <div className="flex items-center gap-2 border-l border-border/20 pl-2">
              {user.picture ? (
                <img
                  src={user.picture}
                  alt={user.name}
                  className="w-6 h-6 rounded-full border border-border/40 object-cover"
                  referrerPolicy="no-referrer"
                />
              ) : (
                <div className="w-6 h-6 rounded-full bg-violet-500/20 text-violet-400 flex items-center justify-center text-[10px] font-bold">
                  {user.name.slice(0, 1)}
                </div>
              )}
              <button
                onClick={() => {
                  // 활성 세션 초기화 후 로그아웃 (순환 참조 방지를 위해 여기서 순차 호출)
                  useChatStore.getState().resetActiveSession();
                  logout();
                }}
                title="로그아웃"
                className="p-2 text-muted-foreground hover:text-red-400 hover:bg-red-500/10 rounded-lg border border-border/20 transition-all duration-300 hover:scale-105 active:scale-95"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          )}
        </div>
      </div>
    </header>
  );
}
