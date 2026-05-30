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
    createSession,
    addMessage,
    appendAnswerChunk,
    appendReasoning,
    appendReference,
    finishStreaming,
    renameSession,
  } = useChatStore();

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [activeSession?.messages]);

  const handleChatSubmit = async (text: string, image?: string) => {
    let targetSessionId = activeSessionId;

    const defaultTitle = text.trim() 
      ? (text.length > 25 ? text.slice(0, 25) + "..." : text) 
      : "📸 알람 사진 질문";

    // 활성 세션이 없으면 자동으로 새 세션 생성
    if (!targetSessionId) {
      targetSessionId = createSession(defaultTitle);
    } else {
      // 기존 세션이 있고 첫 메시지인 경우 제목 변경
      const currentSession = sessions.find((s) => s.id === targetSessionId);
      if (currentSession && currentSession.messages.length === 0) {
        renameSession(targetSessionId, defaultTitle);
      }
    }

    if (!targetSessionId) return;

    addMessage(targetSessionId, { role: "user", content: text, image });
    addMessage(targetSessionId, {
      role: "assistant",
      content: "",
      isStreaming: true,
      reasoningSteps: [],
      references: [],
    });

    // 기존 요청 중단
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const currentSession = sessions.find((s) => s.id === targetSessionId);
      const prevMessages = currentSession
        ? currentSession.messages
            .filter((m) => !m.isStreaming && m.content)
            .slice(-6)
            .map((m) => ({ role: m.role, content: m.content.slice(0, 300) }))
        : [];

      let apiUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      if (apiUrl === "http://localhost:8000" && typeof window !== "undefined") {
        const hostname = window.location.hostname;
        if (hostname && hostname !== "localhost" && hostname !== "127.0.0.1" && !hostname.includes("vercel.app")) {
          apiUrl = `http://${hostname}:8000`;
        }
      }
      const response = await fetch(`${apiUrl}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          chat_history: prevMessages.length > 0 ? prevMessages : undefined,
          image: image || undefined,
        }),
        signal: controller.signal,
      });

      // 응답 상태 체크 (서버 오류 처리)
      if (!response.ok) {
        throw new Error(`서버 오류 (${response.status})`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let streamDone = false;

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
                  appendReasoning(targetSessionId, data.content);
                  break;
                case "reference":
                  appendReference(targetSessionId, {
                    pageNumber: data.page_number,
                    imageBase64: data.image_base64,
                  });
                  break;
                case "answer":
                  appendAnswerChunk(targetSessionId, data.content);
                  break;
                case "error":
                  appendAnswerChunk(targetSessionId, `\n\n> ⚠️ 오류: ${data.content}\n`);
                  break;
                case "done":
                  finishStreaming(targetSessionId);
                  streamDone = true;
                  break;
              }
            } catch {
              /* JSON parse error */
            }
          }
          // done 이벤트 수신 시 while 루프 탈출
          if (streamDone) break;
        }
      }
      // done 이벤트를 못 받고 스트림이 끝난 경우에만 finishStreaming 호출
      if (!streamDone) {
        finishStreaming(targetSessionId);
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // 사용자가 의도적으로 중단 → 에러 메시지 표시하지 않음
        console.log('사용자가 스트리밍을 중단했습니다.');
      } else {
        console.error(error);
        appendAnswerChunk(targetSessionId, `\n\n> ⚠️ ${error.message || '네트워크 오류가 발생했습니다.'}`);
      }
      finishStreaming(targetSessionId);
    } finally {
      abortControllerRef.current = null;
    }
  };

  /** 스트리밍 중단 핸들러 */
  const handleStopStreaming = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (activeSessionId) {
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
    <div className="flex h-screen-mobile overflow-hidden bg-background">
      <Sidebar isOpen={sidebarOpen} onClose={() => setSidebarOpen(false)} />

      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} />

        {/* Chat Area */}
        <main ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col relative">
          {!activeSession ? (
            /* ── 프리미엄 웰컴 화면 ── */
            <div className="flex-1 flex flex-col justify-start md:justify-center items-center px-6 py-8 md:py-0 relative overflow-y-auto scrollbar-thin">
              <div className="hero-gradient absolute inset-0 pointer-events-none" />
              <div className="relative z-10 text-center space-y-5 md:space-y-6 max-w-lg animate-slide-up my-auto">
                {/* 3D 플로팅 로고 및 야광 링 */}
                <div className="relative w-16 h-16 md:w-24 md:h-24 mx-auto mb-2 animate-float">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 blur-xl opacity-80" />
                  <div className="hero-icon w-16 h-16 md:w-24 md:h-24 rounded-2xl flex items-center justify-center border border-primary/20 bg-card/40 backdrop-blur-md shadow-2xl relative z-10">
                    <span className="text-3xl md:text-5xl drop-shadow-md">📑</span>
                  </div>
                </div>

                <div>
                  <h2 className="text-xl md:text-3xl font-extrabold tracking-tight mb-2 bg-gradient-to-r from-foreground via-foreground to-primary/80 bg-clip-text text-transparent">
                    Vision RAG
                  </h2>
                  <p className="text-[11px] md:text-sm text-muted-foreground/80 leading-relaxed max-w-md mx-auto px-2">
                    산업용 매뉴얼(PDF)을 AI가 인간처럼 목차를 읽고 원본 레이아웃 그대로 분석하여, 현장에서 활용 가능한 조치법을 제공합니다.
                  </p>
                </div>

                {/* 기능 카드 그리드 - 세련된 마이크로 호버 추가 */}
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-2.5 mt-4 md:mt-8 w-full">
                  {features.map((f, i) => (
                    <div
                      key={i}
                      className="glass-subtle rounded-xl p-3 md:p-4 text-left transition-all duration-300 hover:-translate-y-1 hover:shadow-lg hover:shadow-primary/5 hover:border-primary/40 group cursor-pointer"
                      style={{ animationDelay: `${i * 100}ms` }}
                    >
                      <div className="w-7 h-7 md:w-8 md:h-8 rounded-lg bg-primary/10 flex items-center justify-center mb-2 md:mb-3 group-hover:bg-primary/20 transition-colors">
                        <f.icon className="w-4 h-4 md:w-4.5 md:h-4.5 text-primary/70 group-hover:text-primary transition-colors" />
                      </div>
                      <p className="text-[11px] md:text-xs font-bold text-foreground/90 mb-0.5">{f.title}</p>
                      <p className="text-[10px] md:text-[11px] text-muted-foreground/70 leading-relaxed">{f.desc}</p>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ) : activeSession.messages.length === 0 ? (
            /* ── 빈 대화 ── */
            <div className="flex-1 flex flex-col justify-center items-center px-6 relative overflow-hidden">
              <div className="hero-gradient absolute inset-0 pointer-events-none" />
              <div className="relative z-10 text-center space-y-5 animate-slide-up">
                <div className="relative w-16 h-16 mx-auto mb-2 animate-float">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 blur-lg opacity-70" />
                  <div className="hero-icon w-16 h-16 rounded-2xl flex items-center justify-center border border-primary/15 bg-card/40 backdrop-blur-md shadow-xl relative z-10">
                    <span className="text-3xl">💬</span>
                  </div>
                </div>
                <div>
                  <h2 className="text-lg md:text-xl font-bold tracking-tight mb-1">
                    &apos;{activeSession.title}&apos; 대화 시작
                  </h2>
                  <p className="text-xs md:text-sm text-muted-foreground/70 max-w-sm mx-auto">
                    하단의 입력창에 관련 질문을 입력해 주세요.
                    <span className="block mt-2.5 text-primary/60 text-xs bg-primary/5 border border-primary/10 rounded-full px-3 py-1 font-medium inline-block">
                      💡 AI가 업로드된 문서 중 적합한 문서를 자동 판별합니다.
                    </span>
                  </p>
                </div>
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
            activeSession?.messages[activeSession.messages.length - 1]?.isStreaming
          }
          isStreaming={
            activeSession?.messages[activeSession.messages.length - 1]?.isStreaming
          }
          onStop={handleStopStreaming}
        />
      </div>
    </div>
  );
}
