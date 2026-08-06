"use client";

import React, { useEffect, useState } from "react";

/** 첫 토큰 도착 전 대기 표시. 10초가 넘어가면 경과 시간을 함께 보여준다. */
export default function StreamingIndicator() {
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    const started = Date.now();
    const interval = setInterval(
      () => setElapsed(Math.floor((Date.now() - started) / 1000)),
      1000
    );
    return () => clearInterval(interval);
  }, []);

  return (
    <div className="flex items-center gap-2.5 py-0.5" role="status" aria-live="polite">
      <span className="flex gap-1" aria-hidden="true">
        <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:0ms]" />
        <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:150ms]" />
        <span className="w-1.5 h-1.5 bg-muted-foreground/60 rounded-full animate-bounce [animation-delay:300ms]" />
      </span>
      <span className="text-[13px] text-muted-foreground">
        매뉴얼을 찾는 중{elapsed >= 10 ? ` · ${elapsed}초` : ""}
      </span>
    </div>
  );
}
