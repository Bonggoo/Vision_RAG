"use client";

import React from "react";
import { Search, X } from "lucide-react";

/** 문서 검색창 (이름·제조사·모델 통합 검색) */
export default function DocSearchBar({
  value,
  onChange,
  onClear,
}: {
  value: string;
  onChange: (value: string) => void;
  onClear: () => void;
}) {
  return (
    <div className="relative">
      <Search
        className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/60 pointer-events-none"
        aria-hidden="true"
      />
      <input
        type="search"
        aria-label="문서 검색"
        placeholder="문서 검색"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full pl-8 pr-8 py-1.5 text-base md:text-[12.5px] rounded-md
          bg-[var(--surface)] border border-border
          focus:outline-none focus:border-primary
          placeholder:text-muted-foreground/60
          [&::-webkit-search-cancel-button]:hidden"
      />
      {value && (
        <button
          onClick={onClear}
          aria-label="검색어 지우기"
          className="btn-ghost absolute right-1 top-1/2 -translate-y-1/2 p-1 rounded-md"
        >
          <X className="w-3 h-3" />
        </button>
      )}
    </div>
  );
}
