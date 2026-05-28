"use client";

import React, { useState, KeyboardEvent, useRef, useEffect } from "react";
import { SendHorizontal, Sparkles } from "lucide-react";

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [text, setText] = useState("");
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  // textarea 높이 자동 조절
  useEffect(() => {
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [text]);

  const handleSubmit = () => {
    if (text.trim() && !disabled) {
      onSubmit(text.trim());
      setText("");
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-wrapper p-2.5 sm:p-3 md:p-4 border-t border-border/30">
      <div className="max-w-3xl lg:max-w-4xl mx-auto">
        <div className="chat-input relative flex items-end rounded-xl p-1.5 transition-all">
          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder="매뉴얼에 대해 질문하세요..."
            className="w-full bg-transparent pl-3 sm:pl-3.5 pr-12 py-2 sm:py-2.5 text-base md:text-[14px] leading-relaxed
              resize-none overflow-hidden min-h-[40px] max-h-[160px]
              placeholder:text-muted-foreground/40
              focus:outline-none
              disabled:opacity-40"
            rows={1}
          />
          <button
            onClick={handleSubmit}
            disabled={!text.trim() || disabled}
            className="absolute right-2 bottom-1.5 btn-primary p-2.5 rounded-lg disabled:opacity-30 disabled:cursor-default disabled:transform-none disabled:shadow-none flex-shrink-0 transition-all"
          >
            <SendHorizontal className="w-4 h-4" />
          </button>
        </div>
        <div className="flex items-center justify-center gap-1.5 mt-2.5 text-[11px] text-muted-foreground/35">
          <Sparkles className="w-3 h-3" />
          <span>AI는 실수를 할 수 있습니다. 중요한 조치 전 매뉴얼 원본을 확인하세요.</span>
        </div>
      </div>
    </div>
  );
}
