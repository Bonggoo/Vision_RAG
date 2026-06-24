import React from "react";

interface SparkleLogoProps {
  className?: string;
}

export default function SparkleLogo({ className = "w-8 h-8" }: SparkleLogoProps) {
  return (
    <svg
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="sparkle-logo-gradient" x1="15%" y1="15%" x2="85%" y2="85%">
          <stop offset="0%" stopColor="#3b82f6" />
          <stop offset="50%" stopColor="#8b5cf6" />
          <stop offset="100%" stopColor="#ec4899" />
        </linearGradient>
      </defs>
      <path
        d="M 50 0 C 50 38, 38 50, 0 50 C 38 50, 50 62, 50 100 C 50 62, 62 50, 100 50 C 62 50, 50 38, 50 0 Z"
        fill="url(#sparkle-logo-gradient)"
      />
    </svg>
  );
}
