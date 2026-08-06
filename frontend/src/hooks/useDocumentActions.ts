"use client";

import { useCallback, useState } from "react";
import { api, authFetch, API_BASE_URL } from "@/lib/api";
import { useDocumentStore, Document } from "@/store/useDocumentStore";
import { toast, confirmDialog } from "@/store/useUIStore";
import { getDisplayFilename } from "@/components/layout/sidebar/utils";

/** 인라인 메타데이터 수정 폼의 편집 중인 값 */
export interface DocMetaDraft {
  manufacturer: string;
  model_series: string;
  filename: string;
}

const EMPTY_DRAFT: DocMetaDraft = { manufacturer: "", model_series: "", filename: "" };

/** 그룹 일괄 다운로드 시 브라우저 다운로드 차단을 피하기 위한 간격 */
const BATCH_DOWNLOAD_INTERVAL_MS = 500;

/**
 * 문서 항목/그룹에 대한 모든 사용자 액션(이름 수정·다운로드·삭제·재분석·재분류)을 모은 훅.
 * 기존에 Sidebar 컴포넌트 본문에 흩어져 있던 핸들러 9종을 그대로 옮겨온 것으로,
 * Sidebar 는 레이아웃만 담당하고 이 훅이 동작을 담당한다.
 */
export function useDocumentActions() {
  const { deleteDoc, updateDocMeta, downloadDoc, fetchDocuments } = useDocumentStore();

  const [editingDocId, setEditingDocId] = useState<string | null>(null);
  const [draft, setDraft] = useState<DocMetaDraft>(EMPTY_DRAFT);
  const [isReclassifying, setIsReclassifying] = useState(false);

  const startRename = useCallback((doc: Document) => {
    setEditingDocId(doc.document_id);
    setDraft({
      manufacturer: doc.manufacturer || "",
      model_series: doc.model_series || "",
      filename: getDisplayFilename(doc),
    });
  }, []);

  const cancelRename = useCallback(() => {
    setEditingDocId(null);
    setDraft(EMPTY_DRAFT);
  }, []);

  const saveMeta = useCallback(
    async (docId: string) => {
      const filename = draft.filename.trim();
      if (!filename) {
        toast.warning("문서 제목은 비워 둘 수 없습니다.");
        return;
      }
      try {
        await updateDocMeta(docId, {
          filename,
          manufacturer: draft.manufacturer.trim() || undefined,
          model_series: draft.model_series.trim() || undefined,
        });
        setEditingDocId(null);
        setDraft(EMPTY_DRAFT);
        toast.success("문서 정보를 저장했어요.");
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "문서 정보 수정에 실패했습니다.");
      }
    },
    [draft, updateDocMeta]
  );

  /** 다운로드 파일명: "제조사_모델_문서종류.확장자" 형태로 조합 */
  const buildDownloadName = (doc: Document) => {
    const displayFilename = getDisplayFilename(doc);
    const ext =
      doc.source_format && doc.source_format !== "pdf" ? `.${doc.source_format}` : ".pdf";
    const parts = [doc.manufacturer, doc.model_series, doc.doc_type || displayFilename].filter(
      Boolean
    );
    const base = parts.length > 0 ? parts.join("_") : displayFilename;
    return base.endsWith(ext) ? base : `${base}${ext}`;
  };

  const handleDownload = useCallback(
    async (doc: Document) => {
      const ok = await confirmDialog({
        title: "문서 다운로드",
        description: `"${buildDownloadName(doc)}" 문서를 다운로드할까요?`,
        confirmText: "다운로드",
      });
      if (ok) await downloadDoc(doc.document_id);
    },
    [downloadDoc]
  );

  const handleDelete = useCallback(
    async (docId: string) => {
      const ok = await confirmDialog({
        title: "문서 삭제",
        description: "이 문서와 관련 데이터가 모두 영구 삭제됩니다.",
        confirmText: "삭제",
        danger: true,
      });
      if (ok) await deleteDoc(docId);
    },
    [deleteDoc]
  );

  const handleRetryAnalysis = useCallback(
    async (doc: Document) => {
      try {
        const res = await authFetch(`${API_BASE_URL}/upload/analyze`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            document_id: doc.document_id,
            filename: doc.filename,
            file_hash: doc.file_hash || "",
          }),
        });
        if (!res.ok) throw new Error("재분석 요청이 거부되었습니다.");
        toast.success("AI 분석을 다시 시작했어요.");
        fetchDocuments();
      } catch (err) {
        toast.error(err instanceof Error ? err.message : "재분석을 시작하지 못했습니다.");
      }
    },
    [fetchDocuments]
  );

  const handleBatchDelete = useCallback(
    async (docs: Document[], groupLabel: string) => {
      const targets = docs.filter((d) => d.status !== "analyzing");
      if (targets.length === 0) return;

      const ok = await confirmDialog({
        title: "그룹 문서 삭제",
        description: `"${groupLabel}" 그룹의 문서 ${targets.length}개를 삭제합니다.\n이 작업은 되돌릴 수 없습니다.`,
        confirmText: `${targets.length}개 삭제`,
        danger: true,
      });
      if (!ok) return;

      let failed = 0;
      for (const doc of targets) {
        try {
          await deleteDoc(doc.document_id);
        } catch {
          failed += 1;
        }
      }
      const succeeded = targets.length - failed;
      if (failed === 0) toast.success(`문서 ${succeeded}개를 삭제했어요.`);
      else toast.warning(`${succeeded}개 삭제, ${failed}개 실패했어요. 잠시 후 다시 시도해 주세요.`);
    },
    [deleteDoc]
  );

  const handleBatchDownload = useCallback(
    async (docs: Document[], groupLabel: string) => {
      const targets = docs.filter((d) => d.status !== "analyzing" && d.status !== "error");
      if (targets.length === 0) {
        toast.info("다운로드할 수 있는 문서가 없습니다.");
        return;
      }
      const ok = await confirmDialog({
        title: "그룹 문서 다운로드",
        description: `"${groupLabel}" 그룹의 문서 ${targets.length}개를 순서대로 내려받을까요?`,
        confirmText: "다운로드",
      });
      if (!ok) return;

      for (const doc of targets) {
        await downloadDoc(doc.document_id);
        await new Promise((r) => setTimeout(r, BATCH_DOWNLOAD_INTERVAL_MS));
      }
    },
    [downloadDoc]
  );

  const handleReclassify = useCallback(async () => {
    if (isReclassifying) return;
    setIsReclassifying(true);
    try {
      const result = await api.reclassifyDocuments();
      toast.info(result.message, { title: "문서 재분류" });
      if (result.count > 0) {
        // 백엔드가 문서당 약 1~2초 걸리므로 중간/완료 시점에 두 번 갱신한다
        setTimeout(() => fetchDocuments(), Math.min(result.count * 1000, 15000));
        setTimeout(() => fetchDocuments(), result.count * 2000 + 3000);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "재분류 요청에 실패했습니다.");
    } finally {
      setIsReclassifying(false);
    }
  }, [isReclassifying, fetchDocuments]);

  return {
    editingDocId,
    draft,
    setDraft,
    startRename,
    cancelRename,
    saveMeta,
    handleDownload,
    handleDelete,
    handleRetryAnalysis,
    handleBatchDelete,
    handleBatchDownload,
    isReclassifying,
    handleReclassify,
  };
}
