"use client";

import React, { useMemo, useRef, useState } from "react";
import { Loader2, Upload } from "lucide-react";
import { useDocumentStore, Document } from "@/store/useDocumentStore";
import { useDocumentActions } from "@/hooks/useDocumentActions";
import { processUploadFiles } from "@/lib/upload";
import { UPLOAD_ACCEPT_ATTR } from "@/lib/fileTypes";
import DocSearchBar from "./DocSearchBar";
import SortToggle from "./SortToggle";
import DocItem from "./DocItem";
import DocTree from "./DocTree";
import { getDisplayFilename } from "./utils";

/** 사이드바 "문서" 탭 — 업로드 · 검색 · 정렬 · 문서 트리 */
export default function DocsPanel() {
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [sortBy, setSortBy] = useState<"latest" | "name">("latest");
  const [expandedManufacturers, setExpandedManufacturers] = useState<Record<string, boolean>>({});
  const [expandedModels, setExpandedModels] = useState<Record<string, boolean>>({});

  const {
    documents,
    fetchDocuments,
    fetchError,
    uploadDocuments,
    isUploading,
    uploadingIndex,
    uploadTotal,
    uploadProgress,
  } = useDocumentStore();

  const actions = useDocumentActions();

  const analyzingDocs = useMemo(
    () => documents.filter((d) => d.status === "analyzing"),
    [documents]
  );

  const filteredDocuments = useMemo(() => {
    const query = searchQuery.toLowerCase().trim();
    if (!query) return documents;
    return documents.filter(
      (doc) =>
        getDisplayFilename(doc).toLowerCase().includes(query) ||
        (doc.manufacturer || "").toLowerCase().includes(query) ||
        (doc.model_series || "").toLowerCase().includes(query)
    );
  }, [documents, searchQuery]);

  // 인라인 수정 폼의 제조사 자동완성 후보
  const manufacturerOptions = useMemo(
    () => Array.from(new Set(documents.map((d) => d.manufacturer).filter(Boolean))) as string[],
    [documents]
  );

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    if (files.length > 0) await processUploadFiles(files, uploadDocuments, fetchDocuments);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  const renderDocItem = (doc: Document) => (
    <DocItem
      key={doc.document_id}
      doc={doc}
      isEditing={actions.editingDocId === doc.document_id}
      draft={actions.draft}
      onDraftChange={actions.setDraft}
      onSave={actions.saveMeta}
      onCancel={actions.cancelRename}
      onRetry={actions.handleRetryAnalysis}
      onDownload={actions.handleDownload}
      onStartRename={actions.startRename}
      onDelete={actions.handleDelete}
    />
  );

  return (
    <div className="flex-1 flex flex-col min-h-0">
      <datalist id="manufacturers-list">
        {manufacturerOptions.map((m) => (
          <option key={m} value={m} />
        ))}
      </datalist>

      <div className="px-3 py-2 space-y-2">
        <input
          type="file"
          accept={UPLOAD_ACCEPT_ATTR}
          multiple
          className="hidden"
          ref={fileInputRef}
          onChange={handleFileUpload}
        />
        <button
          onClick={() => fileInputRef.current?.click()}
          disabled={isUploading}
          className="btn-secondary w-full flex items-center gap-2 py-2 px-3 rounded-lg text-[13.5px]"
        >
          {isUploading ? (
            <Loader2 className="w-4 h-4 animate-spin shrink-0" />
          ) : (
            <Upload className="w-4 h-4 shrink-0" />
          )}
          <span className="truncate">
            {isUploading ? `업로드 중 ${uploadingIndex + 1}/${uploadTotal} · ${uploadProgress}%` : "문서 업로드"}
          </span>
        </button>

        <DocSearchBar
          value={searchQuery}
          onChange={setSearchQuery}
          onClear={() => setSearchQuery("")}
        />
      </div>

      <div className="flex-1 overflow-y-auto scrollbar-thin px-2 pb-2">
        <div className="flex items-center justify-between px-2 py-1">
          <span className="text-[11px] text-muted-foreground/70">문서</span>
          <SortToggle sortBy={sortBy} onChange={setSortBy} />
        </div>

        {analyzingDocs.length > 0 && (
          <div className="mx-1 mb-2 px-2.5 py-2 rounded-lg border border-border bg-[var(--muted)]">
            <p className="flex items-center gap-1.5 text-[11px] text-muted-foreground mb-1">
              <Loader2 className="w-3 h-3 animate-spin" aria-hidden="true" />
              AI 분석 중 {analyzingDocs.length}개
            </p>
            <ul className="space-y-0.5 max-h-28 overflow-y-auto scrollbar-thin">
              {analyzingDocs.map((doc) => (
                <li key={doc.document_id} className="text-[11.5px] text-foreground/80 truncate">
                  {getDisplayFilename(doc)}
                </li>
              ))}
            </ul>
          </div>
        )}

        <DocTree
          documents={documents}
          filteredDocuments={filteredDocuments}
          searchQuery={searchQuery}
          fetchError={fetchError}
          onRetryFetch={fetchDocuments}
          sortBy={sortBy}
          expandedManufacturers={expandedManufacturers}
          expandedModels={expandedModels}
          onToggleManufacturer={(mfg) =>
            setExpandedManufacturers((prev) => ({ ...prev, [mfg]: !prev[mfg] }))
          }
          onToggleModel={(key) => setExpandedModels((prev) => ({ ...prev, [key]: !prev[key] }))}
          isReclassifying={actions.isReclassifying}
          onReclassify={actions.handleReclassify}
          onBatchDownload={actions.handleBatchDownload}
          onBatchDelete={actions.handleBatchDelete}
          renderDocItem={renderDocItem}
        />
      </div>
    </div>
  );
}
