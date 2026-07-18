"use client";

import React, { useEffect, useState } from "react";
import { Menu, Sun, Moon } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import ExportButton from "@/components/chat/ExportButton";
import SparkleLogo from "./SparkleLogo";

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  // 💡 Hydration 에러 방지: 마운트 상태 추가
  const [isMounted, setIsMounted] = useState(false);

  const { activeSessionId } = useChatStore();

  const [theme, setTheme] = useState<"light" | "dark">("dark");

  // 💡 브라우저 마운트 완료 후 렌더링
  useEffect(() => {
    setIsMounted(true);
  }, []);

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

  // 마운트 전에는 조건부 렌더링 방어막
  if (!isMounted) {
    return null;
  }

  return (
    <header className="header-blur header-safe-area sticky top-0 z-30 w-full relative">
      <div className="h-14 w-full flex items-center justify-between px-4">
        <div className="flex items-center gap-3">
          <button
            onClick={onMenuClick}
            aria-label="메뉴 열기"
            className="md:hidden p-2 -ml-2 text-muted-foreground hover:text-foreground hover:bg-accent/50 rounded-lg transition-colors"
          >
            <Menu className="w-5 h-5" />
          </button>

          <div className="flex items-center gap-2">
            <SparkleLogo className="w-6 h-6 filter drop-shadow-[0_1.5px_5px_rgba(139,92,246,0.3)]" />
            <h1 className="font-semibold font-display text-[16px] tracking-tight text-foreground">TechNote</h1>
          </div>
        </div>

        {/* 우측 제어 */}
        <div className="flex items-center gap-3">
          {/* 대화 내보내기 버튼 */}
          {activeSessionId && <ExportButton />}

          {/* 테마 토글 버튼 (마이크로 모션 제공) */}
          <button
            onClick={toggleTheme}
            aria-label="테마 전환"
            className="p-2 text-muted-foreground hover:text-foreground hover:bg-accent/40 rounded-full border border-border/20 transition-all duration-300 hover:scale-105 active:scale-95"
          >
            {theme === "dark" ? (
              <Sun className="w-4 h-4 text-white rotate-0 transition-transform duration-500" />
            ) : (
              <Moon className="w-4 h-4 text-primary -rotate-12 transition-transform duration-500" />
            )}
          </button>
        </div>
      </div>
      {/* 헤더 하단 그라데이션 라인 */}
      <div className="header-gradient-line" />
    </header>
  );
}
