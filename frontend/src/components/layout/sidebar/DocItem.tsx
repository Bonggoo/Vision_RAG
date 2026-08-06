"use client";

import React from "react";
import {
  Loader2,
  FileText,
  Trash2,
  Pencil,
  Check,
  Download,
  AlertCircle,
  RotateCw,
} from "lucide-react";
import { Document } from "@/store/useDocumentStore";
import type { DocMetaDraft } from "@/hooks/useDocumentActions";
import { getDisplayFilename } from "./utils";

interface DocItemProps {
  doc: Document;
  isEditing: boolean;
  draft: DocMetaDraft;
  onDraftChange: (draft: DocMetaDraft) => void;
  onSave: (docId: string) => void;
  onCancel: () => void;
  onRetry: (doc: Document) => void;
  onDownload: (doc: Document) => void;
  onStartRename: (doc: Document) => void;
  onDelete: (docId: string) => void;
}

const FIELD_CLASS =
  "w-full bg-background text-foreground px-2.5 py-1.5 rounded-md border border-border " +
  "focus:outline-none focus:border-primary text-base md:text-[12px]";

const ICON_BTN_CLASS =
  "btn-ghost p-1.5 rounded-md md:opacity-0 md:group-hover:opacity-100 md:focus-visible:opacity-100";

/** 사이드바의 단일 문서 항목 — 상태 배지 + 인라인 메타데이터 수정 폼 */
export default function DocItem({
  doc,
  isEditing,
  draft,
  onDraftChange,
  onSave,
  onCancel,
  onRetry,
  onDownload,
  onStartRename,
  onDelete,
}: DocItemProps) {
  const isAnalyzing = doc.status === "analyzing";
  const isError = doc.status === "error";
  const isReady = !isAnalyzing && !isError;

  if (isEditing) {
    return (
      <form
        className="p-2.5 rounded-lg border border-border bg-[var(--surface)] space-y-2"
        onSubmit={(e) => {
          e.preventDefault();
          onSave(doc.document_id);
        }}
      >
        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">제조사</span>
          <input
            type="text"
            list="manufacturers-list"
            value={draft.manufacturer}
            onChange={(e) => onDraftChange({ ...draft, manufacturer: e.target.value })}
            className={FIELD_CLASS}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">모델 시리즈</span>
          <input
            type="text"
            value={draft.model_series}
            onChange={(e) => onDraftChange({ ...draft, model_series: e.target.value })}
            className={FIELD_CLASS}
          />
        </label>
        <label className="block space-y-1">
          <span className="text-[11px] text-muted-foreground">문서 제목</span>
          <input
            type="text"
            value={draft.filename}
            onChange={(e) => onDraftChange({ ...draft, filename: e.target.value })}
            className={FIELD_CLASS}
          />
        </label>
        <div className="flex justify-end gap-1.5 pt-0.5">
          <button
            type="button"
            onClick={onCancel}
            className="btn-ghost px-2.5 py-1 text-[12px] rounded-md"
          >
            취소
          </button>
          <button
            type="submit"
            className="btn-primary px-2.5 py-1 text-[12px] rounded-md inline-flex items-center gap-1"
          >
            <Check className="w-3 h-3" /> 저장
          </button>
        </div>
      </form>
    );
  }

  return (
    <div className="doc-item group flex items-start gap-2 px-2 py-1.5">
      <span className="mt-0.5 shrink-0 text-muted-foreground/70" aria-hidden="true">
        {isAnalyzing ? (
          <Loader2 className="w-3.5 h-3.5 animate-spin text-[var(--warning)]" />
        ) : isError ? (
          <AlertCircle className="w-3.5 h-3.5 text-destructive" />
        ) : (
          <FileText className="w-3.5 h-3.5" />
        )}
      </span>

      <div className="flex-1 min-w-0">
        <p className="text-[12.5px] text-foreground/90 line-clamp-2 break-all leading-snug">
          {getDisplayFilename(doc)}
        </p>
        <div className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 mt-0.5 text-[11px] text-muted-foreground/70">
          {isAnalyzing ? (
            <span className="text-[var(--warning)]">분석 중</span>
          ) : isError ? (
            <span className="text-destructive" title={(doc as { error_message?: string }).error_message}>
              분석 실패
            </span>
          ) : (
            <>
              <span>{doc.total_pages}p</span>
              {doc.manufacturer && <span className="truncate max-w-[70px]">{doc.manufacturer}</span>}
              {doc.model_series && <span className="truncate max-w-[70px]">{doc.model_series}</span>}
              {(doc.similar_documents?.length ?? 0) > 0 && (
                <span
                  className="text-[var(--warning)] cursor-help"
                  title={`유사 문서 ${doc.similar_documents!.length}건: ${doc.similar_documents!
                    .map((s) => s.filename)
                    .join(", ")}`}
                >
                  유사 {doc.similar_documents!.length}
                </span>
              )}
            </>
          )}
        </div>
      </div>

      <div className="flex items-center shrink-0">
        {isError && (
          <button onClick={() => onRetry(doc)} title="재분석" aria-label="재분석" className="btn-ghost p-1.5 rounded-md">
            <RotateCw className="w-3.5 h-3.5" />
          </button>
        )}
        {isReady && (
          <>
            <button onClick={() => onDownload(doc)} title="다운로드" aria-label="다운로드" className={ICON_BTN_CLASS}>
              <Download className="w-3.5 h-3.5" />
            </button>
            <button onClick={() => onStartRename(doc)} title="정보 수정" aria-label="정보 수정" className={ICON_BTN_CLASS}>
              <Pencil className="w-3.5 h-3.5" />
            </button>
          </>
        )}
        <button
          onClick={() => onDelete(doc.document_id)}
          title="삭제"
          aria-label="삭제"
          className={`${ICON_BTN_CLASS} hover:text-destructive`}
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
