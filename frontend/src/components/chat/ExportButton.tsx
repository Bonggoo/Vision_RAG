"use client";

import React from "react";
import { Share } from "lucide-react";
import { useChatStore } from "@/store/useChatStore";

export default function ExportButton() {
  const { sessions, activeSessionId } = useChatStore();

  const handleExport = () => {
    const session = sessions.find((s) => s.id === activeSessionId);
    if (!session) {
      alert("내보낼 대화가 없습니다.");
      return;
    }

    if (session.messages.length === 0) {
      alert("대화 기록이 비어 있습니다.");
      return;
    }

    // 1. 마크다운 생성
    const today = new Date().toISOString().split("T")[0];
    let markdown = `# 💎 Vision RAG 대화 기록\n`;
    markdown += `> 💬 **대화 제목**: ${session.title}\n`;
    markdown += `> 📅 **내보낸 날짜**: ${today}\n\n`;
    markdown += `---\n\n`;

    session.messages.forEach((msg) => {
      if (msg.role === "user") {
        markdown += `## 👤 사용자\n`;
        markdown += `${msg.content}\n\n`;
      } else {
        markdown += `## 🤖 Vision RAG\n`;
        
        // 생각 과정(reasoningSteps)이 존재한다면 요약 블록으로 추가
        if (msg.reasoningSteps && msg.reasoningSteps.length > 0) {
          markdown += `<details>\n`;
          markdown += `<summary>🧠 AI 추론 과정 (Reasoning Steps)</summary>\n\n`;
          msg.reasoningSteps.forEach((step) => {
            markdown += `> ${step}\n`;
          });
          markdown += `\n</details>\n\n`;
        }

        markdown += `${msg.content}\n\n`;
      }
      markdown += `---\n\n`;
    });

    markdown += `_Vectorless Agentic Vision RAG에서 생성된 대화 기록입니다._\n`;

    // 2. Blob을 이용한 다운로드 실행
    try {
      const blob = new Blob([markdown], { type: "text/markdown;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      
      // 파일명 조합 (특수문자 필터링)
      const cleanTitle = session.title.replace(/[\\/*?:"<>|]/g, "").trim();
      const filename = `VisionRAG_${cleanTitle || "대화"}_${today.replace(/-/g, "")}.md`;
      
      link.href = url;
      link.setAttribute("download", filename);
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
    } catch (error) {
      console.error("대화 내보내기 실패:", error);
      alert("대화 내보내기에 실패했습니다.");
    }
  };

  return (
    <button
      onClick={handleExport}
      title="대화 내보내기"
      className="btn-secondary flex items-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-medium text-muted-foreground hover:text-foreground transition-all shadow-sm border border-border/40 bg-accent/25 hover:bg-accent/45"
    >
      <Share className="w-3.5 h-3.5 shrink-0" />
      <span>대화 내보내기</span>
    </button>
  );
}
