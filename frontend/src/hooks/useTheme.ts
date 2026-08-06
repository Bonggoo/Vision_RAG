"use client";

import { useCallback, useState } from "react";

export type Theme = "light" | "dark";

const readThemeFromDom = (): Theme => {
  if (typeof document === "undefined") return "light";
  return document.documentElement.classList.contains("dark") ? "dark" : "light";
};

/**
 * 테마 상태 + 토글.
 *
 * 최초 테마는 `app/layout.tsx` 의 인라인 스크립트가 이미 `<html>` 에 적용해 두었으므로
 * 여기서는 그 DOM 상태를 읽어 미러링만 한다(중복 적용 금지 — 깜빡임 원인).
 * 초기값은 lazy initializer 로 렌더 중에 읽어 별도 effect 를 두지 않는다.
 */
export function useTheme() {
  const [theme, setThemeState] = useState<Theme>(readThemeFromDom);

  const setTheme = useCallback((next: Theme) => {
    setThemeState(next);
    document.documentElement.classList.toggle("dark", next === "dark");
    try {
      localStorage.setItem("theme", next);
    } catch {
      // 사파리 프라이빗 모드 등 localStorage 접근 불가 — 세션 내에서만 적용
    }
  }, []);

  const toggleTheme = useCallback(
    () => setTheme(readThemeFromDom() === "dark" ? "light" : "dark"),
    [setTheme]
  );

  return { theme, setTheme, toggleTheme };
}
