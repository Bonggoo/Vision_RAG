const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const api = {
  /** PDF 문서 업로드 */
  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    const res = await fetch(`${API_BASE_URL}/upload`, {
      method: "POST",
      body: formData,
    });
    if (!res.ok) {
      let errorMsg = `업로드 실패: ${res.statusText}`;
      try {
        const errData = await res.json();
        if (errData && errData.detail) {
          errorMsg = errData.detail;
        }
      } catch (e) {}
      const error = new Error(errorMsg) as any;
      error.status = res.status;
      throw error;
    }
    return res.json();
  },

  /** 전체 문서 목록 조회 */
  getDocuments: async () => {
    const res = await fetch(`${API_BASE_URL}/documents`);
    if (!res.ok) throw new Error("Failed to fetch documents");
    return res.json();
  },

  /** 문서 메타데이터 수정 */
  updateDocumentMeta: async (docId: string, data: {
    filename?: string;
    manufacturer?: string;
    model_series?: string;
  }) => {
    const res = await fetch(`${API_BASE_URL}/documents/${docId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    if (!res.ok) {
      let errorMsg = "메타데이터 수정 실패";
      try {
        const errData = await res.json();
        if (errData && errData.detail) errorMsg = errData.detail;
      } catch (e) {}
      throw new Error(errorMsg);
    }
    return res.json();
  },

  /** 문서 삭제 */
  deleteDocument: async (docId: string) => {
    const res = await fetch(`${API_BASE_URL}/documents/${docId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete document");
    return res.json();
  },

  /** 문서 다운로드 */
  downloadDocument: async (docId: string) => {
    const res = await fetch(`${API_BASE_URL}/documents/${docId}/download-url`);
    if (!res.ok) throw new Error("문서 다운로드에 실패했습니다.");
    const data = await res.json();
    
    const downloadUrl = data.mode === "gcs" ? data.url : `${API_BASE_URL}${data.url}`;
    
    // a 태그를 생성하여 직접 다운로드 트리거 (Safari 팝업 차단 예방 및 cross-origin 대응)
    const a = document.createElement("a");
    a.href = downloadUrl;
    a.download = data.filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
  },
};
