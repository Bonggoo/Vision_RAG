"use client";

import React from "react";
import { Menu, FileText, Sparkles } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";

interface HeaderProps {
  onMenuClick?: () => void;
}

export default function Header({ onMenuClick }: HeaderProps) {
  const { sessions, activeSessionId } = useChatStore();
  const activeSession = sessions.find((s) => s.id === activeSessionId);

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
          <div className="w-6 h-6 rounded-md bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center">
            <span className="text-white text-[10px] font-bold">V</span>
          </div>
          <h1 className="font-semibold text-[15px] tracking-tight">Vision RAG</h1>
        </div>

        {/* 모바일에서 제목 표시 */}
        <h1 className="md:hidden font-semibold text-[15px] tracking-tight">Vision RAG</h1>
      </div>

      {/* 활성 대화 표시 */}
      <div className="flex items-center gap-3">
        {activeSession && (
          <div className="hidden sm:flex items-center gap-2 text-xs text-muted-foreground bg-accent/30 px-3 py-1.5 rounded-full">
            <Sparkles className="w-3 h-3 text-primary/70" />
            <span className="max-w-[200px] truncate">{activeSession.title}</span>
          </div>
        )}

        <div className="flex items-center gap-1.5 text-xs text-muted-foreground/60">
          <Sparkles className="w-3.5 h-3.5 text-primary/50" />
          <span className="hidden sm:inline">Gemini 3.1 Flash-Lite</span>
        </div>
      </div>
    </header>
  );
}
