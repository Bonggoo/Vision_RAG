"use client";

import React from "react";
import { LogOut } from "lucide-react";
import { useAuthStore } from "@/store/useAuthStore";
import { useChatStore } from "@/store/useChatStore";

/** 사이드바 하단 사용자 정보 + 로그아웃 */
export default function UserMenu({ compact = false }: { compact?: boolean }) {
  const { user, logout } = useAuthStore();

  const handleLogout = () => {
    useChatStore.getState().resetActiveSession();
    logout();
  };

  if (!user) {
    return compact ? null : (
      <p className="p-3 text-center text-[12px] text-muted-foreground">로그인이 필요합니다.</p>
    );
  }

  const avatar = user.picture ? (
    // eslint-disable-next-line @next/next/no-img-element -- 구글 프로필 CDN 이미지, next/image 도메인 설정 없이 사용
    <img
      src={user.picture}
      alt=""
      referrerPolicy="no-referrer"
      className="w-7 h-7 rounded-full object-cover border border-border shrink-0"
    />
  ) : (
    <span className="w-7 h-7 rounded-full bg-[var(--muted)] text-foreground flex items-center justify-center text-[12px] font-medium shrink-0">
      {user.name.slice(0, 1)}
    </span>
  );

  if (compact) {
    return (
      <button
        onClick={handleLogout}
        title={`${user.name} · 로그아웃`}
        aria-label="로그아웃"
        className="btn-ghost p-1 rounded-full"
      >
        {avatar}
      </button>
    );
  }

  return (
    <div className="flex items-center gap-2 p-2 mx-2 mb-2 rounded-lg">
      {avatar}
      <div className="flex flex-col min-w-0 flex-1">
        <span className="text-[12.5px] font-medium truncate">{user.name}</span>
        <span className="text-[11px] text-muted-foreground truncate">{user.email}</span>
      </div>
      <button
        onClick={handleLogout}
        title="로그아웃"
        aria-label="로그아웃"
        className="btn-ghost p-1.5 rounded-md shrink-0 hover:text-destructive"
      >
        <LogOut className="w-4 h-4" />
      </button>
    </div>
  );
}
