import { useAuthStore } from "@/store/useAuthStore";

const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
export { API_BASE_URL };

/** API 요청에 JWT 토큰 헤더 추가하는 헬퍼 */
function getAuthHeaders(headers: Record<string, string> = {}): Record<string, string> {
  const token = useAuthStore.getState().token;
  if (token) {
    return {
      ...headers,
      "Authorization": `Bearer ${token}`
    };
  }
  return headers;
}

// 토큰 갱신 동시 요청 방지를 위한 플래그 및 대기열
let isRefreshing = false;
let refreshSubscribers: Array<(token: string) => void> = [];

/** 리프레시 토큰으로 새 액세스 토큰 발급 시도 */
async function tryRefreshToken(): Promise<string | null> {
  // 이미 갱신 중이면 대기열에 추가
  if (isRefreshing) {
    return new Promise((resolve) => {
      refreshSubscribers.push(resolve);
    });
  }

  isRefreshing = true;
  try {
    // 💡 credentials: "include"로 쿠키 자동 전송
    const res = await fetch(`${API_BASE_URL}/api/auth/refresh`, {
      method: "POST",
      credentials: "include",
    });

    if (!res.ok) return null;

    const data = await res.json();
    // 스토어에 새 Access Token 저장
    useAuthStore.setState({
      token: data.access_token,
    });

    // 대기 중인 요청들에 새 토큰 전달
    refreshSubscribers.forEach((cb) => cb(data.access_token));
    refreshSubscribers = [];

    return data.access_token;
  } catch {
    return null;
  } finally {
    isRefreshing = false;
  }
}

/** fetch 래퍼: 401 응답 시 토큰 갱신 후 자동 재시도 */
async function authFetch(url: string, options: RequestInit = {}): Promise<Response> {
  const headers = getAuthHeaders((options.headers as Record<string, string>) || {});
  const fetchOptions: RequestInit = {
    ...options,
    headers,
    credentials: "include" // 크로스 오리진 쿠키 공유를 위해 필수 지정
  };
  let res = await fetch(url, fetchOptions);

  if (res.status === 401) {
    const newToken = await tryRefreshToken();
    if (newToken) {
      const newHeaders = getAuthHeaders((options.headers as Record<string, string>) || {});
      newHeaders["Authorization"] = `Bearer ${newToken}`;
      res = await fetch(url, { ...fetchOptions, headers: newHeaders });
    } else {
      useAuthStore.getState().logout();
    }
  }
  return res;
}

export { authFetch };

/** 파일의 SHA-256 해시 계산 (Web Crypto API 사용) */
async function calculateFileHash(file: File): Promise<string> {
  const buffer = await file.arrayBuffer();
  const hashBuffer = await crypto.subtle.digest("SHA-256", buffer);
  const hashArray = Array.from(new Uint8Array(hashBuffer));
  return hashArray.map(b => b.toString(16).padStart(2, "0")).join("");
}

/** GCS Signed URL로 파일 직접 업로드 (진행률 추적) - OAuth 대상 아님 */
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

// 문서 목록 API용 ETag 캐시 변수
let _lastDocEtag: string | null = null;
let _lastDocData: any = null;

export const api = {
  /** PDF 문서 업로드 (비동기 GCS Direct 업로드 및 분석 트리거) */
  uploadDocument: async (file: File, onProgress?: (progress: number) => void): Promise<any> => {
    try {
      console.log(`[Upload] 비동기 GCS Direct 업로드 모드 시작 (${(file.size / 1024 / 1024).toFixed(2)}MB)`);
      
      // 1. 사전 해시 계산
      const fileHash = await calculateFileHash(file);
      
      // 2. Pre-flight 검증 API 호출
      const preflightRes = await authFetch(`${API_BASE_URL}/upload/preflight`, {
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
      const analyzeRes = await authFetch(`${API_BASE_URL}/upload/analyze`, {
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
      
      // JWT 토큰 주입
      const token = useAuthStore.getState().token;
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }
      
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
    const headers: Record<string, string> = {};
    if (_lastDocEtag) {
      headers["If-None-Match"] = _lastDocEtag;
    }

    const res = await authFetch(`${API_BASE_URL}/documents`, { headers });

    // 304 Not Modified 이고 로컬 캐시 데이터가 있으면 캐시 반환
    if (res.status === 304 && _lastDocData) {
      return _lastDocData;
    }

    if (!res.ok) throw new Error("Failed to fetch documents");

    // ETag 헤더 추출 및 저장
    const etag = res.headers.get("etag") || res.headers.get("ETag");
    if (etag) {
      _lastDocEtag = etag;
    }

    const data = await res.json();
    _lastDocData = data;
    return data;
  },

  /** 문서 메타데이터 수정 */
  updateDocumentMeta: async (docId: string, data: {
    filename?: string;
    manufacturer?: string;
    model_series?: string;
    doc_type?: string;
  }) => {
    const res = await authFetch(`${API_BASE_URL}/documents/${docId}`, {
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
    const res = await authFetch(`${API_BASE_URL}/documents/${docId}`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error("Failed to delete document");
    return res.json();
  },

  /** 문서 다운로드 */
  downloadDocument: async (docId: string) => {
    const res = await authFetch(`${API_BASE_URL}/documents/${docId}/download-url`);
    if (!res.ok) throw new Error("문서 다운로드에 실패했습니다.");
    const data = await res.json();
    
    if (data.mode === "gcs") {
      // GCS 모드일 때는 Signed URL을 브라우저에 그대로 위임 (서명이 쿼리에 포함되어 헤더 불필요)
      const a = document.createElement("a");
      a.href = data.url;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
    } else {
      // 로컬 모드일 때는 인증 헤더를 동반하여 파일 바이너리를 직접 가져와 다운로드
      const fileRes = await authFetch(`${API_BASE_URL}${data.url}`);
      if (!fileRes.ok) throw new Error("문서 파일 다운로드에 실패했습니다.");
      
      const blob = await fileRes.blob();
      const blobUrl = window.URL.createObjectURL(blob);
      
      const a = document.createElement("a");
      a.href = blobUrl;
      a.download = data.filename;
      document.body.appendChild(a);
      a.click();
      
      // 메모리 유수 방지를 위해 해제
      window.URL.revokeObjectURL(blobUrl);
      document.body.removeChild(a);
    }
  },

  /** 미분류 문서 일괄 재분류 */
  reclassifyDocuments: async (): Promise<{ status: string; message: string; count: number }> => {
    const res = await authFetch(`${API_BASE_URL}/documents/reclassify`, {
      method: "POST",
    });
    if (!res.ok) throw new Error("재분류 요청에 실패했습니다.");
    return res.json();
  },
};
