"use client";

import React, { useEffect, useState } from "react";
import { Menu, FileText, Sparkles, Sun, Moon } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const { sessions, activeSessionId } = useChatStore();
  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const [theme, setTheme] = useState<"light" | "dark">("dark");

  useEffect(() => {
    // 초기 테마 로드
    const savedTheme = localStorage.getItem("theme");
    const isDark = savedTheme === "dark" || (!savedTheme && document.documentElement.classList.contains("dark"));
    setTheme(isDark ? "dark" : "light");
    if (isDark) {
      document.documentElement.classList.add("dark");
    } else {
      document.documentElement.classList.remove("dark");
    }
  }, []);

  const toggleTheme = () => {
    const nextTheme = theme === "dark" ? "light" : "dark";
    setTheme(nextTheme);
    if (nextTheme === "dark") {
      document.documentElement.classList.add("dark");
      localStorage.setItem("theme", "dark");
    } else {
      document.documentElement.classList.remove("dark");
      localStorage.setItem("theme", "light");
    }
  };

  return (
    <header className="header-blur h-14 flex items-center justify-between px-4 sticky top-0 z-30">
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
            <Sparkles className="w-3 h-3 text-primary/70" />
            <span className="max-w-[150px] truncate">{activeSession.title}</span>
          </div>
        )}

        <div className="flex items-center gap-2 text-xs text-muted-foreground/60">
          <Sparkles className="w-3.5 h-3.5 text-primary/50" />
          <span className="hidden sm:inline">Gemini 3.1 Flash-Lite</span>
        </div>

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
      </div>
    </header>
  );
}


