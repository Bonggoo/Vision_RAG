"use client";

import React from "react";

/**
 * 정렬 토글 (최신순 / 이름순) (M5 분해) — 기존 renderDocsTab 내 정렬 버튼 그룹을 그대로 추출.
 */
export default function SortToggle({ sortBy, onChange }: {
  sortBy: "latest" | "name";
  onChange: (sortBy: "latest" | "name") => void;
}) {
  return (
    <div className="flex items-center gap-1 bg-accent/20 p-0.5 rounded-md border border-border/10 shrink-0">
      <button onClick={() => onChange("latest")} className={`text-[9px] px-1.5 py-0.5 rounded transition-all font-medium ${sortBy === "latest" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground/50 hover:text-foreground"}`}>최신순</button>
      <button onClick={() => onChange("name")} className={`text-[9px] px-1.5 py-0.5 rounded transition-all font-medium ${sortBy === "name" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground/50 hover:text-foreground"}`}>이름순</button>
    </div>
  );
}
