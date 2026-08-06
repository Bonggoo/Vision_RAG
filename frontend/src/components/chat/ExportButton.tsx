"use client";

import React from "react";
import { Share } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { toast, confirmDialog } from "@/store/useUIStore";

export default function ExportButton() {
  const { sessions, activeSessionId } = useChatStore();

  const handleExport = async () => {
    const session = sessions.find((s) => s.id === activeSessionId);
    if (!session) {
      toast.info("내보낼 대화가 없습니다.");
      return;
    }

    if (session.messages.length === 0) {
      toast.info("대화 기록이 비어 있습니다.");
      return;
    }

    // 💡 내보내기 전 다운로드 여부 확인 (사용자 취소 지원)
    const ok = await confirmDialog({
      title: "대화 내보내기",
      description: `'${session.title}' 대화를 마크다운(.md) 파일로 저장할까요?`,
      confirmText: "내보내기",
    });
    if (!ok) return;

    // 1. 마크다운 생성
    const today = new Date().toISOString().split("T")[0];
    let markdown = `# ${session.title}\n\n`;
    markdown += `> TechNote 대화 기록 · ${today}\n\n`;
    markdown += `---\n\n`;

    session.messages.forEach((msg) => {
      if (msg.role === "user") {
        markdown += `## 질문\n\n${msg.content}\n\n`;
      } else {
        markdown += `## 답변\n\n`;

        // 추론 과정은 접이식 블록으로 (본문 가독성 우선)
        if (msg.reasoningSteps && msg.reasoningSteps.length > 0) {
          markdown += `<details>\n<summary>추론 과정 ${msg.reasoningSteps.length}단계</summary>\n\n`;
          msg.reasoningSteps.forEach((step, i) => {
            markdown += `${i + 1}. ${step}\n`;
          });
          markdown += `\n</details>\n\n`;
        }

        markdown += `${msg.content}\n\n`;
      }
      markdown += `---\n\n`;
    });

    markdown += `_TechNote AI로 생성된 대화 기록입니다._\n`;

    // 2. Blob을 이용한 다운로드 실행
    try {
      const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      
      // 파일명 조합 (특수문자 필터링)
      const cleanTitle = session.title.replace(/[\\/*?:"<>|]/g, "").trim();
      const filename = `TechNote_${cleanTitle || "대화"}_${today.replace(/-/g, "")}.md`;
      
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      toast.success("대화 기록을 저장했어요.");
    } catch (error) {
      console.error("대화 내보내기 실패:", error);
      toast.error("대화 내보내기에 실패했습니다.");
    }
  };

  return (
    <button
      onClick={handleExport}
      title="대화 내보내기"
      aria-label="대화 내보내기"
      className="btn-ghost flex items-center gap-1.5 py-1.5 px-2.5 rounded-md text-[12.5px]"
    >
      <Share className="w-3.5 h-3.5 shrink-0" />
      <span className="hidden sm:inline">내보내기</span>
    </button>
  );
}
