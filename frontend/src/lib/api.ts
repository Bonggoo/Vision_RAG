const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

/** 파일의 SHA-256 해시 계산 (Web Crypto API 사용) */
async function calculateFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

/** GCS Signed URL로 파일 직접 업로드 (진행률 추적) */
function uploadToGCS(file: File, signedUrl: string, onProgress?: (percent: number) => void): Promise<void> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("PUT", signedUrl);
    xhr.setRequestHeader("Content-Type", "application/pdf");
    
    if (onProgress) {
      xhr.upload.onprogress = (e) => {
        if (e.lengthComputable) {
          onProgress(Math.round((e.loaded / e.total) * 100));
        }
      };
    }
    
    xhr.onload = () => {
      if (xhr.status === 200) {
        resolve();
      } else {
        reject(new Error(`GCS 다이렉트 업로드 실패 (HTTP ${xhr.status})`));
      }
    };
    
    xhr.onerror = () => reject(new Error("GCS 다이렉트 업로드 네트워크 오류"));
    xhr.send(file);
  });
}

export const api = {
  /** PDF 문서 업로드 (비동기 GCS Direct 업로드 및 분석 트리거) */
  uploadDocument: async (file: File, onProgress?: (progress: number) => void): Promise<any> => {
    try {
      console.log(`[Upload] 비동기 GCS Direct 업로드 모드 시작 (${(file.size / 1024 / 1024).toFixed(2)}MB)`);
      
      // 1. 사전 해시 계산
      const fileHash = await calculateFileHash(file);
      
      // 2. Pre-flight 검증 API 호출
      const preflightRes = await fetch(`${API_BASE_URL}/upload/preflight`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          file_hash: fileHash,
          file_size: file.size,
          filename: file.name
        })
      });
      
      if (!preflightRes.ok) {
        let errorMsg = "사전 검증 실패";
        try {
          const errData = await preflightRes.json();
          if (errData && errData.detail) errorMsg = errData.detail;
        } catch (e) {}
        
        const error = new Error(errorMsg) as any;
        error.status = preflightRes.status;
        throw error;
      }
      
      const { document_id, upload_url } = await preflightRes.json();
      
      // 3. 로컬 모드 등으로 Signed URL이 없으면 동기식 업로드로 Fallback
      if (!upload_url) {
        console.warn("[Upload] GCS Signed URL이 누락되어 동기식 업로드로 Fallback합니다.");
        return await api._uploadDocumentSync(file, onProgress);
      }
      
      // 4. GCS 다이렉트 업로드 (Phase B)
      await uploadToGCS(file, upload_url, onProgress);
      
      // 5. 비동기 AI 분석 파이프라인 트리거 (Phase C)
      const analyzeRes = await fetch(`${API_BASE_URL}/upload/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id,
          filename: file.name,
          file_hash: fileHash
        })
      });
      
      if (!analyzeRes.ok) {
        throw new Error("서버 AI 분석 요청에 실패했습니다.");
      }
      
      const analyzeData = await analyzeRes.json();
      
      // UI 호환을 위해 분석 중 임시 응답 반환
      return {
        document_id,
        filename: file.name,
        total_pages: 0,
        toc: [],
        status: "analyzing",
        file_hash: fileHash,
        uploaded_at: new Date().toISOString()
      };
      
    } catch (error: any) {
      // 409 중복 에러 등 명시적 서버 에러는 Fallback 하지 않고 전파
      if (error.status === 409) {
        throw error;
      }
      console.error("[Upload] 비동기 업로드 오류로 동기 Fallback 실행:", error);
      return await api._uploadDocumentSync(file, onProgress);
    }
  },

  /** 기존 동기 업로드 (XMLHttpRequest 기반 진행률 연동) */
  _uploadDocumentSync: async (file: File, onProgress?: (progress: number) => void): Promise<any> => {
    return new Promise((resolve, reject) => {
      const xhr = new XMLHttpRequest();
      const formData = new FormData();
      formData.append("file", file);
      
      xhr.open("POST", `${API_BASE_URL}/upload`);
      
      if (onProgress) {
        xhr.upload.onprogress = (e) => {
          if (e.lengthComputable) {
            onProgress(Math.round((e.loaded / e.total) * 100));
          }
        };
      }
      
      xhr.onload = () => {
        if (xhr.status >= 200 && xhr.status < 300) {
          try {
            resolve(JSON.parse(xhr.responseText));
          } catch (e) {
            resolve(xhr.responseText);
          }
        } else {
          let errorMsg = `업로드 실패: ${xhr.statusText}`;
          try {
            const errData = JSON.parse(xhr.responseText);
            if (errData && errData.detail) errorMsg = errData.detail;
          } catch (e) {}
          const error = new Error(errorMsg) as any;
          error.status = xhr.status;
          reject(error);
        }
      };
      
      xhr.onerror = () => reject(new Error("업로드 중 네트워크 오류가 발생했습니다."));
      xhr.send(formData);
    });
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
