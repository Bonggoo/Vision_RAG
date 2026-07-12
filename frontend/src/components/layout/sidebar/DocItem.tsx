"use client";

import React from "react";
import { Loader2, FileText, Trash2, Pencil, Check, Download, AlertCircle, RotateCw } from "lucide-react";
import { Document } from "@/store/useDocumentStore";
import { getDisplayFilename } from "./utils";

/**
 * 단일 문서 항목 (M5 분해) — 기존 Sidebar.renderSingleDocItem 을 그대로 추출.
 * 인라인 메타데이터 수정 폼(제조사/모델/제목) + 다운로드/수정/삭제/재분석 액션을 포함한다.
 * 편집 상태(editing*)는 Sidebar 가 소유하고 props 로 내려준다.
 */
export default function DocItem({
  doc,
  isEditing,
  editingMfg, setEditingMfg,
  editingModel, setEditingModel,
  editingName, setEditingName,
  onSave,
  onCancel,
  onRetry,
  onDownload,
  onStartRename,
  onDelete,
}: {
  doc: Document;
  isEditing: boolean;
  editingMfg: string;
  setEditingMfg: (value: string) => void;
  editingModel: string;
  setEditingModel: (value: string) => void;
  editingName: string;
  setEditingName: (value: string) => void;
  onSave: (docId: string) => void;
  onCancel: () => void;
  onRetry: (e: React.MouseEvent, doc: Document) => void;
  onDownload: (e: React.MouseEvent, doc: Document) => void;
  onStartRename: (e: React.MouseEvent, doc: Document) => void;
  onDelete: (e: React.MouseEvent, docId: string) => void;
}) {
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
            <button onClick={() => onCancel()} className="px-3 py-1.5 md:px-2 md:py-0.5 text-[11px] md:text-[10px] font-medium rounded-full hover:bg-accent text-muted-foreground transition-colors">취소</button>
            <button onClick={() => onSave(doc.document_id)} className="px-3.5 py-1.5 md:px-2.5 md:py-0.5 text-[11px] md:text-[10px] font-medium bg-primary text-white rounded-full hover:bg-primary/90 flex items-center gap-1 transition-colors shadow-sm"><Check className="w-3 h-3 md:w-2.5 md:h-2.5" /> 저장</button>
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
              {doc.status === "analyzing" ? <span className="text-amber-500 font-semibold animate-pulse flex items-center gap-0.5">🤖 AI 분석 중...</span> : doc.status === "error" ? <span title={(doc as any).error_message || "분석 에러"} className="text-destructive font-semibold cursor-help">❌ 분석 실패</span> : <><span>{doc.total_pages}p</span>{doc.manufacturer && <span className="bg-primary/5 px-1 rounded-full text-primary/80 truncate max-w-[60px]">{doc.manufacturer}</span>}{doc.model_series && <span className="bg-blue-500/5 px-1 rounded-full text-blue-500/80 truncate max-w-[60px]">{doc.model_series}</span>}{(doc.similar_documents?.length ?? 0) > 0 && <span title={`유사한 기존 문서 ${doc.similar_documents!.length}건: ${doc.similar_documents!.map(s => s.filename).join(", ")}\n중복이면 삭제를 고려하세요.`} className="bg-amber-500/10 px-1 rounded-full text-amber-600/90 cursor-help flex items-center gap-0.5">🔁 유사 {doc.similar_documents!.length}</span>}</>}
            </div>
          </div>
          <div className="flex items-center gap-0.5 shrink-0 self-start">
            {doc.status === "error" && <button onClick={(e) => onRetry(e, doc)} title="재분석" className="p-1 rounded-full hover:bg-amber-500/20 text-amber-500 transition-all animate-pulse"><RotateCw className="w-3 h-3" /></button>}
            {doc.status !== "analyzing" && doc.status !== "error" && <button onClick={(e) => onDownload(e, doc)} title="다운로드" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Download className="w-3 h-3" /></button>}
            {doc.status !== "analyzing" && doc.status !== "error" && <button onClick={(e) => onStartRename(e, doc)} title="수정" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-accent/60 text-muted-foreground/40 hover:text-foreground transition-all"><Pencil className="w-3 h-3" /></button>}
            <button onClick={(e) => onDelete(e, doc.document_id)} title="삭제" className="md:opacity-0 group-hover:opacity-100 p-1 rounded-full hover:bg-destructive/20 text-muted-foreground/40 hover:text-destructive transition-all"><Trash2 className="w-3 h-3" /></button>
          </div>
        </div>
      )}
    </div>
  );
}
