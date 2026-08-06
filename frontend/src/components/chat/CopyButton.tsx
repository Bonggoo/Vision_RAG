"use client";

import React, { useState } from "react";
import { Check, Copy } from "lucide-react";
import { toast } from "@/store/useUIStore";

/** 답변 본문을 클립보드로 복사. 성공 시 2초간 체크 아이콘으로 전환된다. */
export default function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = async () => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      toast.error("복사에 실패했습니다. 텍스트를 직접 선택해 주세요.");
    }
  };

  return (
    <button
      onClick={handleCopy}
      title="답변 복사"
      aria-label="답변 복사"
      className="btn-ghost p-1.5 rounded-md"
    >
      {copied ? (
        <Check className="w-3.5 h-3.5 text-[var(--success)]" />
      ) : (
        <Copy className="w-3.5 h-3.5" />
      )}
    </button>
  );
}
