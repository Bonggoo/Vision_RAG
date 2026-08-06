"use client";

import React, { useState, KeyboardEvent, useRef, useEffect } from "react";
import { ArrowUp, ImagePlus, X, Square } from "lucide-react";
import { toast } from "@/store/useUIStore";

const MAX_IMAGE_BYTES = 10 * 1024 * 1024;
const MAX_TEXTAREA_HEIGHT = 200;

interface ChatInputProps {
  onSubmit: (message: string, image?: string) => void;
  disabled?: boolean;
  isStreaming?: boolean;
  onStop?: () => void;
}

export default function ChatInput({ onSubmit, disabled, isStreaming, onStop }: ChatInputProps) {
  const [text, setText] = useState("");
  const [image, setImage] = useState<string | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const imageInputRef = useRef<HTMLInputElement>(null);

  // textarea 높이 자동 조절
  useEffect(() => {
    const el = textareaRef.current;
    if (!el) return;
    el.style.height = "auto";
    el.style.height = `${Math.min(el.scrollHeight, MAX_TEXTAREA_HEIGHT)}px`;
  }, [text]);

  const readImageFile = (file: File) => {
    if (!file.type.startsWith("image/")) return;
    if (file.size > MAX_IMAGE_BYTES) {
      toast.warning("이미지 크기는 10MB 이하여야 합니다.");
      return;
    }
    const reader = new FileReader();
    reader.onloadend = () => {
      if (typeof reader.result === "string") setImage(reader.result);
    };
    reader.onerror = () => toast.error("이미지를 읽지 못했습니다.");
    reader.readAsDataURL(file);
  };

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) readImageFile(file);
    // 같은 파일 재선택이 가능하도록 초기화
    if (imageInputRef.current) imageInputRef.current.value = "";
  };

  // 클립보드 이미지 붙여넣기 지원 (현장에서 캡처 → Ctrl+V 흐름)
  const handlePaste = (e: React.ClipboardEvent<HTMLTextAreaElement>) => {
    const file = Array.from(e.clipboardData.files)[0];
    if (file?.type.startsWith("image/")) {
      e.preventDefault();
      readImageFile(file);
    }
  };

  const canSubmit = (text.trim().length > 0 || !!image) && !disabled;

  const handleSubmit = () => {
    if (!canSubmit) return;
    onSubmit(text.trim(), image || undefined);
    setText("");
    setImage(null);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-wrapper px-3 pb-3 pt-1 md:px-4 md:pb-4">
      <div className="max-w-3xl lg:max-w-4xl mx-auto">
        <div className="chat-input flex flex-col gap-1 p-2">
          {/* 첨부 이미지 미리보기 */}
          {image && (
            <div className="flex px-1 pt-1">
              <div className="relative">
                {/* eslint-disable-next-line @next/next/no-img-element -- base64 data URL 이라 next/image 최적화 대상이 아님 */}
                <img
                  src={image}
                  alt="첨부한 이미지 미리보기"
                  className="w-14 h-14 object-cover rounded-md border border-border"
                />
                <button
                  onClick={() => setImage(null)}
                  aria-label="첨부 이미지 제거"
                  className="absolute -top-1.5 -right-1.5 w-5 h-5 rounded-full bg-foreground text-background flex items-center justify-center"
                >
                  <X className="w-3 h-3" />
                </button>
              </div>
            </div>
          )}

          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            onPaste={handlePaste}
            disabled={disabled}
            aria-label="질문 입력"
            placeholder={image ? "이 사진에 대해 질문해 보세요" : "매뉴얼에 대해 무엇이든 물어보세요"}
            className="w-full bg-transparent px-2 py-2 text-base md:text-[15px] leading-relaxed
              resize-none overflow-y-auto min-h-[40px]
              placeholder:text-muted-foreground/60
              focus:outline-none disabled:opacity-50"
            rows={1}
          />

          <div className="flex items-center justify-between gap-2">
            <input
              type="file"
              ref={imageInputRef}
              onChange={handleImageChange}
              accept="image/*"
              className="hidden"
            />
            <button
              onClick={() => imageInputRef.current?.click()}
              disabled={disabled}
              className="btn-ghost p-2 rounded-md disabled:opacity-40"
              title="장비 사진 첨부"
              aria-label="장비 사진 첨부"
            >
              <ImagePlus className="w-[18px] h-[18px]" />
            </button>

            {isStreaming ? (
              <button
                onClick={onStop}
                aria-label="응답 중단"
                title="응답 중단"
                className="btn-secondary w-8 h-8 rounded-md flex items-center justify-center"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
              </button>
            ) : (
              <button
                onClick={handleSubmit}
                disabled={!canSubmit}
                aria-label="메시지 전송"
                className="btn-primary w-8 h-8 rounded-md flex items-center justify-center"
              >
                <ArrowUp className="w-[18px] h-[18px]" />
              </button>
            )}
          </div>
        </div>

        <p className="mt-2 text-center text-[11px] text-muted-foreground/70">
          AI는 실수할 수 있습니다. 중요한 조치 전 매뉴얼 원본을 확인하세요.
        </p>
      </div>
    </div>
  );
}
