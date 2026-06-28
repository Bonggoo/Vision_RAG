"use client";

import React, { useRef, useEffect, useState } from "react";
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import ChatInput from "@/components/layout/ChatInput";
import ChatMessage from "@/components/chat/ChatMessage";
import LoginView from "@/components/layout/LoginView";
import SparkleLogo from "@/components/layout/SparkleLogo";
import { useChatStore } from "@/store/useChatStore";
import { useAuthStore } from "@/store/useAuthStore";
import { useChatStream } from "@/hooks/useChatStream";
import { MessageCircleQuestion } from "lucide-react";

export default function Home() {
  // 💡 Hydration 에러 방지: 마운트 상태 추가
  const [isMounted, setIsMounted] = useState(false);

  const { isAuthenticated, isSessionVerified, verifySession, token } = useAuthStore();
  const {
    sessions,
    activeSessionId,
    loadSessions,
    clarificationState,
    clearClarification,
  } = useChatStore();

  const { submit: handleChatSubmit, stop: handleStopStreaming } = useChatStream();

  const activeSession = sessions.find((s) => s.id === activeSessionId);
  const scrollRef = useRef<HTMLDivElement>(null);
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [sidebarCollapsed, setSidebarCollapsed] = useState(false);

  // 💡 브라우저 마운트 완료 후 렌더링
  useEffect(() => {
    setIsMounted(true);
  }, []);

  // 💡 앱 시작 시 서버에 세션 유효성 검증 (iOS 쿠키 소멸 대응)
  useEffect(() => {
    if (isMounted) {
      verifySession();
    }
  }, [isMounted, verifySession]);

  // 💡 로그인 + 세션 검증 완료 후 대화 세션 목록 로드
  useEffect(() => {
    if (isMounted && isAuthenticated && isSessionVerified) {
      loadSessions();
    }
  }, [isMounted, isAuthenticated, isSessionVerified, loadSessions]);

  // 💡 자동 스크롤 - 반드시 조건부 return 전에 선언 (React Hooks 규칙)
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo({ top: scrollRef.current.scrollHeight, behavior: "smooth" });
    }
  }, [activeSession?.messages, clarificationState]);

  // 마운트 전이거나 세션 검증 중에는 로딩 표시
  if (!isMounted || !isSessionVerified) {
    return (
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        height: "100dvh",
        background: "var(--bg-primary, #0a0a0a)",
      }}>
        <div style={{
          display: "flex",
          flexDirection: "column",
          alignItems: "center",
          gap: "16px",
          color: "var(--text-secondary, #888)",
        }}>
          <div style={{
            width: "32px",
            height: "32px",
            border: "3px solid rgba(255,255,255,0.1)",
            borderTopColor: "rgba(255,255,255,0.6)",
            borderRadius: "50%",
            animation: "spin 0.8s linear infinite",
          }} />
          <span style={{ fontSize: "14px" }}>세션 확인 중...</span>
          <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
        </div>
      </div>
    );
  }

  // 💡 비로그인 유저는 로그인 화면을 반환
  if (!isAuthenticated) {
    return (
      <div className="animate-fade">
        <LoginView />
      </div>
    );
  }

  /** 되묻기 후보 선택 핸들러 */
  const handleClarificationSelect = async (documentId: string) => {
    if (!activeSessionId || !activeSession) return;
    
    // 마지막 user 메시지 찾기
    const lastUserMsg = [...activeSession.messages]
      .reverse()
      .find((m) => m.role === "user");
    
    if (!lastUserMsg) return;

    // 선택된 후보의 장비 정보 추출
    const selectedCand = clarificationState?.candidates.find(
      (c) => c.document_id === documentId
    );
    
    // 질문 뒤에 장비 모델명 정보 덧붙임
    const rewrittenQuestion = selectedCand
      ? `${lastUserMsg.content} (선택 장비: ${selectedCand.manufacturer} ${selectedCand.model_series})`
      : lastUserMsg.content;

    clearClarification();
    
    // 선택된 document_id와 함께 재전송
    await handleChatSubmit(rewrittenQuestion, lastUserMsg.image, documentId);
  };

  const examplePrompts = [
    { emoji: "🚨", text: "서보 2051 알람 설명" },
    { emoji: "🔋", text: "배터리 교체 주기와 방법" },
    { emoji: "⚙️", text: "원점 복귀(Homing) 설정 절차" },
    { emoji: "🔌", text: "통신 에러 타임아웃 해결법" },
  ];

  return (
    <div className="flex h-screen-mobile overflow-hidden bg-background animate-fade" style={{ animationDuration: '0.5s' }}>
      <Sidebar
        isOpen={sidebarOpen}
        onClose={() => setSidebarOpen(false)}
        isCollapsed={sidebarCollapsed}
        onToggleCollapse={() => setSidebarCollapsed(!sidebarCollapsed)}
      />

      <div className="flex-1 flex flex-col min-w-0">
        <Header onMenuClick={() => setSidebarOpen(true)} />

        {/* Chat Area */}
        <main ref={scrollRef} className="flex-1 overflow-y-auto flex flex-col relative">
          {!activeSession || activeSession.messages.length === 0 ? (
            /* ── 프리미엄 웰컴 화면 ── */
            <div className="flex-1 flex flex-col justify-start md:justify-center items-center px-6 py-8 md:py-0 relative overflow-y-auto scrollbar-thin">
              <div className="hero-gradient absolute inset-0 pointer-events-none" />
              <div className="relative z-10 text-center space-y-5 md:space-y-6 max-w-lg animate-slide-up my-auto">
                {/* 3D 플로팅 로고 및 야광 링 */}
                <div className="relative w-16 h-16 md:w-24 md:h-24 mx-auto mb-2 animate-float">
                  <div className="absolute inset-0 rounded-2xl bg-gradient-to-br from-violet-500/20 to-indigo-500/20 blur-xl opacity-80" />
                  <div className="hero-icon w-16 h-16 md:w-24 md:h-24 rounded-2xl flex items-center justify-center border border-white/60 dark:border-primary/20 bg-white/80 dark:bg-card/40 backdrop-blur-md shadow-[0_12px_40px_rgba(115,73,170,0.06)] dark:shadow-2xl relative z-10">
                    <SparkleLogo className="w-10 h-10 md:w-16 md:h-16 filter drop-shadow-[0_4px_12px_rgba(115,73,170,0.12)] dark:drop-shadow-[0_4px_16px_rgba(139,92,246,0.45)]" />
                  </div>
                </div>

                <div>
                  <h2 className="text-[22px] md:text-[32px] font-extrabold font-display tracking-tight mb-2 bg-gradient-to-r from-foreground via-foreground to-primary/80 bg-clip-text text-transparent">
                    TechNote
                  </h2>
                  <p className="text-[12px] md:text-[14px] text-muted-foreground/80 leading-relaxed max-w-md mx-auto px-2 font-medium">
                    산업용 매뉴얼을 AI가 분석하여 현장에서 바로 활용 가능한 답변을 제공합니다.
                  </p>
                </div>

                {/* 💡 예시 질문 카드 */}
                <div className="w-full mt-4 md:mt-8">
                  <div className="flex items-center justify-center gap-1.5 mb-4 text-[11px] text-muted-foreground/60 font-semibold uppercase tracking-widest">
                    <MessageCircleQuestion className="w-3.5 h-3.5" />
                    <span>이런 질문을 해보세요</span>
                  </div>
                  <div className="grid grid-cols-2 gap-3 w-full">
                    {examplePrompts.map((p, i) => (
                      <button
                        key={i}
                        onClick={() => handleChatSubmit(p.text)}
                        className="glass-subtle rounded-2xl px-4 py-3.5 text-left transition-all duration-300
                          hover:-translate-y-1 hover:shadow-lg hover:shadow-primary/10 border border-border/40 hover:border-primary/40
                          active:scale-[0.98] cursor-pointer group flex flex-col gap-1.5"
                      >
                        <span className="text-lg block">{p.emoji}</span>
                        <span className="text-[12px] md:text-[13px] font-medium text-muted-foreground/90 group-hover:text-foreground transition-colors leading-snug">
                          {p.text}
                        </span>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
            </div>
          ) : (
            /* ── 메시지 목록 ── */
            <div className="max-w-3xl lg:max-w-4xl w-full mx-auto space-y-4 md:space-y-6 p-3 sm:p-4 md:p-6 pb-6">
              {activeSession.messages.map((msg) => (
                <ChatMessage key={msg.id} message={msg} />
              ))}

              {/* 되묻기 UI — 보강 질문 + 문서 후보 */}
              {clarificationState && (
                <div className="flex flex-col gap-4 p-5 md:p-6 rounded-3xl border border-primary/20 bg-card/60 backdrop-blur-xl animate-slide-up shadow-xl relative overflow-hidden">
                  <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-primary/40 via-blue-500/40 to-primary/40" />
                  <div className="text-[13px] md:text-[14px] font-bold text-foreground/90 flex items-center gap-2.5">
                    <span className="text-lg">🤖</span>
                    <span>{clarificationState.content}</span>
                  </div>

                  {/* 보강 질문 카드 */}
                  {clarificationState.suggested_questions && clarificationState.suggested_questions.length > 0 && (
                    <div className="flex flex-col gap-2 mt-1">
                      <div className="text-[11px] text-primary/80 font-semibold uppercase tracking-widest flex items-center gap-1.5 px-1 mb-1">
                        <span>✨</span>
                        <span>추천 질문</span>
                      </div>
                      {clarificationState.suggested_questions.map((q, idx) => (
                        <button
                          key={idx}
                          onClick={() => {
                            clearClarification();
                            handleChatSubmit(q);
                          }}
                          className="flex items-center gap-3 text-left p-3.5 md:p-4 rounded-2xl border border-primary/20 bg-background/50 hover:bg-primary/10 hover:border-primary/40 transition-all cursor-pointer group shadow-sm"
                        >
                          <span className="text-sm text-primary/60 group-hover:text-primary transition-colors shrink-0">→</span>
                          <span className="text-[13px] md:text-[14px] font-medium text-foreground/90 group-hover:text-foreground transition-colors">
                            {q}
                          </span>
                        </button>
                      ))}
                    </div>
                  )}

                  {/* 문서 후보 카드 */}
                  {clarificationState.candidates.length > 0 && (
                    <div className="flex flex-col gap-2 mt-2">
                      {clarificationState.suggested_questions && clarificationState.suggested_questions.length > 0 && (
                        <div className="text-[11px] text-muted-foreground/60 font-semibold uppercase tracking-widest flex items-center gap-1.5 px-1 mt-2 mb-1">
                          <span>📂</span>
                          <span>직접 문서 선택</span>
                        </div>
                      )}
                      {clarificationState.candidates.map((cand) => (
                        <button
                          key={cand.document_id}
                          onClick={() => handleClarificationSelect(cand.document_id)}
                          className="flex items-center justify-between text-left p-4 rounded-2xl border border-border/60 bg-background/50 hover:bg-primary/5 hover:border-primary/40 transition-all cursor-pointer group shadow-sm"
                        >
                          <div className="flex-1 pr-4 min-w-0">
                            <div className="text-[13px] md:text-[14px] font-bold text-foreground group-hover:text-primary transition-colors truncate font-display">
                              {cand.manufacturer} {cand.model_series}
                            </div>
                            <div className="text-[11px] md:text-[12px] text-muted-foreground/80 mt-1 truncate">
                              {cand.title}
                            </div>
                          </div>
                          <div className="text-[11px] font-bold text-primary/80 bg-primary/10 px-2.5 py-1 rounded-full shrink-0">
                            {(cand.confidence * 100).toFixed(0)}% 일치
                          </div>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              )}
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
