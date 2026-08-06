"use client";

import React from "react";
import { Menu, Sun, Moon } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useMounted } from "@/hooks/useMounted";
import { useTheme } from "@/hooks/useTheme";
import ExportButton from "@/components/chat/ExportButton";

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const mounted = useMounted();
  const activeSessionId = useChatStore((s) => s.activeSessionId);
  const activeSession = useChatStore((s) =>
    s.sessions.find((session) => session.id === s.activeSessionId)
  );
  const { theme, toggleTheme } = useTheme();

  // 테마 아이콘이 SSR/CSR 간 어긋나는 것을 막기 위해 마운트 전에는 헤더 골격만 유지
  const title = activeSession?.title?.trim() || "TechNote";

  return (
    <header className="app-header header-safe-area sticky top-0 z-30 w-full">
      <div className="h-14 w-full flex items-center gap-2 px-3 md:px-4">
        <button
          onClick={onMenuClick}
          aria-label="메뉴 열기"
          className="btn-ghost md:hidden p-2 -ml-1 rounded-md"
        >
          <Menu className="w-5 h-5" />
        </button>

        {/* 현재 대화 제목 — 사이드바에 이미 로고가 있으므로 헤더는 컨텍스트만 보여준다 */}
        <h1 className="min-w-0 flex-1 truncate text-[15px] font-medium text-foreground">
          {title}
        </h1>

        <div className="flex items-center gap-1 shrink-0">
          {activeSessionId && <ExportButton />}

          <button
            onClick={toggleTheme}
            aria-label={theme === "dark" ? "라이트 모드로 전환" : "다크 모드로 전환"}
            className="btn-ghost p-2 rounded-md"
          >
            {mounted && theme === "dark" ? (
              <Sun className="w-[18px] h-[18px]" />
            ) : (
              <Moon className="w-[18px] h-[18px]" />
            )}
          </button>
        </div>
      </div>
    </header>
  );
}
