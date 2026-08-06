"use client";

import React, { useState } from "react";
import { X } from "lucide-react";
import type { ReferenceImage } from "@/store/useChatStore";

/**
 * 답변 근거가 된 매뉴얼 페이지 썸네일. 클릭하면 크게 펼쳐진다.
 *
 * 펼침 상태는 이 컴포넌트가 단독으로 소유한다.
 * (이전에는 부모가 activePage 를 들고 effect 로 되돌려받는 양방향 구조였는데,
 *  실제로 외부에서 페이지를 지정하는 경로가 없어 중복 상태였다.)
 */
export default function ReferenceImages({ references }: { references: ReferenceImage[] }) {
  const [expandedIdx, setExpandedIdx] = useState<number | null>(null);

  if (!references || references.length === 0) return null;

  return (
    <div className="mb-4">
      <p className="text-[12px] text-muted-foreground mb-2">참조 페이지 {references.length}장</p>
      <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-thin">
        {references.map((ref, i) => {
          const isExpanded = expandedIdx === i;
          return (
            <button
              key={`${ref.pageNumber}-${i}`}
              onClick={() => setExpandedIdx(isExpanded ? null : i)}
              aria-label={`${ref.pageNumber}페이지 ${isExpanded ? "접기" : "펼치기"}`}
              aria-expanded={isExpanded}
              className="shrink-0 relative rounded-md overflow-hidden border border-border hover:border-border-strong transition-colors"
            >
              {/* eslint-disable-next-line @next/next/no-img-element -- base64 인라인 이미지라 next/image 최적화 대상이 아님 */}
              <img
                src={ref.imageBase64}
                alt={`매뉴얼 ${ref.pageNumber}페이지`}
                className={
                  isExpanded
                    ? "w-64 sm:w-80 lg:w-96 max-w-full h-auto"
                    : "w-16 h-22 sm:w-20 sm:h-28 object-cover"
                }
              />
              <span className="absolute bottom-1 right-1 bg-foreground/80 text-background text-[10px] px-1.5 py-0.5 rounded font-mono-util">
                p.{ref.pageNumber}
              </span>
              {isExpanded && (
                <span className="absolute top-1.5 right-1.5 w-5 h-5 rounded-full bg-foreground/80 text-background flex items-center justify-center">
                  <X className="w-3 h-3" />
                </span>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}
