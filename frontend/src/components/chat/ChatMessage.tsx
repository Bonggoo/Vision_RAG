"use client";

import React from "react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Message } from "@/store/useChatStore";
import ReasoningBlock from "./ReasoningBlock";
import ReferenceImages from "./ReferenceImages";
import StreamingIndicator from "./StreamingIndicator";
import CopyButton from "./CopyButton";

interface ChatMessageProps {
  message: Message;
}

/** 답변 본문 마크다운 타이포그래피 — 클래스가 길어 상수로 분리 */
const PROSE_CLASS = `prose dark:prose-invert prose-sm max-w-none break-words [overflow-wrap:anywhere]
  prose-headings:font-semibold prose-headings:tracking-tight prose-headings:text-foreground
  prose-h2:text-[16px] prose-h2:mt-6 prose-h2:mb-2
  prose-h3:text-[15px] prose-h3:mt-4 prose-h3:mb-1.5
  prose-p:text-[14.5px] prose-p:text-foreground prose-p:leading-[1.75]
  prose-li:text-[14.5px] prose-li:text-foreground prose-li:leading-[1.75] prose-li:my-0.5
  prose-strong:text-foreground prose-strong:font-semibold
  prose-blockquote:border-l-2 prose-blockquote:border-border-strong prose-blockquote:not-italic
  prose-blockquote:text-muted-foreground prose-blockquote:font-normal
  prose-code:bg-[var(--muted)] prose-code:text-foreground prose-code:px-1.5 prose-code:py-0.5
  prose-code:rounded prose-code:text-[13px] prose-code:font-mono-util prose-code:before:content-none prose-code:after:content-none
  prose-pre:bg-[var(--muted)] prose-pre:text-foreground prose-pre:border prose-pre:border-border
  prose-table:text-[13.5px] prose-table:my-4
  prose-th:text-foreground prose-th:bg-[var(--muted)] prose-th:px-3 prose-th:py-2 prose-th:font-medium
  prose-td:px-3 prose-td:py-2
  prose-a:text-primary prose-a:underline prose-a:underline-offset-2
  prose-hr:border-border`;

export default function ChatMessage({ message }: ChatMessageProps) {
  const isUser = message.role === "user";

  if (isUser) {
    return (
      <div className="flex justify-end animate-in">
        <div className="flex flex-col items-end gap-2 max-w-[85%]">
          {message.image && (
            // eslint-disable-next-line @next/next/no-img-element -- base64 data URL 이라 next/image 최적화 대상이 아님
            <img
              src={message.image}
              alt="사용자가 첨부한 장비 이미지"
              className="w-44 sm:w-52 h-auto max-h-40 object-contain rounded-xl border border-border"
            />
          )}
          {message.content && (
            <div className="chat-bubble-user px-4 py-2.5">
              <p className="whitespace-pre-wrap leading-relaxed text-[14.5px]">
                {message.content}
              </p>
            </div>
          )}
        </div>
      </div>
    );
  }

  // 비어 있는 assistant 메시지는 렌더하지 않는다 (되묻기 시 빈 영역 노출 방지)
  const hasContent =
    !!message.content?.trim() ||
    !!message.reasoningSteps?.length ||
    !!message.references?.length ||
    message.isStreaming;
  if (!hasContent) return null;

  return (
    <div className="animate-in group/message">
      <ReasoningBlock steps={message.reasoningSteps || []} />

      <ReferenceImages references={message.references || []} />

      {message.content ? (
        <>
          <div className={PROSE_CLASS}>
            <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
          </div>
          {message.isStreaming ? (
            <span
              aria-hidden="true"
              className="inline-block w-[2px] h-4 bg-foreground/60 ml-0.5 align-middle animate-pulse"
            />
          ) : (
            <div className="mt-2 -ml-1.5 flex items-center opacity-0 group-hover/message:opacity-100 focus-within:opacity-100 transition-opacity">
              <CopyButton text={message.content} />
            </div>
          )}
        </>
      ) : (
        message.isStreaming && <StreamingIndicator />
      )}
    </div>
  );
}
