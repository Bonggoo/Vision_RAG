"use client";

import React, { useRef, useEffect, useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import ChatInput from "@/components/layout/ChatInput";
import ChatMessage from "@/components/chat/ChatMessage";
import ClarificationCard from "@/components/chat/ClarificationCard";
import WelcomeScreen from "@/components/chat/WelcomeScreen";
import LoginView from "@/components/layout/LoginView";
import { useChatStore } from "@/store/useChatStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useDocumentStore } from "@/store/useDocumentStore";
import { useChatStream } from "@/hooks/useChatStream";
import { useMounted } from "@/hooks/useMounted";

export default function Home() {
  const isMounted = useMounted();

  const { isAuthenticated, isSessionVerified, verifySession } = useAuthStore();
  const { sessions, activeSessionId, loadSessions, clarifications, clearClarification } =
    useChatStore();
  const fetchDocuments = useDocumentStore((s) => s.fetchDocuments);

  const { submit: handleChatSubmit, stop: handleStopStreaming } = useChatStream();

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  // 되묻기 카드는 그 질문을 한 세션에서만 보여야 한다 (세션 전환 시 남지 않도록)
  const clarificationState = activeSessionId ? clarifications[activeSessionId] ?? null : null;
  const scrollRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // 앱 시작 시 서버에 세션 유효성 검증 (iOS 쿠키 소멸 대응)
  useEffect(() => {
    if (isMounted) verifySession();
  }, [isMounted, verifySession]);

  // 로그인 + 세션 검증 완료 후 대화/문서 목록 로드
  // (문서 유무에 따라 웰컴 화면이 온보딩↔질문 모드로 갈리므로 함께 불러온다)
  useEffect(() => {
    if (isMounted && isAuthenticated && isSessionVerified) {
      loadSessions();
      fetchDocuments();
    }
  }, [isMounted, isAuthenticated, isSessionVerified, loadSessions, fetchDocuments]);

  // 자동 스크롤 — 조건부 return 보다 위에 있어야 함 (React Hooks 규칙)
  useEffect(() => {
    scrollRef.current?.scrollTo({
      top: scrollRef.current.scrollHeight,
      behavior: "smooth",
    });
  }, [activeSession?.messages, clarificationState]);

  if (!isMounted || !isSessionVerified) {
    return (
      <div className="flex h-screen-mobile items-center justify-center bg-background">
        <div className="flex flex-col items-center gap-3 text-muted-foreground">
          <span
            className="w-6 h-6 rounded-full border-2 border-border border-t-foreground animate-spin"
            aria-hidden="true"
          />
          <span className="text-[13px]">세션 확인 중</span>
        </div>
      </div>
    );
  }

  if (!isAuthenticated) return <LoginView />;

  /** 되묻기에서 문서 후보를 고르면, 마지막 질문에 장비 정보를 덧붙여 재전송한다 */
  const handleClarificationSelect = async (documentId: string) => {
    if (!activeSession) return;
    const lastUserMsg = [...activeSession.messages].reverse().find((m) => m.role === "user");
    if (!lastUserMsg) return;

    const selected = clarificationState?.candidates.find((c) => c.document_id === documentId);
    const question = selected
      ? `${lastUserMsg.content} (선택 장비: ${selected.manufacturer} ${selected.model_series})`
      : lastUserMsg.content;

    clearClarification(activeSession.id);
    await handleChatSubmit(question, lastUserMsg.image, documentId);
  };

  const handleClarificationQuestion = (question: string) => {
    if (activeSessionId) clearClarification(activeSessionId);
    handleChatSubmit(question);
  };

  const lastMessage = activeSession?.messages[activeSession.messages.length - 1];
  const isStreaming = !!lastMessage?.isStreaming;
  const isEmptyConversation = !activeSession || activeSession.messages.length === 0;

  return (
    <div className="flex h-screen-mobile overflow-hidden bg-background">
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed((v) => !v)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} />

        <main ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col">
          {isEmptyConversation ? (
            <WelcomeScreen onAskExample={handleChatSubmit} />
          ) : (
            <div className="w-full max-w-3xl lg:max-w-4xl mx-auto px-4 py-6 md:px-6 space-y-6">
              {activeSession.messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {clarificationState && (
                <ClarificationCard
                  state={clarificationState}
                  onSelectQuestion={handleClarificationQuestion}
                  onSelectDocument={handleClarificationSelect}
                />
              )}
            </div>
          )}
        </main>

        <ChatInput
          onSubmit={handleChatSubmit}
          disabled={isStreaming}
          isStreaming={isStreaming}
          onStop={handleStopStreaming}
        />
      </div>
    </div>
  );
}
