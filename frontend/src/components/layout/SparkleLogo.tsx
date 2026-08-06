import React from "react";

interface SparkleLogoProps {
  className?: string;
}

/**
 * 앱 마크. 색은 `currentColor` 를 따르므로 부모의 text-* 클래스로 제어한다.
 * (기존 3색 그라디언트 + 드롭섀도우 제거 — 테마 토큰 하나로 통일)
 */
export default function SparkleLogo({ className = "w-8 h-8" }: SparkleLogoProps) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-hidden="true"
    >
      <path
        d="M 50 0 C 50 38, 38 50, 0 50 C 38 50, 50 62, 50 100 C 50 62, 62 50, 100 50 C 62 50, 50 38, 50 0 Z"
        fill="currentColor"
      />
    </svg>
  );
}
