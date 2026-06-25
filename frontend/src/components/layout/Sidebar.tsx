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
  ChevronDown,
  Pencil,
  Check,
  Download,
  Building,
  Cpu,
  Folder,
  Search,
  AlertCircle,
  RotateCw,
  RefreshCw,
  PanelLeftClose,
  PanelLeftOpen,
  LogOut
} from "lucide-react";
import { useChatStore } from "@/store/useChatStore";
import { useDocumentStore, Document } from "@/store/useDocumentStore";
import { useAuthStore } from "@/store/useAuthStore";
import { api } from "@/lib/api";
import SparkleLogo from "./SparkleLogo";

// 💡 PDF 메타데이터 찌꺼기 등을 제외하고 가독성 있는 파일명을 결정하는 헬퍼 함수
export const getDisplayFilename = (doc: any): string => {
  const badTitlePattern = /^(microsoft word\s*-\s*)|^(한글\s*-\s*)|^(adobe indesign\s*)|untitled|document|cover|제목\s*없음|\.(doc|docx|pdf|cdr|xls|xlsx|ppt|pptx|hwp|png|jpg)$/i;
  
  if (doc.filename && badTitlePattern.test(doc.filename)) {
    if (doc.original_filename) {
      return doc.original_filename.replace(/\.pdf$/i, "");
    }
  }
  return doc.filename;
};

// 💡 문자열의 첫 글자가 한글인지 여부를 판별하는 헬퍼 함수
const isKoreanStart = (str: string): boolean => {
  if (!str) return false;
  const firstChar = str.trim().charAt(0);
  return /[\u3130-\u318F\uAC00-\uD7A3]/.test(firstChar);
};

// 💡 한글 가나다 및 영어 ABCD 사전식 오름차순 정렬을 위한 헬퍼 함수
export const sortByName = (a: string, b: string): number => {
  if (a === "미분류") return 1;
  if (b === "미분류") return -1;

  const aIsKo = isKoreanStart(a);
  const bIsKo = isKoreanStart(b);

  if (aIsKo && !bIsKo) return 1;
  if (!aIsKo && bIsKo) return -1;

  return a.localeCompare(b, "ko", { sensitivity: "base", numeric: true });
};

// 💡 업로드 날짜 기준 정렬
export const sortByDate = (a: any, b: any): number => {
  const dateA = a.uploaded_at ? new Date(a.uploaded_at).getTime() : 0;
  const dateB = b.uploaded_at ? new Date(b.uploaded_at).getTime() : 0;
  return dateB - dateA;
};

export const getLatestDateInDocs = (docs: any[]): number => {
  if (docs.length === 0) return 0;
  return Math.max(...docs.map(d => d.uploaded_at ? new Date(d.uploaded_at).getTime() : 0));
};

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

  const handleDownloadDoc = (e: React.MouseEvent, doc: any) => {
    e.stopPropagation();
    const displayFilename = getDisplayFilename(doc);
    const parts = [doc.manufacturer, doc.model_series, doc.doc_type || displayFilename].filter(Boolean);
    const fallbackName = displayFilename.endsWith(".pdf") ? displayFilename : `${displayFilename}.pdf`;
    let downloadName = parts.length > 0 ? `${parts.join("_")}` : fallbackName;
    if (parts.length > 0 && !downloadName.endsWith(".pdf")) downloadName += ".pdf";
    if (window.confirm(`📥 "${downloadName}" 문서를 다운로드하시겠습니까?`)) {
      downloadDoc(doc.document_id);
    }
  };

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length === 0) return;
    await processUploadFiles(files);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const handleDragOver = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(true); };
  const handleDragLeave = (e: React.DragEvent) => { e.preventDefault(); setIsDragging(false); };
  const handleDrop = async (e: React.DragEvent) => {
    e.preventDefault(); setIsDragging(false);
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    const pdfFiles = files.filter(f => f.type === "application/pdf" || f.name.toLowerCase().endsWith(".pdf"));
    if (pdfFiles.length === 0) { alert("PDF 파일만 업로드할 수 있습니다."); return; }
    await processUploadFiles(pdfFiles);
  };

  const processUploadFiles = async (files: File[]) => {
    try {
      const results = await uploadDocuments(files);
      const successCount = results.filter(r => r.status === "success").length;
      const dupCount = results.filter(r => r.status === "duplicate").length;
      const errCount = results.filter(r => r.status === "error").length;
      let alertMsg = `🎉 업로드 완료! (성공: ${successCount}개`;
      if (dupCount > 0) alertMsg += `, 중복: ${dupCount}개`;
      if (errCount > 0) alertMsg += `, 실패: ${errCount}개`;
      alertMsg += `)`;
      if (errCount > 0 || dupCount > 0) {
        alertMsg += "\n\n──────────────────\n상세 내역:";
        results.forEach(r => {
          if (r.status === "duplicate") alertMsg += `\n⚠️ [중복 업로드 방지] ${r.filename}`;
          if (r.status === "error") alertMsg += `\n❌ [업로드 실패] ${r.filename}: ${r.errorMsg}`;
        });
      }
      alert(alertMsg);
      fetchDocuments();
    } catch (err: any) { alert(err.message || "파일 업로드 과정에서 오류가 발생했습니다."); }
  };

  const handleRetryAnalysis = async (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    try {
      const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const res = await fetch(`${API_BASE_URL}/upload/analyze`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ document_id: doc.document_id, filename: doc.filename, file_hash: doc.file_hash || "" })
      });
      if (!res.ok) throw new Error("재분석 요청 실패");
      alert("🔄 AI 분석을 다시 시작했습니다!");
      fetchDocuments();
    } catch (err: any) { alert(`재분석 시작 실패: ${err.message}`); }
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
    } catch (err: any) { alert(err.message || "대화 세션 생성에 실패했습니다."); }
  };

  const handleDeleteSession = async (e: React.MouseEvent, sessionId: string) => {
    e.stopPropagation();
    if (confirm("이 대화를 삭제하시겠습니까?")) {
      try { await deleteSession(sessionId); }
      catch (err: any) { alert(err.message || "대화 삭제에 실패했습니다."); }
    }
  };

  const handleDeleteDoc = async (e: React.MouseEvent, docId: string) => {
    e.stopPropagation();
    if (confirm("이 문서를 삭제하시겠습니까? 관련 데이터가 모두 영구 제거됩니다.")) await deleteDoc(docId);
  };

  const handleStartRename = (e: React.MouseEvent, doc: Document) => {
    e.stopPropagation();
    setEditingDocId(doc.document_id); setEditingMfg(doc.manufacturer || "");
    setEditingModel(doc.model_series || ""); setEditingName(getDisplayFilename(doc));
  };

  const handleSaveMeta = async (docId: string) => {
    const trimmedName = editingName.trim();
    if (!trimmedName) { alert("문서 제목은 필수입니다."); return; }
    try {
      await updateDocMeta(docId, { filename: trimmedName, manufacturer: editingMfg.trim() || undefined, model_series: editingModel.trim() || undefined });
      setEditingDocId(null);
    } catch (err: any) { alert(err.message || "메타데이터 수정에 실패했습니다."); }
  };

  const handleBatchDelete = async (e: React.MouseEvent, docs: Document[], groupLabel: string) => {
    e.stopPropagation();
    const targetDocs = docs.filter(d => d.status !== "analyzing");
    if (targetDocs.length === 0) return;
    if (!confirm(`"${groupLabel}" 그룹의 문서 ${targetDocs.length}개를 모두 삭제하시겠습니까?\n이 작업은 되돌릴 수 없습니다.`)) return;
    for (const doc of targetDocs) await deleteDoc(doc.document_id);
  };

  const handleBatchDownload = async (e: React.MouseEvent, docs: Document[], groupLabel: string) => {
    e.stopPropagation();
    const targetDocs = docs.filter(d => d.status !== "analyzing" && d.status !== "error");
    if (targetDocs.length === 0) { alert("다운로드 가능한 문서가 없습니다."); return; }
    if (!confirm(`"${groupLabel}" 그룹의 문서 ${targetDocs.length}개를 순차 다운로드합니다.`)) return;
    for (const doc of targetDocs) { await downloadDoc(doc.document_id); await new Promise(r => setTimeout(r, 500)); }
  };

  const [isReclassifying, setIsReclassifying] = useState(false);
  const handleReclassify = async (e: React.MouseEvent) => {
    e.stopPropagation(); if (isReclassifying) return;
    setIsReclassifying(true);
    try {
      const result = await api.reclassifyDocuments();
      alert(result.message);
      if (result.count > 0) {
        setTimeout(() => fetchDocuments(), result.count * 2000 + 3000);
        setTimeout(() => fetchDocuments(), Math.min(result.count * 1000, 15000));
      }
    } catch (err: any) { alert(err.message || "재분류 요청에 실패했습니다."); }
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

  const getGroupedDocs = (docs: Document[]) => {
    const grouped: Record<string, Record<string, Document[]>> = {};
    docs.forEach((doc) => {
      if (doc.status === "analyzing") return;
      const mfg = doc.manufacturer || "미분류"; const model = doc.model_series || "미분류";
      if (!grouped[mfg]) grouped[mfg] = {}; if (!grouped[mfg][model]) grouped[mfg][model] = [];
      grouped[mfg][model].push(doc);
    });
    return grouped;
  };

  const groupedDocs = getGroupedDocs(filteredDocuments);

  const renderSingleDocItem = (doc: Document) => {
    const isEditing = editingDocId === doc.document_id;
    return (
      <div key={doc.document_id} className="doc-item group flex flex-col gap-1.5 px-2.5 py-2 rounded-xl hover:bg-accent/40 transition-all border border-transparent hover:border-border/20 bg-accent/5">
        {isEditing ? (
          <div className="w-full space-y-2.5 p-2.5 bg-background/60 rounded-xl border border-border/30 shadow-inner" onClick={e => e.stopPropagation()}>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">제조사</label>
              <input type="text" list="manufacturers-list" placeholder="제조사" value={editingMfg} onChange={e => setEditingMfg(e.target.value)} className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded-full border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">모델 시리즈</label>
              <input type="text" placeholder="모델 시리즈" value={editingModel} onChange={e => setEditingModel(e.target.value)} className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded-full border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs" />
            </div>
            <div className="space-y-1">
              <label className="text-[10px] md:text-[9px] font-semibold text-muted-foreground/80">문서 제목</label>
              <input type="text" placeholder="문서 제목" value={editingName} onChange={e => setEditingName(e.target.value)} className="w-full bg-accent/20 text-foreground px-2.5 py-1.5 md:px-2 md:py-1 rounded-full border border-border/50 focus:outline-none focus:border-primary/50 text-base md:text-xs" />
            </div>
            <div className="flex justify-end gap-1.5 pt-1">
              <button onClick={() => setEditingDocId(null)} className="px-3 py-1.5 md:px-2 md:py-0.5 text-[11px] md:text-[10px] font-medium rounded-full hover:bg-accent text-muted-foreground transition-colors">취소</button>
              <button onClick={() => handleSaveMeta(doc.document_id)} className="px-3.5 py-1.5 md:px-2.5 md:py-0.5 text-[11px] md:text-[10px] font-medium bg-primary text-white rounded-full hover:bg-primary/90 flex items-center gap-1 transition-colors shadow-sm"><Check className="w-3 h-3 md:w-2.5 md:h-2.5" /> 저장</button>
            </div>
          </div>
        ) : (
          <div className="flex items-start gap-2">
            <div className={`w-6 h-6 rounded-full flex items-center justify-center flex-shrink-0 mt-0.5 ${
              doc.status === "analyzing" ? "bg-amber-500/10 text-amber-500" : doc.status === "error" ? "bg-destructive/10 text-destructive" : "bg-primary/10 text-primary/70"
            }`}>
              {doc.status === "analyzing" ? <Loader2 className="w-3 h-3 animate-spin" /> : doc.status === "error" ? <AlertCircle className="w-3 h-3" /> : <FileText className="w-3 h-3" />}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-xs md:text-[11px] font-medium text-foreground/80 group-hover:text-foreground line-clamp-3 break-all leading-tight pr-1">{getDisplayFilename(doc)}</p>
              <div className="flex flex-wrap gap-1 mt-1 text-[9px] text-muted-foreground/50">
                {doc.status === "analyzing" ? <span className="text-amber-500 font-semibold animate-pulse flex items-center gap-0.5">🤖 AI 분석 중...</span> : doc.status === "error" ? <span title={(doc as any).error_message || "분석 에러"} className="text-destructive font-semibold cursor-help">❌ 분석 실패</span> : <><span>{doc.total_pages}p</span>{doc.manufacturer && <span className="bg-primary/5 px-1 rounded-full text-primary/80 truncate max-w-[60px]">{doc.manufacturer}</span>}{doc.model_series && <span className="bg-blue-500/5 px-1 rounded-full text-blue-500/80 truncate max-w-[60px]">{doc.model_series}</span>}</>}
              </div>
            </div>
            <div className="flex items-center gap-0.5 shrink-0 self-start">
              {doc.status === "error" && <button onClick={(e) => handleRetryAnalysis(e, doc)} title="재분석" className="p-1 rounded-full hover:bg-amber-500/20 text-amber-500 transition-all animate-pulse"><RotateCw className="w-3 h-3" /></button>}
              {doc.status !== "analyzing" && doc.status !== "error" && <button onClick={(e) => handleDownloadDoc(e, doc)} title="다운로드" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-3 h-3" /></button>}
              {doc.status !== "analyzing" && doc.status !== "error" && <button onClick={(e) => handleStartRename(e, doc)} title="수정" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Pencil className="w-3 h-3" /></button>}
              <button onClick={(e) => handleDeleteDoc(e, doc.document_id)} title="삭제" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-3 h-3" /></button>
            </div>
          </div>
        )}
      </div>
    );
  };

  const renderDocumentList = () => {
    const completedFilteredDocs = filteredDocuments.filter(d => d.status !== "analyzing");
    const completedDocs = documents.filter(d => d.status !== "analyzing");

    if (completedFilteredDocs.length === 0) {
      return <p className="text-[11px] text-muted-foreground/40 px-3 py-3 text-center">{searchQuery ? "검색 결과가 없습니다" : "업로드된 문서가 없습니다"}</p>;
    }

    if (completedDocs.length <= 3 || completedFilteredDocs.length <= 3) {
      const sortedFlatDocs = [...completedFilteredDocs].sort((a, b) => sortBy === "latest" ? sortByDate(a, b) : sortByName(getDisplayFilename(a), getDisplayFilename(b)));
      return <div className="space-y-1">{sortedFlatDocs.map((doc) => renderSingleDocItem(doc))}</div>;
    }

    const sortedManufacturers = Object.entries(groupedDocs).sort(([mfgA, modelsA], [mfgB, modelsB]) => {
      if (mfgA === "미분류") return 1; if (mfgB === "미분류") return -1;
      if (sortBy === "latest") return getLatestDateInDocs(Object.values(modelsB).flat()) - getLatestDateInDocs(Object.values(modelsA).flat());
      return sortByName(mfgA, mfgB);
    });

    return (
      <div className="space-y-2.5">
        {sortedManufacturers.map(([mfg, models]) => {
          const isMfgExpanded = !!expandedManufacturers[mfg];
          return (
            <div key={mfg} className="space-y-1">
              <div className="group/mfg flex items-center gap-0.5">
                <button onClick={() => toggleManufacturer(mfg)} className="flex-1 min-w-0 flex items-center justify-between text-xs font-semibold text-foreground/80 hover:text-foreground hover:bg-accent/30 py-1.5 px-2 rounded-xl transition-all">
                  <div className="flex items-center gap-1.5 truncate">
                    {mfg === "미분류" ? <Folder className="w-3.5 h-3.5 text-muted-foreground/60 shrink-0" /> : <Building className="w-3.5 h-3.5 text-primary/70 shrink-0" />}
                    <span className="truncate">{mfg}</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <span className="text-[10px] text-muted-foreground/50 font-normal">({Object.values(models).flat().length})</span>
                    {isMfgExpanded ? <ChevronDown className="w-3 h-3 text-muted-foreground/60 shrink-0" /> : <ChevronRight className="w-3 h-3 text-muted-foreground/60 shrink-0" />}
                  </div>
                </button>
                <div className="flex items-center gap-0.5 opacity-0 group-hover/mfg:opacity-100 transition-opacity shrink-0">
                  {mfg === "미분류" && <button onClick={handleReclassify} disabled={isReclassifying} className="p-1 rounded-full hover:bg-primary/20 text-muted-foreground/40 hover:text-primary transition-all"><RefreshCw className={`w-3 h-3 ${isReclassifying ? "animate-spin" : ""}`} /></button>}
                  <button onClick={(e) => handleBatchDownload(e, Object.values(models).flat(), mfg)} className="p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-3 h-3" /></button>
                  <button onClick={(e) => handleBatchDelete(e, Object.values(models).flat(), mfg)} className="p-1 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-3 h-3" /></button>
                </div>
              </div>
              {isMfgExpanded && (
                <div className="pl-3.5 border-l border-border/40 ml-3.5 space-y-1 pt-0.5">
                  {Object.entries(models).sort(([modelA, docsA], [modelB, docsB]) => {
                    if (modelA === "미분류") return 1; if (modelB === "미분류") return -1;
                    if (sortBy === "latest") return getLatestDateInDocs(docsB) - getLatestDateInDocs(docsA);
                    return sortByName(modelA, modelB);
                  }).map(([model, docs]) => {
                    const isModelExpanded = !!expandedModels[`${mfg}-${model}`];
                    return (
                      <div key={model} className="space-y-0.5">
                        <div className="group/model flex items-center gap-0.5">
                          <button onClick={() => toggleModel(`${mfg}-${model}`)} className="flex-1 min-w-0 flex items-center justify-between text-[11px] font-medium text-foreground/70 hover:text-foreground hover:bg-accent/30 py-1 px-1.5 rounded-xl transition-all">
                            <div className="flex items-center gap-1 truncate"><Cpu className="w-3 h-3 text-blue-500/60 shrink-0" /><span className="truncate">{model}</span></div>
                            <div className="flex items-center gap-1"><span className="text-[9px] text-muted-foreground/50 font-normal">({docs.length})</span>{isModelExpanded ? <ChevronDown className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" /> : <ChevronRight className="w-2.5 h-2.5 text-muted-foreground/60 shrink-0" />}</div>
                          </button>
                          <div className="flex items-center gap-0.5 opacity-0 group-hover/model:opacity-100 transition-opacity shrink-0">
                            <button onClick={(e) => handleBatchDownload(e, docs, `${mfg} > ${model}`)} className="p-0.5 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-2.5 h-2.5" /></button>
                            <button onClick={(e) => handleBatchDelete(e, docs, `${mfg} > ${model}`)} className="p-0.5 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-2.5 h-2.5" /></button>
                          </div>
                        </div>
                        {isModelExpanded && (
                          <div className="pl-2 space-y-0.5 pt-0.5">
                            {[...docs].sort((a, b) => sortBy === "latest" ? sortByDate(a, b) : sortByName(getDisplayFilename(a), getDisplayFilename(b))).map((doc) => renderSingleDocItem(doc))}
                          </div>
                        )}
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
    );
  };

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
        <input type="file" accept="application/pdf" multiple className="hidden" ref={fileInputRef} onChange={handleFileUpload} />
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
            <span className="truncate text-[13px] font-semibold">{isUploading ? `업로드 중... (${uploadingIndex + 1}/${uploadTotal})` : "PDF 매뉴얼 업로드"}</span>
          </div>
        </button>

        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-muted-foreground/50" />
          <input type="text" placeholder="검색 (이름, 제조사, 모델)..." value={searchQuery} onChange={(e) => setSearchQuery(e.target.value)} className="w-full pl-9 pr-8 py-1.5 text-[12px] rounded-full bg-accent/20 border border-border/20 focus:border-primary/50 focus:bg-accent/10 focus:outline-none transition-all placeholder-muted-foreground/40" />
          {searchQuery && <button onClick={() => setSearchQuery("")} className="absolute right-2 top-1/2 -translate-y-1/2 p-0.5 rounded-full hover:bg-accent/70 text-muted-foreground/50"><X className="w-2.5 h-2.5" /></button>}
        </div>
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-3 pb-1">
        <div className="flex items-center justify-between px-2 py-1 mb-2">
          <div className="flex items-center gap-1.5 text-[10px] font-semibold text-muted-foreground/70 tracking-widest">
            <FileText className="w-3 h-3" /> 업로드된 문서
          </div>
          <div className="flex items-center gap-1 bg-accent/20 p-0.5 rounded-md border border-border/10 shrink-0">
            <button onClick={() => setSortBy("latest")} className={`text-[9px] px-1.5 py-0.5 rounded transition-all font-medium ${sortBy === "latest" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground/50 hover:text-foreground"}`}>최신순</button>
            <button onClick={() => setSortBy("name")} className={`text-[9px] px-1.5 py-0.5 rounded transition-all font-medium ${sortBy === "name" ? "bg-background text-foreground shadow-sm font-semibold" : "text-muted-foreground/50 hover:text-foreground"}`}>이름순</button>
          </div>
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
        <div className="px-1">{renderDocumentList()}</div>
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
          <p className="text-sm font-bold text-primary">PDF를 놓아 업로드하세요</p>
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
