"use client";

import React, { useState, KeyboardEvent, useRef, useEffect } from "react";
import { SendHorizontal, Sparkles, Camera, X, Square } from "lucide-react";
import { toast } from "@/store/useUIStore";

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
    if (textareaRef.current) {
      textareaRef.current.style.height = "auto";
      textareaRef.current.style.height = `${Math.min(textareaRef.current.scrollHeight, 160)}px`;
    }
  }, [text]);

  const handleImageChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (file.size > 10 * 1024 * 1024) {
      toast.warning("이미지 크기는 10MB 이하여야 합니다.");
      return;
    }

    const reader = new FileReader();
    reader.onloadend = () => {
      if (typeof reader.result === "string") {
        setImage(reader.result);
      }
    };
    reader.readAsDataURL(file);
    
    // 파일 input 초기화 (같은 파일 재업로드 가능하도록 함)
    if (imageInputRef.current) {
      imageInputRef.current.value = "";
    }
  };



  const handleSubmit = () => {
    if ((text.trim() || image) && !disabled) {
      onSubmit(text.trim(), image || undefined);
      setText("");
      setImage(null);
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.nativeEvent.isComposing) return;
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="chat-input-wrapper p-2.5 sm:p-3 md:p-4 border-t border-border/30">
      <div className="max-w-3xl lg:max-w-4xl mx-auto space-y-2">
        


        {/* 이미지 업로드 미리보기 프리뷰 바 */}
        {image && (
          <div className="flex justify-start items-center animate-slide-up">
            <div className="relative rounded-xl overflow-hidden border border-primary/20 bg-card/60 backdrop-blur-md p-1.5 flex items-center shadow-lg">
              <img
                src={image}
                alt="미리보기"
                className="w-12 h-12 object-cover rounded-lg"
              />
              <button
                onClick={() => setImage(null)}
                className="absolute -top-1 -right-1 w-5 h-5 rounded-full bg-black/70 hover:bg-black/90 flex items-center justify-center transition-colors cursor-pointer shadow-md"
              >
                <X className="w-3 h-3 text-white" />
              </button>
            </div>
          </div>
        )}

        <div className="chat-input relative flex items-end rounded-3xl p-1.5 transition-all border border-border/40 bg-accent/10 focus-within:border-primary/50 focus-within:shadow-[0_0_20px_rgba(139,92,246,0.15)] focus-within:bg-background/90 backdrop-blur-sm">
          {/* 숨겨진 이미지 파일 선택기 */}
          <input
            type="file"
            ref={imageInputRef}
            onChange={handleImageChange}
            accept="image/*"
            className="hidden"
          />

          {/* 카메라 촬영/앨범 선택 버튼 */}
          <button
            onClick={() => imageInputRef.current?.click()}
            disabled={disabled}
            className="relative z-30 btn-ghost p-3.5 sm:p-2.5 rounded-full flex-shrink-0 mr-0.5 hover:bg-primary/10 transition-colors cursor-pointer disabled:opacity-40"
            title="장비 알람 사진 찍기/첨부"
          >
            <Camera className="w-5 h-5 sm:w-4.5 sm:h-4.5 text-muted-foreground/75 hover:text-primary transition-colors" />
          </button>

          <textarea
            ref={textareaRef}
            value={text}
            onChange={(e) => setText(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={disabled}
            placeholder={image ? "알람 코드에 대해 질문해 보세요..." : "등록된 매뉴얼에 대해 질문하거나 사진을 첨부하세요..."}
            className="w-full bg-transparent pl-1 sm:pl-1.5 pr-12 py-2.5 text-base md:text-[14px] leading-relaxed
              resize-none overflow-hidden min-h-[44px] max-h-[160px]
              placeholder:text-muted-foreground/50 font-medium
              focus:outline-none
              disabled:opacity-40"
            rows={1}
          />
          {isStreaming ? (
            <button
              onClick={onStop}
              className="absolute right-2.5 bottom-2 p-2.5 rounded-full flex-shrink-0 transition-all bg-destructive/90 hover:bg-destructive shadow-lg shadow-destructive/20 animate-pulse"
              title="응답 중단"
            >
              <Square className="w-4 h-4 text-white fill-white" />
            </button>
          ) : (
            <button
              onClick={handleSubmit}
              disabled={(!text.trim() && !image) || disabled}
              className="absolute right-2.5 bottom-2 btn-primary p-2.5 rounded-full disabled:opacity-30 disabled:cursor-default disabled:transform-none disabled:shadow-none flex-shrink-0 transition-all shadow-md shadow-primary/20"
            >
              <SendHorizontal className="w-4 h-4" />
            </button>
          )}
        </div>
        <div className="flex items-center justify-center gap-1.5 mt-2 text-[10px] md:text-[11px] text-muted-foreground/35">
          <Sparkles className="w-3 h-3" />
          <span>AI는 실수를 할 수 있습니다. 중요한 조치 전 매뉴얼 원본을 확인하세요.</span>
        </div>
      </div>
    </div>
  );
}
