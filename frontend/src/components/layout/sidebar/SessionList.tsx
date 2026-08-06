"use client";

import React from "react";
import { Plus, Trash2 } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useAuthStore } from "@/store/useAuthStore";
import { toast, confirmDialog } from "@/store/useUIStore";

interface SessionListProps {
  /** 모바일에서 항목 선택 시 사이드바를 닫기 위한 콜백 */
  onNavigate?: () => void;
}

/** 사이드바 "대화" 탭 — 새 대화 시작 + 내 대화 목록 */
export default function SessionList({ onNavigate }: SessionListProps) {
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession, loadConversation } =
    useChatStore();
  const user = useAuthStore((s) => s.user);

  // ownerEmail 이 없는 항목은 로그인 이전 로컬 세션이므로 함께 노출한다
  const mySessions = sessions.filter((s) => s.ownerEmail === user?.email || !s.ownerEmail);

  const handleNewChat = async () => {
    try {
      // 비어 있는 세션이 이미 있으면 재사용 (빈 대화가 쌓이는 것 방지)
      const empty = mySessions.find((s) => s.messages.length === 0);
      if (empty) {
        setActiveSession(empty.id);
      } else {
        setActiveSession(await createSession("새로운 대화"));
      }
      onNavigate?.();
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "대화를 만들지 못했습니다.");
    }
  };

  const handleDelete = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    const ok = await confirmDialog({
      title: "대화 삭제",
      description: "이 대화를 삭제할까요?",
      confirmText: "삭제",
      danger: true,
    });
    if (!ok) return;
    try {
      await deleteSession(sessionId);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "대화를 삭제하지 못했습니다.");
    }
  };

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-3 py-2">
        <button
          onClick={handleNewChat}
          className="btn-secondary w-full flex items-center gap-2 py-2 px-3 rounded-lg text-[13.5px]"
        >
          <Plus className="w-4 h-4 shrink-0" />
          새 대화
        </button>
      </div>

      <nav aria-label="대화 목록" className="flex-1 overflow-y-auto px-2 pb-2 scrollbar-thin">
        {mySessions.length === 0 ? (
          <p className="px-3 py-6 text-center text-[12px] text-muted-foreground">
            대화 기록이 없습니다.
          </p>
        ) : (
          <ul className="space-y-0.5">
            {mySessions.map((session) => (
              <li key={session.id}>
                <div
                  className="nav-item group flex items-center gap-1"
                  data-active={activeSessionId === session.id}
                >
                  <button
                    onClick={() => {
                      loadConversation(session.id);
                      onNavigate?.();
                    }}
                    aria-current={activeSessionId === session.id ? "page" : undefined}
                    className="flex-1 min-w-0 text-left px-2.5 py-2 text-[13px] truncate"
                  >
                    {session.title}
                  </button>
                  <button
                    onClick={(e) => handleDelete(e, session.id)}
                    aria-label={`${session.title} 대화 삭제`}
                    className="btn-ghost p-1.5 mr-1 rounded-md shrink-0 hover:text-destructive md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                </div>
              </li>
            ))}
          </ul>
        )}
      </nav>
    </div>
  );
}
