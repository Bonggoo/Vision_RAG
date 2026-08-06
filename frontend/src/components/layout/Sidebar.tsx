"use client";

import React, { useEffect, useRef, useState } from "react";
import {
  MessageSquare,
  FileText,
  UploadCloud,
  X,
  PanelLeftClose,
  PanelLeftOpen,
  Plus,
} from "lucide-react";
import { useDocumentStore } from "@/store/useDocumentStore";
import { useChatStore } from "@/store/useChatStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useMounted } from "@/hooks/useMounted";
import { toast } from "@/store/useUIStore";
import { processUploadFiles } from "@/lib/upload";
import { isSupportedUploadFile, UNSUPPORTED_FORMAT_MESSAGE } from "@/lib/fileTypes";
import SparkleLogo from "./SparkleLogo";
import SessionList from "./sidebar/SessionList";
import DocsPanel from "./sidebar/DocsPanel";
import UserMenu from "./sidebar/UserMenu";
import { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs } from "./sidebar/utils";

// 기존 공개 API 유지 — 외부에서 Sidebar 경유로 헬퍼를 import 하는 코드 호환
export { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs };

/** 분석 중 문서 상태를 따라잡기 위한 목록 폴링 주기 */
const DOC_POLL_INTERVAL_MS = 60_000;

type SidebarTab = "chat" | "docs";

interface SidebarProps {
  isOpen?: boolean;
  onClose?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}

/**
 * 앱 사이드바.
 * 레이아웃(탭 전환·반응형·드래그 앤 드롭)만 담당하고,
 * 실제 내용은 SessionList / DocsPanel / UserMenu 가 각자 소유한다.
 */
export default function Sidebar({ isOpen, onClose, isCollapsed, onToggleCollapse }: SidebarProps) {
  const isMounted = useMounted();
  const [activeTab, setActiveTab] = useState<SidebarTab>("chat");
  const [isDragging, setIsDragging] = useState(false);
  const dragDepth = useRef(0);

  const { documents, fetchDocuments, uploadDocuments, isUploading } = useDocumentStore();
  const sessions = useChatStore((s) => s.sessions);
  const createSession = useChatStore((s) => s.createSession);
  const setActiveSession = useChatStore((s) => s.setActiveSession);
  const user = useAuthStore((s) => s.user);

  const mySessionCount = sessions.filter((s) => s.ownerEmail === user?.email || !s.ownerEmail).length;
  const readyDocCount = documents.filter((d) => d.status !== "analyzing").length;

  // 열려 있는 동안 문서 목록 폴링 (분석 완료 반영). 업로드 중에는 건너뛴다.
  useEffect(() => {
    const isDesktop = typeof window !== "undefined" && window.innerWidth >= 768;
    if (!isDesktop && !isOpen) return;

    fetchDocuments();
    const interval = setInterval(() => {
      if (!isUploading) fetchDocuments();
    }, DOC_POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [isOpen, fetchDocuments, isUploading]);

  // dragenter/leave 가 자식 요소마다 발생하므로 깊이를 세어 깜빡임을 막는다
  const handleDragEnter = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current += 1;
    setIsDragging(true);
  };
  const handleDragLeave = (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current = Math.max(0, dragDepth.current - 1);
    if (dragDepth.current === 0) setIsDragging(false);
  };
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault();
    dragDepth.current = 0;
    setIsDragging(false);

    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    const supported = files.filter(isSupportedUploadFile);
    if (supported.length === 0) {
      toast.warning(UNSUPPORTED_FORMAT_MESSAGE);
      return;
    }
    setActiveTab("docs");
    await processUploadFiles(supported, uploadDocuments, fetchDocuments);
  };

  const handleQuickNewChat = async () => {
    const empty = sessions.find((s) => s.messages.length === 0);
    setActiveSession(empty ? empty.id : await createSession("새로운 대화"));
    onToggleCollapse?.();
  };

  if (!isMounted) return null;

  const tabs: { id: SidebarTab; label: string; icon: typeof MessageSquare; count: number }[] = [
    { id: "chat", label: "대화", icon: MessageSquare, count: mySessionCount },
    { id: "docs", label: "문서", icon: FileText, count: readyDocCount },
  ];

  const content = (
    <div
      onDragEnter={handleDragEnter}
      onDragOver={(e) => e.preventDefault()}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      className="relative flex flex-col h-full"
    >
      {isDragging && (
        <div className="absolute inset-2 z-50 rounded-lg border-2 border-dashed border-primary bg-background/90 flex flex-col items-center justify-center gap-2 pointer-events-none">
          <UploadCloud className="w-7 h-7 text-primary" />
          <p className="text-[13px] font-medium">여기에 놓아 업로드</p>
        </div>
      )}

      <div className="flex items-center justify-between gap-2 px-3 h-14 shrink-0">
        <span className="flex items-center gap-2 min-w-0">
          <SparkleLogo className="w-5 h-5 text-primary shrink-0" />
          <span className="font-display text-[17px] tracking-tight truncate">TechNote</span>
        </span>
        {onClose && (
          <button onClick={onClose} aria-label="사이드바 닫기" className="btn-ghost md:hidden p-2 rounded-md">
            <X className="w-4 h-4" />
          </button>
        )}
        {onToggleCollapse && (
          <button
            onClick={onToggleCollapse}
            aria-label="사이드바 접기"
            title="사이드바 접기"
            className="btn-ghost hidden md:flex p-2 rounded-md"
          >
            <PanelLeftClose className="w-4 h-4" />
          </button>
        )}
      </div>

      <div role="tablist" aria-label="사이드바 영역" className="flex gap-1 px-3 pb-2 shrink-0">
        {tabs.map(({ id, label, icon: Icon, count }) => (
          <button
            key={id}
            role="tab"
            aria-selected={activeTab === id}
            onClick={() => setActiveTab(id)}
            className={`nav-item flex-1 flex items-center justify-center gap-1.5 py-1.5 text-[12.5px]`}
            data-active={activeTab === id}
          >
            <Icon className="w-3.5 h-3.5" />
            {label}
            {count > 0 && <span className="text-[11px] text-muted-foreground/60">{count}</span>}
          </button>
        ))}
      </div>

      {activeTab === "chat" ? <SessionList onNavigate={onClose} /> : <DocsPanel />}

      <div className="border-t border-border pt-2 mt-auto shrink-0">
        <UserMenu />
      </div>
    </div>
  );

  const collapsedRail = (
    <div className="flex flex-col h-full items-center py-3 gap-1">
      <button
        onClick={onToggleCollapse}
        aria-label="사이드바 펼치기"
        title="사이드바 펼치기"
        className="btn-ghost p-2 rounded-md"
      >
        <PanelLeftOpen className="w-5 h-5" />
      </button>
      <button
        onClick={handleQuickNewChat}
        aria-label="새 대화"
        title="새 대화"
        className="btn-ghost p-2 rounded-md"
      >
        <Plus className="w-5 h-5" />
      </button>
      <button
        onClick={() => {
          setActiveTab("chat");
          onToggleCollapse?.();
        }}
        aria-label={`대화 ${mySessionCount}개`}
        title={`대화 ${mySessionCount}개`}
        className="btn-ghost p-2 rounded-md"
      >
        <MessageSquare className="w-5 h-5" />
      </button>
      <button
        onClick={() => {
          setActiveTab("docs");
          onToggleCollapse?.();
        }}
        aria-label={`문서 ${readyDocCount}개`}
        title={`문서 ${readyDocCount}개`}
        className="btn-ghost p-2 rounded-md"
      >
        <FileText className="w-5 h-5" />
      </button>
      <div className="mt-auto">
        <UserMenu compact />
      </div>
    </div>
  );

  return (
    <>
      {isOpen && (
        <div
          className="overlay-scrim fixed inset-0 z-40 md:hidden animate-fade"
          onClick={onClose}
          aria-hidden="true"
        />
      )}

      <aside
        className={`sidebar hidden md:flex flex-col h-full z-50 transition-[width] duration-200 ${
          isCollapsed ? "w-[60px]" : "w-[264px]"
        }`}
      >
        {isCollapsed ? collapsedRail : content}
      </aside>

      <aside
        aria-hidden={!isOpen}
        inert={!isOpen}
        className={`sidebar fixed top-0 left-0 w-[86vw] max-w-[320px] h-full flex flex-col z-50 md:hidden
          transition-transform duration-200 ease-out ${isOpen ? "translate-x-0" : "-translate-x-full"}`}
      >
        {content}
      </aside>
    </>
  );
}
