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
  PanelLeftClose,
  PanelLeftOpen,
  LogOut
} from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useDocumentStore, Document } from "@/store/useDocumentStore";
import { useAuthStore } from "@/store/useAuthStore";
import { api, authFetch, API_BASE_URL } from "@/lib/api";
import { toast, confirmDialog } from "@/store/useUIStore";
import { processUploadFiles } from "@/lib/upload";
import { isSupportedUploadFile, UPLOAD_ACCEPT_ATTR, UNSUPPORTED_FORMAT_MESSAGE } from "@/lib/fileTypes";
import SparkleLogo from "./SparkleLogo";
import DocSearchBar from "./sidebar/DocSearchBar";
import SortToggle from "./sidebar/SortToggle";
import DocItem from "./sidebar/DocItem";
import DocTree from "./sidebar/DocTree";
import { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs } from "./sidebar/utils";

// 💡 하위 호환을 위해 sidebar/utils 의 헬퍼를 그대로 재export (이전 공개 API 유지)
export { getDisplayFilename, sortByName, sortByDate, getLatestDateInDocs };

export default function Sidebar({ isOpen, onClose, isCollapsed, onToggleCollapse }: {
  isOpen?: boolean;
  onClose?: () => void;
  isCollapsed?: boolean;
  onToggleCollapse?: () => void;
}) {
  const [isMounted, setIsMounted] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);
  
  // 탭 상태 (chat | docs)
  const [activeTab, setActiveTab] = useState<"chat" | "docs">("chat");

  const { 
    sessions, activeSessionId, setActiveSession, createSession, deleteSession, loadConversation 
  } = useChatStore();
  const { user, logout } = useAuthStore();

  const mySessions = sessions.filter(s => s.ownerEmail === user?.email || !s.ownerEmail);
  const {
    documents, uploadDocuments, fetchDocuments, isUploading, uploadingIndex, uploadTotal,
    uploadProgress: storeUploadProgress, deleteDoc, updateDocMeta, downloadDoc
  } = useDocumentStore();

  const analyzingDocuments = documents.filter((doc) => doc.status === "analyzing");

  const [isDragging, setIsDragging] = useState(false);
  const [searchQuery, setSearchQuery] = useState("");
  const [expandedManufacturers, setExpandedManufacturers] = useState<Record<string, boolean>>({});
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});
  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [editingMfg, setEditingMfg] = useState("");
  const [editingModel, setEditingModel] = useState("");
  const [editingName, setEditingName] = useState("");
  const [uploadProgress, setUploadProgress] = useState(0);
  const [sortBy, setSortBy] = useState<"latest" | "name">("latest");

  useEffect(() => {
    setIsMounted(true);
  }, []);

  useEffect(() => {
    if (isUploading && uploadTotal > 0) {
      setUploadProgress(storeUploadProgress);
    } else {
      setUploadProgress(0);
    }
  }, [isUploading, storeUploadProgress, uploadTotal]);

  useEffect(() => {
    const isDesktop = () => typeof window !== "undefined" && window.innerWidth >= 768;
    if (!isDesktop() && !isOpen) return;

    fetchDocuments();

    const interval = setInterval(() => {
      if (!isUploading) {
        fetchDocuments();
      }
    }, 60000);

    return () => clearInterval(interval);
  }, [isOpen, fetchDocuments, isUploading]);

  const handleDownloadDoc = async (e: React.MouseEvent, doc: any) => {
    e.stopPropagation();
    const displayFilename = getDisplayFilename(doc);
    const parts = [doc.manufacturer, doc.model_series, doc.doc_type || displayFilename].filter(Boolean);
    // 비-PDF 업로드 문서는 보관된 원본(원래 확장자)이 다운로드됨
    const ext = doc.source_format && doc.source_format !== "pdf" ? `.${doc.source_format}` : ".pdf";
    const fallbackName = displayFilename.endsWith(ext) ? displayFilename : `${displayFilename}${ext}`;
    let downloadName = parts.length > 0 ? `${parts.join("_")}` : fallbackName;
    if (parts.length > 0 && !downloadName.endsWith(ext)) downloadName += ext;
    const ok = await confirmDialog({
      title: "문서 다운로드",
      description: `"${downloadName}" 문서를 다운로드할까요?`,
      confirmText: "다운로드",
      icon: "📥",
    });
    if (ok) downloadDoc(doc.document_id);
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    await handleUploadFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    const supportedFiles = files.filter(isSupportedUploadFile);
    if (supportedFiles.length === 0) { toast.warning(UNSUPPORTED_FORMAT_MESSAGE); return; }
    await handleUploadFiles(supportedFiles);
  };

  const handleUploadFiles = (files: File[]) => processUploadFiles(files, uploadDocuments, fetchDocuments);

  const handleRetryAnalysis = async (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    try {
      const res = await authFetch(`${API_BASE_URL}/upload/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: doc.document_id, filename: doc.filename, file_hash: doc.file_hash || "" })
      });
      if (!res.ok) throw new Error("재분석 요청 실패");
      toast.success("AI 분석을 다시 시작했습니다!");
      fetchDocuments();
    } catch (err: any) { toast.error(`재분석 시작 실패: ${err.message}`); }
  };

  const handleNewChat = async () => {
    try {
      // 이미 메시지가 없는 빈 세션이 있다면 해당 세션으로 이동 (중복 생성 방지)
      const emptySession = mySessions.find(s => s.messages.length === 0);
      
      if (emptySession) {
        setActiveSession(emptySession.id);
      } else {
        const sessionId = await createSession("새로운 대화");
        setActiveSession(sessionId);
      }
      
      onClose?.();
      if (!isCollapsed && onToggleCollapse) {
        onToggleCollapse();
      }
      setActiveTab("chat");
    } catch (err: any) { toast.error(err.message || "대화 세션 생성에 실패했습니다."); }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    const ok = await confirmDialog({
      title: "대화 삭제",
      description: "이 대화를 삭제할까요?",
      confirmText: "삭제",
      danger: true,
      icon: "🗑️",
    });
    if (!ok) return;
    try { await deleteSession(sessionId); }
    catch (err: any) { toast.error(err.message || "대화 삭제에 실패했습니다."); }
  };

  const handleDeleteDoc = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    const ok = await confirmDialog({
      title: "문서 삭제",
      description: "이 문서를 삭제할까요?\n관련 데이터가 모두 영구 제거됩니다.",
      confirmText: "삭제",
      danger: true,
      icon: "🗑️",
    });
    if (ok) await deleteDoc(docId);
  };

  const handleStartRename = (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    setEditingDocId(doc.document_id); setEditingMfg(doc.manufacturer || "");
    setEditingModel(doc.model_series || ""); setEditingName(getDisplayFilename(doc));
  };

  const handleSaveMeta = async (docId: string) => {
    const trimmedName = editingName.trim();
    if (!trimmedName) { toast.warning("문서 제목은 필수입니다."); return; }
    try {
      await updateDocMeta(docId, { filename: trimmedName, manufacturer: editingMfg.trim() || undefined, model_series: editingModel.trim() || undefined });
      setEditingDocId(null);
      toast.success("문서 정보를 저장했어요.");
    } catch (err: any) { toast.error(err.message || "메타데이터 수정에 실패했습니다."); }
  };

  const handleBatchDelete = async (e: React.MouseEvent, docs: Document[], groupLabel: string) => {
    e.stopPropagation();
    const targetDocs = docs.filter(d => d.status !== "analyzing");
    if (targetDocs.length === 0) return;
    const ok = await confirmDialog({
      title: "그룹 문서 삭제",
      description: `"${groupLabel}" 그룹의 문서 ${targetDocs.length}개를 모두 삭제할까요?\n이 작업은 되돌릴 수 없습니다.`,
      confirmText: `${targetDocs.length}개 삭제`,
      danger: true,
      icon: "🗑️",
    });
    if (!ok) return;
    for (const doc of targetDocs) await deleteDoc(doc.document_id);
    toast.success(`문서 ${targetDocs.length}개를 삭제했어요.`);
  };

  const handleBatchDownload = async (e: React.MouseEvent, docs: Document[], groupLabel: string) => {
    e.stopPropagation();
    const targetDocs = docs.filter(d => d.status !== "analyzing" && d.status !== "error");
    if (targetDocs.length === 0) { toast.info("다운로드 가능한 문서가 없습니다."); return; }
    const ok = await confirmDialog({
      title: "그룹 문서 다운로드",
      description: `"${groupLabel}" 그룹의 문서 ${targetDocs.length}개를 순차 다운로드할까요?`,
      confirmText: "다운로드",
      icon: "📥",
    });
    if (!ok) return;
    for (const doc of targetDocs) { await downloadDoc(doc.document_id); await new Promise(r => setTimeout(r, 500)); }
  };

  const [isReclassifying, setIsReclassifying] = useState(false);
  const handleReclassify = async (e: React.MouseEvent) => {
    e.stopPropagation(); if (isReclassifying) return;
    setIsReclassifying(true);
    try {
      const result = await api.reclassifyDocuments();
      toast.info(result.message, { title: "문서 재분류" });
      if (result.count > 0) {
        setTimeout(() => fetchDocuments(), result.count * 2000 + 3000);
        setTimeout(() => fetchDocuments(), Math.min(result.count * 1000, 15000));
      }
    } catch (err: any) { toast.error(err.message || "재분류 요청에 실패했습니다."); }
    finally { setIsReclassifying(false); }
  };

  const filteredDocuments = documents.filter((doc) => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return true;
    return ( getDisplayFilename(doc).toLowerCase().includes(query) || (doc.manufacturer || "").toLowerCase().includes(query) || (doc.model_series || "").toLowerCase().includes(query) );
  });

  const existingManufacturers = Array.from(new Set(documents.map(d => d.manufacturer).filter(Boolean))) as string[];

  const toggleManufacturer = (mfg: string) => setExpandedManufacturers(prev => ({ ...prev, [mfg]: !prev[mfg] }));
  const toggleModel = (model: string) => setExpandedModels(prev => ({ ...prev, [model]: !prev[model] }));

  // 💡 개별 문서 항목 렌더링 — DocItem 으로 위임 (편집 상태/핸들러는 Sidebar 가 소유)
  const renderDocItem = (doc: Document) => (
    <DocItem
      key={doc.document_id}
      doc={doc}
      isEditing={editingDocId === doc.document_id}
      editingMfg={editingMfg}
      setEditingMfg={setEditingMfg}
      editingModel={editingModel}
      setEditingModel={setEditingModel}
      editingName={editingName}
      setEditingName={setEditingName}
      onSave={handleSaveMeta}
      onCancel={() => setEditingDocId(null)}
      onRetry={handleRetryAnalysis}
      onDownload={handleDownloadDoc}
      onStartRename={handleStartRename}
      onDelete={handleDeleteDoc}
    />
  );

  if (!isMounted) return null;

  const renderChatTab = () => (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3">
        <button
          onClick={handleNewChat}
          className="btn-primary w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-full text-sm font-medium shadow-md transition-all"
        >
          <PlusCircle className="w-4 h-4" />
          새 대화 시작
        </button>
      </div>
      <div className="flex-1 overflow-y-auto px-3 space-y-0.5 scrollbar-thin">
        {mySessions.length === 0 && (
          <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">
            대화 기록이 없습니다
          </p>
        )}
        {mySessions.map((session) => (
          <div
            key={session.id}
            className={`group flex items-center gap-2.5 px-3 py-2 rounded-xl text-sm cursor-pointer transition-all ${
              activeSessionId === session.id
                ? "bg-primary/10 text-primary font-medium border border-primary/20 shadow-sm"
                : "hover:bg-accent/40 text-muted-foreground hover:text-foreground"
            }`}
            onClick={() => { loadConversation(session.id); onClose?.(); }}
          >
            <ChevronRight className={`w-3.5 h-3.5 shrink-0 transition-transform ${
              activeSessionId === session.id ? "rotate-90" : ""
            }`} />
            <span className="truncate flex-1 text-[13px]">{session.title}</span>
            <button
              onClick={(e) => handleDeleteSession(e, session.id)}
              className="opacity-100 md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"
            >
              <Trash2 className="w-3 h-3" />
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  const renderDocsTab = () => (
    <div className="flex-1 flex flex-col min-h-0">
      <div className="px-4 py-3 space-y-3">
        <input type="file" accept={UPLOAD_ACCEPT_ATTR} multiple className="hidden" ref={fileInputRef} onChange={handleFileUpload} />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className={`w-full flex items-center justify-center gap-2 py-2.5 px-4 rounded-full text-sm font-medium relative overflow-hidden transition-all ${
            isUploading ? "bg-primary/5 border border-primary/20 text-primary cursor-not-allowed" : "btn-primary"
          }`}
        >
          {isUploading && <div className="absolute left-0 top-0 bottom-0 bg-primary/10 transition-all duration-300 ease-out" style={{ width: `${uploadProgress}%` }} />}
          <div className="flex items-center gap-2 relative z-10 w-full justify-center">
            {isUploading ? <Loader2 className="w-4 h-4 animate-spin shrink-0" /> : <UploadCloud className="w-4 h-4 shrink-0" />}
            <span className="truncate text-[13px] font-semibold">{isUploading ? `업로드 중... (${uploadingIndex + 1}/${uploadTotal})` : "문서 업로드"}</span>
          </div>
        </button>

        <DocSearchBar value={searchQuery} onChange={setSearchQuery} onClear={() => setSearchQuery("")} />
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-3 pb-1">
        <div className="flex items-center justify-between px-2 py-1 mb-2">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 tracking-widest">
            <FileText className="w-3 h-3" /> 업로드된 문서
          </div>
          <SortToggle sortBy={sortBy} onChange={setSortBy} />
        </div>
        {analyzingDocuments.length > 0 && (
          <div className="mx-1 mt-1 mb-2.5 space-y-1.5 p-2 bg-amber-500/5 border border-amber-500/10 rounded-xl animate-pulse">
            <div className="flex items-center gap-1.5 px-1 py-0.5 text-[9px] font-bold text-amber-500 uppercase tracking-wider">
              <Loader2 className="w-2.5 h-2.5 animate-spin" /><span>AI 분석 중 ({analyzingDocuments.length})</span>
            </div>
            <div className="space-y-1 max-h-[120px] overflow-y-auto scrollbar-thin">
              {analyzingDocuments.map((doc) => (
                <div key={doc.document_id} className="flex items-center gap-1.5 px-2 py-1 rounded-lg bg-background/40 border border-amber-500/5 text-[10px] text-foreground/70">
                  <Loader2 className="w-2.5 h-2.5 text-amber-500 animate-spin shrink-0" />
                  <span className="truncate flex-1 font-medium leading-tight">{getDisplayFilename(doc)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="px-1">
          <DocTree
            documents={documents}
            filteredDocuments={filteredDocuments}
            searchQuery={searchQuery}
            sortBy={sortBy}
            expandedManufacturers={expandedManufacturers}
            expandedModels={expandedModels}
            onToggleManufacturer={toggleManufacturer}
            onToggleModel={toggleModel}
            isReclassifying={isReclassifying}
            onReclassify={handleReclassify}
            onBatchDownload={handleBatchDownload}
            onBatchDelete={handleBatchDelete}
            renderDocItem={renderDocItem}
          />
        </div>
      </div>
    </div>
  );

  const sidebarContent = (
    <div
      onDragOver={handleDragOver} onDragLeave={handleDragLeave} onDrop={handleDrop}
      className={`flex flex-col h-full relative transition-all duration-300 ${isDragging ? "border-2 border-dashed border-primary bg-primary/5 shadow-2xl scale-[0.99] rounded-xl" : "bg-background"}`}
    >
      {isDragging && (
        <div className="absolute inset-0 bg-primary/5 backdrop-blur-[1px] flex flex-col items-center justify-center pointer-events-none z-50 rounded-xl">
          <UploadCloud className="w-12 h-12 text-primary animate-bounce mb-2" />
          <p className="text-sm font-bold text-primary">문서를 놓아 업로드하세요</p>
        </div>
      )}

      {/* 로고 & 상단 탭 */}
      <div className="p-4 flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <SparkleLogo className="w-8 h-8 filter drop-shadow-[0_2px_8px_rgba(139,92,246,0.35)]" />
            <span className="text-[17px] font-semibold tracking-tight font-display">TechNote</span>
          </div>
          <div className="flex items-center gap-1">
            {onClose && <button onClick={onClose} className="md:hidden p-1.5 rounded-full hover:bg-accent/50 text-muted-foreground"><X className="w-4 h-4" /></button>}
            {onToggleCollapse && <button onClick={onToggleCollapse} title="사이드바 접기" className="hidden md:flex p-1.5 rounded-full hover:bg-accent/50 text-muted-foreground hover:text-foreground transition-all"><PanelLeftClose className="w-4 h-4" /></button>}
          </div>
        </div>

        {/* 탭 네비게이션 (Stitch 스타일 Pill) */}
        <div className="flex p-1 bg-accent/20 rounded-full border border-border/30">
          <button
            onClick={() => setActiveTab("chat")}
            className={`flex-1 py-1.5 text-[13px] font-medium rounded-full transition-all flex items-center justify-center gap-1.5 ${activeTab === "chat" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-background/50"}`}
          >
            <MessageSquare className="w-3.5 h-3.5" /> Chat
          </button>
          <button
            onClick={() => setActiveTab("docs")}
            className={`flex-1 py-1.5 text-[13px] font-medium rounded-full transition-all flex items-center justify-center gap-1.5 ${activeTab === "docs" ? "bg-background shadow text-foreground" : "text-muted-foreground hover:text-foreground hover:bg-background/50"}`}
          >
            <FileText className="w-3.5 h-3.5" /> Documents
          </button>
        </div>
      </div>

      <div className="h-px bg-border/40 mx-4" />

      {/* 탭 콘텐츠 영역 */}
      {activeTab === "chat" ? renderChatTab() : renderDocsTab()}

      {/* 하단 유저 프로필 영역 (Stitch 디자인 적용) */}
      <div className="p-3 border-t border-border/30 mt-auto bg-background/50">
        {user ? (
          <div className="flex items-center justify-between p-2 rounded-xl hover:bg-accent/40 transition-colors">
            <div className="flex items-center gap-2.5 overflow-hidden">
              {user.picture ? (
                <img src={user.picture} alt={user.name} className="w-8 h-8 rounded-full border border-border/40 object-cover shrink-0" referrerPolicy="no-referrer" />
              ) : (
                <div className="w-8 h-8 rounded-full bg-primary/20 text-primary flex items-center justify-center text-xs font-bold shrink-0">{user.name.slice(0, 1)}</div>
              )}
              <div className="flex flex-col min-w-0">
                <span className="text-[13px] font-semibold text-foreground truncate">{user.name}</span>
                <span className="text-[10px] text-muted-foreground truncate">{user.email}</span>
              </div>
            </div>
            <button
              onClick={() => { useChatStore.getState().resetActiveSession(); logout(); }}
              title="로그아웃"
              className="p-2 rounded-full text-muted-foreground hover:text-destructive hover:bg-destructive/10 transition-colors shrink-0"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        ) : (
          <div className="text-center p-2 text-xs text-muted-foreground">로그인이 필요합니다</div>
        )}
      </div>
    </div>
  );

  return (
    <>
      {isOpen && <div className="sidebar-overlay fixed inset-0 z-40 md:hidden animate-fade" onClick={onClose} />}
      <aside className={`sidebar h-full flex-col z-50 hidden md:flex transition-all duration-300 ease-in-out ${isCollapsed ? 'w-[72px]' : 'w-[280px]'}`}>
        {isCollapsed ? (
          <div className="flex flex-col h-full items-center py-5 gap-4">
            <div className="cursor-pointer mb-2" onClick={onToggleCollapse}>
              <SparkleLogo className="w-9 h-9 filter drop-shadow-[0_2px_8px_rgba(139,92,246,0.35)] hover:scale-105 transition-transform" />
            </div>
            <button onClick={onToggleCollapse} title="사이드바 펼치기" className="p-2.5 rounded-full text-muted-foreground hover:text-foreground hover:bg-accent/50 transition-all">
              <PanelLeftOpen className="w-5 h-5" />
            </button>
            <div className="h-px w-10 bg-border/50 my-1" />
            <button onClick={() => { setActiveTab("chat"); onToggleCollapse?.(); handleNewChat(); }} title="새 대화 시작" className="p-2.5 rounded-full text-primary hover:bg-primary/10 transition-all">
              <PlusCircle className="w-5 h-5" />
            </button>
            <div className="h-px w-10 bg-border/50 my-1" />
            <button onClick={() => { setActiveTab("docs"); onToggleCollapse?.(); }} title={`문서 ${documents.filter(d => d.status !== 'analyzing').length}개`} className={`p-2.5 rounded-full transition-all ${activeTab === 'docs' ? 'text-primary bg-primary/10' : 'text-muted-foreground/60 hover:bg-accent/50'}`}>
              <FileText className="w-5 h-5" />
            </button>
            <button onClick={() => { setActiveTab("chat"); onToggleCollapse?.(); }} title={`대화 ${mySessions.length}개`} className={`p-2.5 rounded-full transition-all ${activeTab === 'chat' ? 'text-primary bg-primary/10' : 'text-muted-foreground/60 hover:bg-accent/50'}`}>
              <MessageSquare className="w-5 h-5" />
            </button>
            <div className="mt-auto flex flex-col items-center gap-3">
              {user && (
                <button title="로그아웃" onClick={() => { useChatStore.getState().resetActiveSession(); logout(); }} className="w-10 h-10 rounded-full overflow-hidden border border-border/40 hover:opacity-80 shrink-0 flex items-center justify-center bg-accent/20">
                  {user.picture ? <img src={user.picture} alt="profile" className="w-full h-full object-cover" /> : <div className="w-full h-full text-primary flex items-center justify-center text-sm font-bold">{user.name.slice(0, 1)}</div>}
                </button>
              )}
            </div>
          </div>
        ) : sidebarContent}
      </aside>
      <aside className={`sidebar fixed top-0 left-0 w-[88vw] max-w-[320px] h-full flex flex-col z-50 md:hidden transition-transform duration-300 ease-out ${isOpen ? "translate-x-0" : "-translate-x-full"}`}>
        {sidebarContent}
      </aside>
    </>
  );
}
