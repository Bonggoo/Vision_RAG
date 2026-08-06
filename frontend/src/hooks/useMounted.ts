"use client";

import { useSyncExternalStore } from "react";

/** 구독 대상이 없는 스토어 — 값이 바뀌지 않으므로 해지 함수만 돌려준다 */
const noopSubscribe = () => () => {};

/**
 * 클라이언트 마운트 완료 여부.
 * SSR 결과와 다른 트리를 그려야 하는 컴포넌트(테마, localStorage 의존 등)에서
 * hydration mismatch 를 피하기 위해 사용한다.
 *
 * `useState + useEffect` 대신 `useSyncExternalStore` 를 쓰면 추가 렌더 없이
 * 서버에서는 false, 클라이언트에서는 true 를 반환한다.
 */
export function useMounted(): boolean {
  return useSyncExternalStore(
    noopSubscribe,
    () => true, // 클라이언트
    () => false // 서버 / hydration 첫 렌더
  );
}
