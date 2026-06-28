"use client";

import React from "react";
import { Search, X } from "lucide-react";

/**
 * 문서 검색창 (M5 분해) — 기존 renderDocsTab 내 검색 input 마크업을 그대로 추출.
 */
export default function DocSearchBar({ value, onChange, onClear }: {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="relative">
      <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
      <input type="text" placeholder="검색 (이름, 제조사, 모델)..." value={value} onChange={(e) => onChange(e.target.value)} className="w-full pl-9 pr-8 py-1.5 text-[12px] rounded-full bg-accent/20 border border-border/20 focus:border-primary/50 focus:bg-accent/10 focus:outline-none transition-all placeholder-muted-foreground/40" />
      {value && <button onClick={onClear} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-accent/70 text-muted-foreground/50"><X className="w-2.5 h-2.5" /></button>}
    </div>
  );
}
