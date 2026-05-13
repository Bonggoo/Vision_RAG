import React, { useState, KeyboardEvent } from 'react';
import { SendHorizontal } from 'lucide-react';

interface ChatInputProps {
  onSubmit: (message: string) => void;
  disabled?: boolean;
}

export default function ChatInput({ onSubmit, disabled }: ChatInputProps) {
  const [text, setText] = useState('');

  const handleSubmit = () => {
    if (text.trim() && !disabled) {
      onSubmit(text.trim());
      setText('');
    }
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSubmit();
    }
  };

  return (
    <div className="p-4 bg-background border-t border-border">
      <div className="max-w-3xl mx-auto relative flex items-center">
        <textarea 
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={disabled}
          placeholder="매뉴얼에 대해 질문하세요... (예: 알람 E-102 원인이 뭐야?)"
          className="w-full bg-muted border border-border rounded-xl pl-4 pr-12 py-3 focus:outline-none focus:ring-2 focus:ring-primary/50 resize-none overflow-hidden h-14 min-h-[56px] max-h-32 text-sm md:text-base transition-all disabled:opacity-50"
          rows={1}
        />
        <button 
          onClick={handleSubmit}
          disabled={!text.trim() || disabled}
          className="absolute right-2 p-2 bg-primary text-primary-foreground rounded-lg hover:bg-primary/90 transition-colors disabled:opacity-50"
        >
          <SendHorizontal className="w-5 h-5" />
        </button>
      </div>
      <div className="text-center mt-2 text-xs text-muted-foreground">
        AI는 실수를 할 수 있습니다. 중요한 조치 전 매뉴얼 원본을 확인하세요.
      </div>
    </div>
  );
}
