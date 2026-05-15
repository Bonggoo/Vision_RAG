"use client";

import React, { useRef, useEffect, useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import ChatInput from "@/components/layout/ChatInput";
import ChatMessage from "@/components/chat/ChatMessage";
import { useChatStore } from "@/store/useChatStore";
import { Search, BookOpen, Cpu, Zap } from "lucide-react";

export default function Home() {
  const {
    sessions,
    activeSessionId,
    addMessage,
    appendAnswerChunk,
    appendReasoning,
    appendReference,
    finishStreaming,
    renameSession,
  } = useChatStore();

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [activeSession?.messages]);

  const handleChatSubmit = async (text: string) => {
    if (!activeSessionId || !activeSession) return;

    // 첨 메시지면 대화 제목 자동 생성
    if (activeSession.messages.length === 0) {
      const title = text.length > 25 ? text.slice(0, 25) + "..." : text;
      renameSession(activeSessionId, title);
    }

    addMessage(activeSessionId, { role: "user", content: text });
    addMessage(activeSessionId, {
      role: "assistant",
      content: "",
      isStreaming: true,
      reasoningSteps: [],
      references: [],
    });

    try {
      // 이전 대화 이력 구성 (최근 6턴만)
      const prevMessages = activeSession.messages
        .filter((m) => !m.isStreaming && m.content)
        .slice(-6)
        .map((m) => ({ role: m.role, content: m.content.slice(0, 300) }));

      const apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const response = await fetch(`${apiUrl}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          chat_history: prevMessages.length > 0 ? prevMessages : undefined,
        }),
      });

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";

      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6));
              switch (data.type) {
                case "reasoning":
                  appendReasoning(activeSessionId, data.content);
                  break;
                case "reference":
                  appendReference(activeSessionId, {
                    pageNumber: data.page_number,
                    imageBase64: data.image_base64,
                  });
                  break;
                case "answer":
                  appendAnswerChunk(activeSessionId, data.content);
                  break;
                case "error":
                  appendAnswerChunk(activeSessionId, `\n\n> ⚠️ 오류: ${data.content}\n`);
                  break;
                case "done":
                  finishStreaming(activeSessionId);
                  break;
              }
            } catch {
              /* JSON parse error */
            }
          }
        }
      }
      finishStreaming(activeSessionId);
    } catch (error) {
      console.error(error);
      appendAnswerChunk(activeSessionId, "\n\n> ⚠️ 네트워크 오류가 발생했습니다.");
      finishStreaming(activeSessionId);
    }
  };

  const features = [
    { icon: Search, title: "Agentic 탐색", desc: "AI가 목차를 분석해 정확한 페이지를 찾습니다" },
    { icon: BookOpen, title: "Vision 분석", desc: "도면과 표를 원본 그대로 분석합니다" },
    { icon: Cpu, title: "Vectorless", desc: "벡터 DB 없이 실시간으로 처리합니다" },
    { icon: Zap, title: "즉시 답변", desc: "구조화된 트러블슈팅 가이드를 제공합니다" },
  ];

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} />

        {/* Chat Area */}
        <main ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col">
          {!activeSession ? (
            /* ── 프리미엄 웰컴 화면 ── */
            <div className="flex-1 flex flex-col justify-center items-center px-6 relative">
              <div className="hero-gradient absolute inset-0 pointer-events-none" />
              <div className="relative z-10 text-center space-y-6 max-w-lg animate-slide-up">
                <div className="hero-icon w-16 h-16 md:w-20 md:h-20 rounded-2xl flex items-center justify-center mx-auto animate-float">
                  <span className="text-3xl md:text-4xl">📑</span>
                </div>
                <div>
                  <h2 className="text-xl md:text-2xl font-bold tracking-tight mb-2">
                    Vision RAG에 오신 것을 환영합니다
                  </h2>
                  <p className="text-sm text-muted-foreground/70 leading-relaxed max-w-md mx-auto">
                    산업용 매뉴얼을 AI가 분석하고, 현장에서 바로 활용 가능한 답변을 제공합니다.
                  </p>
                </div>

                {/* 기능 카드 그리드 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 sm:gap-3 mt-6 md:mt-8">
                  {features.map((f, i) => (
                    <div
                      key={i}
                      className="glass-subtle rounded-xl p-4 text-left hover:bg-accent/20 transition-colors group"
                      style={{ animationDelay: `${i * 80}ms` }}
                    >
                      <f.icon className="w-5 h-5 text-primary/70 mb-2 group-hover:text-primary transition-colors" />
                      <p className="text-xs font-semibold text-foreground/90 mb-0.5">{f.title}</p>
                      <p className="text-[11px] text-muted-foreground/60 leading-relaxed">{f.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : activeSession.messages.length === 0 ? (
            /* ── 빈 대화 ── */
            <div className="flex-1 flex flex-col justify-center items-center px-6 relative">
              <div className="hero-gradient absolute inset-0 pointer-events-none" />
              <div className="relative z-10 text-center space-y-4 animate-slide-up">
                <div className="hero-icon w-16 h-16 rounded-2xl flex items-center justify-center mx-auto">
                  <span className="text-3xl">💬</span>
                </div>
                <h2 className="text-xl font-bold tracking-tight">
                  &apos;{activeSession.title}&apos; 대화 시작
                </h2>
                <p className="text-sm text-muted-foreground/60 max-w-sm mx-auto">
                  하단 입력창에 질문을 입력해 주세요.
                  <span className="block mt-2 text-primary/50 text-xs">
                    AI가 업로드된 문서 중 가장 적합한 문서를 자동으로 찾아 답변합니다.
                  </span>
                </p>
              </div>
            </div>
          ) : (
            /* ── 메시지 목록 ── */
            <div className="max-w-3xl lg:max-w-4xl w-full mx-auto space-y-4 md:space-y-5 p-3 sm:p-4 md:p-6 pb-6">
              {activeSession.messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}
            </div>
          )}
        </main>

        <ChatInput
          onSubmit={handleChatSubmit}
          disabled={
            !activeSessionId ||
            activeSession?.messages[activeSession.messages.length - 1]?.isStreaming
          }
        />
      </div>
    </div>
  );
}
