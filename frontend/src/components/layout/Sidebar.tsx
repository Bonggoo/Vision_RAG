"use client";

import React, { useRef, useEffect, useState } from "react";
import {
  PlusCircle,
  MessageSquare,
  UploadCloud,
  Loader2,
  FileText,
  Trash2,
  X,
  ChevronRight,
  Pencil,
  Check,
} from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useDocumentStore } from "@/store/useDocumentStore";

export default function Sidebar({ isOpen, onClose }: { isOpen?: boolean; onClose?: () => void }) {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const { sessions, activeSessionId, setActiveSession, createSession, deleteSession } =
    useChatStore();
  const { documents, uploadDocument, fetchDocuments, isUploading, deleteDoc, renameDoc } =
    useDocumentStore();

  // 인라인 파일명 수정 상태
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [editingName, setEditingName] = useState("");

  useEffect(() => {
    fetchDocuments();
  }, [fetchDocuments]);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      const doc = await uploadDocument(file);
      const title =
        file.name.length > 18 ? `${file.name.slice(0, 18)}...` : file.name;
      const sessionId = createSession(doc.document_id, title);
      setActiveSession(sessionId);
      onClose?.();
    } catch {
      alert("파일 업로드에 실패했습니다.");
    }
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDocumentSelect = (docId: string, filename: string) => {
    const title =
      filename.length > 18 ? `${filename.slice(0, 18)}...` : filename;
    const sessionId = createSession(docId, title);
    setActiveSession(sessionId);
    onClose?.();
  };

  const handleNewChat = () => {
    const sessionId = createSession(null, "새로운 대화");
    setActiveSession(sessionId);
    onClose?.();
  };

  const handleDeleteDoc = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    if (confirm("이 문서를 삭제하시겠습니까?")) {
      await deleteDoc(docId);
    }
  };

  const handleStartRename = (e: React.MouseEvent, docId: string, currentName: string) => {
    e.stopPropagation();
    setEditingDocId(docId);
    setEditingName(currentName);
  };

  const handleSaveRename = async (docId: string) => {
    const trimmed = editingName.trim();
    if (trimmed && trimmed !== documents.find(d => d.document_id === docId)?.filename) {
      await renameDoc(docId, trimmed);
    }
    setEditingDocId(null);
  };

  const sidebarContent = (
    <div className="flex flex-col h-full">
      {/* 로고 + 버튼 */}
      <div className="p-4 space-y-3">
        <div className="flex items-center justify-between mb-1">
          <div className="flex items-center gap-2">
            <div className="w-7 h-7 rounded-lg bg-gradient-to-br from-violet-500 to-blue-600 flex items-center justify-center">
              <span className="text-white text-xs font-bold">V</span>
            </div>
            <span className="text-sm font-semibold tracking-tight">Vision RAG</span>
          </div>
          {onClose && (
            <button onClick={onClose} className="md:hidden p-1 rounded hover:bg-accent/50 text-muted-foreground">
              <X className="w-4 h-4" />
            </button>
          )}
        </div>

        <input
          type="file"
          accept="application/pdf"
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="btn-secondary w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium disabled:opacity-50"
        >
          {isUploading ? (
            <Loader2 className="w-4 h-4 animate-spin" />
          ) : (
            <UploadCloud className="w-4 h-4" />
          )}
          {isUploading ? "업로드 중..." : "PDF 매뉴얼 업로드"}
        </button>

        <button
          onClick={handleNewChat}
          className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-lg text-sm font-medium"
        >
          <PlusCircle className="w-4 h-4" />
          새 대화 시작
        </button>
      </div>

      <div className="h-px bg-border/50 mx-4" />

      {/* 업로드된 문서 */}
      {documents.length > 0 && (
        <div className="px-3 pt-3 pb-1">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 px-2 py-1.5 uppercase tracking-widest">
            <FileText className="w-3 h-3" />
            업로드된 문서
          </div>
          <div className="space-y-0.5 max-h-44 overflow-y-auto scrollbar-thin">
            {documents.map((doc) => (
              <div
                key={doc.document_id}
                onClick={() => handleDocumentSelect(doc.document_id, doc.filename)}
                className="doc-item group flex items-center gap-2 px-3 py-2 cursor-pointer"
              >
                <div className="w-6 h-6 rounded-md bg-primary/10 flex items-center justify-center flex-shrink-0">
                  <FileText className="w-3 h-3 text-primary/70" />
                </div>
                <div className="flex-1 min-w-0">
                  {editingDocId === doc.document_id ? (
                    <input
                      autoFocus
                      type="text"
                      value={editingName}
                      onChange={(e) => setEditingName(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") handleSaveRename(doc.document_id);
                        if (e.key === "Escape") setEditingDocId(null);
                      }}
                      onBlur={() => handleSaveRename(doc.document_id)}
                      onClick={(e) => e.stopPropagation()}
                      className="w-full text-xs font-medium bg-accent/40 text-foreground px-1.5 py-0.5 rounded border border-primary/30 focus:outline-none focus:border-primary/60"
                    />
                  ) : (
                    <p className="text-xs font-medium truncate text-foreground/80 group-hover:text-foreground">
                      {doc.filename}
                    </p>
                  )}
                  <p className="text-[10px] text-muted-foreground/50">{doc.total_pages}페이지</p>
                </div>
                <div className="flex items-center gap-0.5">
                  {editingDocId === doc.document_id ? (
                    <button
                      onClick={(e) => { e.stopPropagation(); handleSaveRename(doc.document_id); }}
                      className="p-1 rounded hover:bg-primary/20 text-primary/60 hover:text-primary transition-all"
                    >
                      <Check className="w-3 h-3" />
                    </button>
                  ) : (
                    <button
                      onClick={(e) => handleStartRename(e, doc.document_id, doc.filename)}
                      className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-accent/50 text-muted-foreground/40 hover:text-foreground transition-all"
                    >
                      <Pencil className="w-3 h-3" />
                    </button>
                  )}
                  <button
                    onClick={(e) => handleDeleteDoc(e, doc.document_id)}
                    className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"
                  >
                    <Trash2 className="w-3 h-3" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      <div className="h-px bg-border/50 mx-4 mt-1" />

      {/* 최근 대화 */}
      <div className="flex-1 overflow-y-auto px-3 pt-3 space-y-0.5 scrollbar-thin">
        <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 px-2 py-1.5 uppercase tracking-widest">
          <MessageSquare className="w-3 h-3" />
          최근 대화
        </div>

        {sessions.length === 0 && (
          <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">
            대화 기록이 없습니다
          </p>
        )}

        {sessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2.5 px-3 py-2.5 rounded-lg text-sm cursor-pointer transition-all ${
              activeSessionId === session.id
                ? "bg-primary/10 text-foreground font-medium border border-primary/20"
                : "hover:bg-accent/40 text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => { setActiveSession(session.id); onClose?.(); }}
          >
            <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${
              activeSessionId === session.id ? "text-primary rotate-90" : ""
            }`} />
            <span className="truncate flex-1 text-[13px]">{session.title}</span>
            <button
              onClick={(e) => { e.stopPropagation(); deleteSession(session.id); }}
              className="opacity-0 group-hover:opacity-100 p-1 rounded hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>

      {/* 하단 정보 */}
      <div className="p-4 border-t border-border/30">
        <p className="text-[10px] text-muted-foreground/40 text-center">
          Vectorless Agentic Vision RAG v1.0
        </p>
      </div>
    </div>
  );

  return (
    <>
      {/* 모바일 오버레이 */}
      {isOpen && (
        <div className="sidebar-overlay fixed inset-0 z-40 md:hidden animate-fade" onClick={onClose} />
      )}

      {/* 데스크탑: 항상 표시 / 모바일: isOpen 시 표시 */}
      <aside className={`
        sidebar w-72 h-full flex-col z-50
        hidden md:flex
      `}>
        {sidebarContent}
      </aside>

      {/* 모바일 슬라이드인 */}
      <aside className={`
        sidebar fixed top-0 left-0 w-72 h-full flex flex-col z-50
        md:hidden
        transition-transform duration-300 ease-out
        ${isOpen ? "translate-x-0" : "-translate-x-full"}
      `}>
        {sidebarContent}
      </aside>
    </>
  );
}
