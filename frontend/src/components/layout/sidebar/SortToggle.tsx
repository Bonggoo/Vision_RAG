"use client";

import React from "react";

const OPTIONS = [
  { value: "latest", label: "최신순" },
  { value: "name", label: "이름순" },
] as const;

/** 문서 정렬 토글 (최신순 / 이름순) */
export default function SortToggle({
  sortBy,
  onChange,
}: {
  sortBy: "latest" | "name";
  onChange: (sortBy: "latest" | "name") => void;
}) {
  return (
    <div role="group" aria-label="문서 정렬" className="flex items-center gap-0.5 shrink-0">
      {OPTIONS.map(({ value, label }) => (
        <button
          key={value}
          onClick={() => onChange(value)}
          aria-pressed={sortBy === value}
          className={`text-[11px] px-1.5 py-0.5 rounded transition-colors ${
            sortBy === value
              ? "text-foreground font-medium"
              : "text-muted-foreground/60 hover:text-foreground"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
