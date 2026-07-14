import { toast } from "@/store/useUIStore";
import type { UploadResult } from "@/store/useDocumentStore";

/**
 * PDF 업로드 공통 처리 — 사이드바와 웰컴 온보딩 화면이 함께 사용합니다.
 * 업로드 결과를 요약해 토스트로 안내하고, 완료 후 목록을 새로고침합니다.
 */
export async function processUploadFiles(
  files: File[],
  uploadDocuments: (files: File[]) => Promise<UploadResult[]>,
  fetchDocuments: () => Promise<void>
): Promise<void> {
  try {
    const results = await uploadDocuments(files);
    const successCount = results.filter((r) => r.status === "success").length;
    const dupCount = results.filter((r) => r.status === "duplicate").length;
    const errCount = results.filter((r) => r.status === "error").length;

    // 상세 실패/중복 내역 (있을 때만)
    const details = results
      .filter((r) => r.status !== "success")
      .map((r) =>
        r.status === "duplicate"
          ? `⚠️ 이미 등록됨 · ${r.filename}`
          : `❌ 실패 · ${r.filename}${r.errorMsg ? ` (${r.errorMsg})` : ""}`
      )
      .join("\n");

    if (successCount > 0) {
      const extra = [
        dupCount > 0 ? `중복 ${dupCount}개` : "",
        errCount > 0 ? `실패 ${errCount}개` : "",
      ]
        .filter(Boolean)
        .join(", ");
      toast.success(
        `매뉴얼 ${successCount}개를 업로드했어요.${extra ? ` (${extra})` : ""}\nAI가 분석을 시작합니다.`,
        { title: "업로드 완료", duration: 4500 }
      );
    } else if (dupCount > 0 && errCount === 0) {
      toast.info(details || "이미 등록된 문서입니다.", { title: "이미 등록된 문서" });
    } else {
      toast.error(details || "업로드에 실패했습니다.", { title: "업로드 실패", duration: 6000 });
    }

    await fetchDocuments();
  } catch (err) {
    const message = err instanceof Error ? err.message : "파일 업로드 과정에서 오류가 발생했습니다.";
    toast.error(message, { title: "업로드 실패" });
  }
}
