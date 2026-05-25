"use client";

import React, { useState, useEffect } from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import {
  ChevronDown,
  ChevronRight,
  FileImage,
  Bot,
  User,
  Brain,
  X,
} from "lucide-react";
import type { Message, ReferenceImage } from "@/store/useChatStore";

interface ChatMessageProps {
  message: Message;
}

/** 추론 과정 블록 */
function ReasoningBlock({ steps }: { steps: string[] }) {
  const [isOpen, setIsOpen] = useState(false);
  if (!steps || steps.length === 0) return null;

  return (
    <div className="mb-3">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className="group flex items-center gap-2 text-xs font-medium text-muted-foreground hover:text-primary/80 transition-colors"
      >
        <div className="flex items-center gap-1 bg-primary/8 hover:bg-primary/12 px-2.5 py-1 rounded-full transition-colors">
          {isOpen ? <ChevronDown className="w-3 h-3" /> : <ChevronRight className="w-3 h-3" />}
          <Brain className="w-3 h-3 text-primary/70" />
          <span>추론 과정 ({steps.length}단계)</span>
        </div>
      </button>

      {isOpen && (
        <div className="mt-2.5 ml-1 pl-3 border-l-2 border-primary/15 space-y-2 animate-in">
          {steps.map((step, i) => (
            <div key={i} className="flex gap-2 items-start">
              <span className="text-[10px] font-mono text-primary/50 bg-primary/5 w-4 h-4 rounded flex items-center justify-center flex-shrink-0 mt-0.5">
                {i + 1}
              </span>
              <p className="text-xs text-muted-foreground/80 leading-relaxed">{step}</p>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

/** 참조 이미지 */
function ReferenceImages({ references }: { references: ReferenceImage[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);
  if (!references || references.length === 0) return null;

  return (
    <div className="mb-4">
      <div className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground mb-2.5">
        <FileImage className="w-3.5 h-3.5 text-primary/60" />
        <span>참조 페이지 ({references.length}장)</span>
      </div>
      <div className="flex gap-2 overflow-x-auto pb-2 scrollbar-thin">
        {references.map((ref, i) => (
          <button
            key={i}
            onClick={() => setExpandedIdx(expandedIdx === i ? null : i)}
            className="flex-shrink-0 group relative rounded-lg overflow-hidden"
          >
            <img
              src={ref.imageBase64}
              alt={`페이지 ${ref.pageNumber}`}
              className={`transition-all duration-300 ${
                expandedIdx === i
                  ? "w-64 sm:w-80 lg:w-96 h-auto rounded-lg shadow-xl"
                  : "w-16 h-22 sm:w-20 sm:h-28 object-cover rounded-lg border border-border/50 hover:border-primary/40 hover:shadow-lg hover:scale-105"
              }`}
            />
            <span className="absolute bottom-1.5 right-1.5 bg-black/70 text-white text-[9px] px-1.5 py-0.5 rounded-md font-mono backdrop-blur-sm">
              p.{ref.pageNumber}
            </span>
            {expandedIdx === i && (
              <div className="absolute top-2 right-2 w-6 h-6 rounded-full bg-black/60 flex items-center justify-center backdrop-blur-sm">
                <X className="w-3 h-3 text-white" />
              </div>
            )}
          </button>
        ))}
      </div>
    </div>
  );
}

/** 스트리밍 대기 표시 (경과 시간 포함) */
function StreamingIndicator() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const interval = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-3 py-1">
      <div className="flex gap-1">
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 bg-primary/60 rounded-full animate-bounce [animation-delay:300ms]" />
      </div>
      <span className="text-xs text-muted-foreground/60">
        분석 중...
        <span className="ml-1 font-mono text-primary/50">({elapsed}s)</span>
      </span>
    </div>
  );
}

/** 개별 채팅 메시지 */
export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-slide-up">
        <div className="flex items-end gap-2.5 max-w-[88%] sm:max-w-[80%]">
          {/* 유저 말풍선 */}
          <div className="chat-bubble-user rounded-2xl rounded-tr-sm px-4 py-3 shadow-md hover:shadow-lg transition-shadow duration-350">
            <p className="whitespace-pre-wrap leading-relaxed text-[13.5px] text-white font-medium">
              {message.content}
            </p>
          </div>
          {/* 유저 아바타 */}
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500/20 to-indigo-500/20 flex items-center justify-center flex-shrink-0 border border-primary/20 shadow-sm">
            <User className="w-4 h-4 text-primary" />
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="flex justify-start animate-slide-up">
      <div className="flex items-start gap-2.5 max-w-[92%] sm:max-w-[85%] lg:max-w-[80%]">
        {/* AI 아바타 - 라이트/다크 다이나믹 컬러 */}
        <div className="w-8 h-8 rounded-full bg-gradient-to-br from-violet-500/10 to-indigo-600/10 dark:from-violet-500/20 dark:to-indigo-500/20 flex items-center justify-center flex-shrink-0 mt-0.5 border border-violet-500/20 dark:border-violet-500/30 shadow-sm">
          <Bot className="w-4 h-4 text-violet-600 dark:text-violet-400" />
        </div>
        
        {/* AI 말풍선 (글래스모피즘) */}
        <div className="chat-bubble-ai rounded-2xl rounded-tl-sm px-4 sm:px-5 py-3.5 sm:py-4 min-w-0">
          {/* 추론 과정 */}
          <ReasoningBlock steps={message.reasoningSteps || []} />

          {/* 참조 이미지 */}
          <ReferenceImages references={message.references || []} />

          {/* 답변 본문 (라이트/다크 가독성 분기) */}
          {message.content ? (
            <div className="prose dark:prose-invert prose-sm max-w-none leading-relaxed
              prose-headings:text-foreground prose-headings:font-bold prose-headings:tracking-tight
              prose-h2:text-[14.5px] prose-h2:mt-5 prose-h2:mb-2 prose-h2:pb-1.5 prose-h2:border-b prose-h2:border-border/30
              prose-h3:text-[13px] prose-h3:mt-4 prose-h3:mb-1.5 prose-h3:text-foreground/90
              prose-p:text-[13px] prose-p:text-foreground/85 prose-p:leading-[1.8]
              prose-li:text-[13px] prose-li:text-foreground/85 prose-li:leading-[1.8]
              prose-strong:text-foreground prose-strong:font-bold
              prose-blockquote:border-l-4 prose-blockquote:border-primary/40 prose-blockquote:bg-primary/5 prose-blockquote:rounded-r-lg prose-blockquote:py-2.5 prose-blockquote:pl-4 prose-blockquote:pr-3
              prose-blockquote:text-muted-foreground prose-blockquote:text-xs prose-blockquote:not-italic
              prose-code:text-violet-600 dark:prose-code:text-violet-300 prose-code:bg-violet-500/5 dark:prose-code:bg-violet-500/10 prose-code:px-1.5 prose-code:py-0.5 prose-code:rounded prose-code:text-xs prose-code:font-mono
              prose-table:text-xs prose-table:my-4
              prose-th:text-foreground/90 prose-th:border-border/40 prose-th:bg-secondary/60 prose-th:px-3 prose-th:py-2 prose-th:font-semibold
              prose-td:border-border/20 prose-td:px-3 prose-td:py-2
              prose-a:text-primary prose-a:no-underline hover:prose-a:underline
              prose-hr:border-border/20"
            >
              <ReactMarkdown remarkPlugins={[remarkGfm]}>
                {message.content}
              </ReactMarkdown>
            </div>
          ) : message.isStreaming ? (
            <StreamingIndicator />
          ) : null}

          {/* 스트리밍 커서 */}
          {message.isStreaming && message.content && (
            <span className="inline-block w-0.5 h-4 bg-primary/70 ml-0.5 animate-pulse rounded-full" />
          )}
        </div>
      </div>
    </div>
  );
}

