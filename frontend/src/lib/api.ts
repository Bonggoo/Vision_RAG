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
    const res = await fetch(`${API_BASE_URL}/documents/${docId}/download`);
    if (!res.ok) throw new Error("문서 다운로드에 실패했습니다.");
    const blob = await res.blob();
    
    // Content-Disposition 헤더에서 파일명 추출 (UTF-8 인코딩 고려)
    const contentDisposition = res.headers.get("content-disposition");
    let filename = "document.pdf";
    
    if (contentDisposition) {
      // RFC 5987 filename*=UTF-8''... 패턴 매칭
      const utf8Match = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
      if (utf8Match && utf8Match[1]) {
        filename = decodeURIComponent(utf8Match[1]);
      } else {
        // 일반 filename="..." 패턴 매칭
        const normalMatch = contentDisposition.match(/filename="?([^";]+)"?/i);
        if (normalMatch && normalMatch[1]) {
          filename = normalMatch[1];
        }
      }
    }
    
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  },
};
