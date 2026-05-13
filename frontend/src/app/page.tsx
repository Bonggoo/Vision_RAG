"use client";

import React, { useRef, useEffect } from 'react';
import Sidebar from "@/components/layout/Sidebar";
import Header from "@/components/layout/Header";
import ChatInput from "@/components/layout/ChatInput";
import { useChatStore } from "@/store/useChatStore";

export default function Home() {
  const { sessions, activeSessionId, addMessage, updateStreamingMessage } = useChatStore();
  const activeSession = sessions.find(s => s.id === activeSessionId);
  const scrollRef = useRef<HTMLDivElement>(null);

  // 자동 스크롤
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTo(0, scrollRef.current.scrollHeight);
    }
  }, [activeSession?.messages]);

  const handleChatSubmit = async (text: string) => {
    if (!activeSessionId || !activeSession) return;
    
    // 유저 메시지 추가
    addMessage(activeSessionId, { role: 'user', content: text });
    // 빈 AI 메시지 추가 (스트리밍 시작)
    addMessage(activeSessionId, { role: 'assistant', content: '', isStreaming: true });
    
    try {
      const apiUrl = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';
      const response = await fetch(`${apiUrl}/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          document_id: activeSession.documentId || "mock_doc_id", 
          message: text 
        }),
      });
      
      const reader = response.body?.getReader();
      const decoder = new TextDecoder('utf-8');
      
      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          
          const chunk = decoder.decode(value, { stream: true });
          const lines = chunk.split('\n');
          
          for (const line of lines) {
            if (line.startsWith('data: ')) {
              try {
                const data = JSON.parse(line.slice(6));
                if (data.type === 'chunk') {
                  updateStreamingMessage(activeSessionId, data.text, false);
                } else if (data.type === 'done') {
                  updateStreamingMessage(activeSessionId, '', true);
                } else if (data.type === 'info') {
                  updateStreamingMessage(activeSessionId, `[System: ${data.message}]\n\n`, false);
                }
              } catch (e) {
                console.error("JSON parse error for SSE data", e);
              }
            }
          }
        }
      }
      // 스트림이 완전히 끝나면 isDone=true 처리 (안전망)
      updateStreamingMessage(activeSessionId, '', true);
      
    } catch (error) {
      console.error(error);
      updateStreamingMessage(activeSessionId, '\n[오류가 발생했습니다]', true);
    }
  };

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col min-w-0">
        <Header />
        
        {/* Chat Area (Scrollable) */}
        <main ref={scrollRef} className="flex-1 overflow-y-auto p-4 flex flex-col scroll-smooth">
          {!activeSession ? (
            <div className="max-w-3xl w-full mx-auto flex-1 flex flex-col justify-center items-center text-center space-y-4 opacity-50 my-auto">
              <h2 className="text-2xl font-bold tracking-tight">Vision RAG에 오신 것을 환영합니다</h2>
              <p className="text-muted-foreground max-w-md">
                좌측 메뉴에서 문서를 선택하거나, 'PDF 매뉴얼 업로드' 버튼을 눌러 새 문서를 업로드한 후 질문을 시작하세요.
              </p>
            </div>
          ) : activeSession.messages.length === 0 ? (
            <div className="max-w-3xl w-full mx-auto flex-1 flex flex-col justify-center items-center text-center space-y-4 opacity-50 my-auto">
              <h2 className="text-xl font-bold tracking-tight">'{activeSession.title}' 대화 시작</h2>
              <p className="text-muted-foreground max-w-md">
                하단 입력창에 질문을 입력해 주세요.
              </p>
            </div>
          ) : (
            <div className="max-w-3xl w-full mx-auto space-y-6 pb-6">
              {activeSession.messages.map((msg) => (
                <div key={msg.id} className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
                  <div className={`max-w-[80%] rounded-2xl px-5 py-3.5 ${
                    msg.role === 'user' 
                      ? 'bg-primary text-primary-foreground rounded-tr-sm' 
                      : 'bg-card border border-border text-card-foreground rounded-tl-sm shadow-sm'
                  }`}>
                    <div className="whitespace-pre-wrap leading-relaxed text-[15px]">
                      {msg.content}
                    </div>
                    {msg.isStreaming && (
                      <span className="inline-block w-2 h-4 bg-primary/60 ml-1 animate-pulse" />
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </main>
        
        <ChatInput 
          onSubmit={handleChatSubmit} 
          disabled={!activeSessionId || activeSession?.messages[activeSession.messages.length - 1]?.isStreaming}
        />
      </div>
    </div>
  );
}
