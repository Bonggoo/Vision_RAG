import { create } from "zustand";
import { api } from "@/lib/api";

export interface Document {
  document_id: string;
  filename: string;
  total_pages: number;
  uploaded_at?: string;
  status: string;
  file_hash?: string;
  manufacturer?: string;
  model_series?: string;
  doc_type?: string;
}

export interface UploadResult {
  filename: string;
  status: "success" | "duplicate" | "error";
  errorMsg?: string;
}

interface DocumentStore {
  documents: Document[];
  isUploading: boolean;
  uploadingIndex: number;
  uploadTotal: number;
  uploadProgress: number; // 💡 실제 업로드 진행률 상태 추가
  uploadResults: UploadResult[];
  
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<Document>;
  uploadDocuments: (files: File[]) => Promise<UploadResult[]>;
  updateDocMeta: (docId: string, data: {
    filename?: string;
    manufacturer?: string;
    model_series?: string;
  }) => Promise<void>;
  deleteDoc: (docId: string) => Promise<void>;
  downloadDoc: (docId: string) => Promise<void>;
}

export const useDocumentStore = create<DocumentStore>((set, get) => ({
  documents: [],
  isUploading: false,
  uploadingIndex: -1,
  uploadTotal: 0,
  uploadProgress: 0, // 💡 기본값 설정
  uploadResults: [],

  fetchDocuments: async () => {
    try {
      const data = await api.getDocuments();
      set({ documents: data.documents || [] });
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  },

  // 단일 업로드 (하위 호환)
  uploadDocument: async (file: File) => {
    set({ isUploading: true, uploadingIndex: 0, uploadTotal: 1, uploadProgress: 0, uploadResults: [] });
    try {
      if (file.size === 0) {
        throw new Error("파일이 로컬에 저장되어 있지 않거나 손상되었습니다. 파일을 확인한 후 다시 시도해 주세요.");
      }
      
      // 💡 대용량 지원을 위해 파일 제한 크기를 200MB로 완화
      const MAX_SIZE = 200 * 1024 * 1024;
      if (file.size > MAX_SIZE) {
        throw new Error("파일 크기가 200MB를 초과하여 업로드할 수 없습니다. PDF를 분할하거나 용량을 줄인 후 다시 시도해 주세요.");
      }
      
      const data = await api.uploadDocument(file, (p) => set({ uploadProgress: p }));
      set((state) => ({
        documents: [data, ...state.documents],
        isUploading: false,
        uploadingIndex: -1,
        uploadTotal: 0,
        uploadProgress: 0
      }));
      return data;
    } catch (error: any) {
      set({ isUploading: false, uploadingIndex: -1, uploadTotal: 0, uploadProgress: 0 });
      throw error;
    }
  },

  // 다중 순차 업로드
  uploadDocuments: async (files: File[]) => {
    const total = files.length;
    if (total === 0) return [];

    set({
      isUploading: true,
      uploadTotal: total,
      uploadingIndex: 0,
      uploadProgress: 0,
      uploadResults: []
    });

    const results: UploadResult[] = [];

    for (let i = 0; i < total; i++) {
      const file = files[i];
      set({ uploadingIndex: i, uploadProgress: 0 });

      // 빈 파일 감지 (0바이트)
      if (file.size === 0) {
        const errorMsg = "파일이 로컬에 저장되어 있지 않거나 손상되었습니다. 파일을 확인한 후 다시 시도해 주세요.";
        results.push({
          filename: file.name,
          status: "error",
          errorMsg
        });
        set({ uploadResults: [...results] });
        continue;
      }

      // 💡 대용량 지원을 위해 파일 제한 크기를 200MB로 완화
      const MAX_SIZE = 200 * 1024 * 1024;
      if (file.size > MAX_SIZE) {
        const errorMsg = "파일 크기가 200MB를 초과하여 업로드할 수 없습니다. PDF를 분할하거나 용량을 줄인 후 다시 시도해 주세요.";
        results.push({
          filename: file.name,
          status: "error",
          errorMsg
        });
        set({ uploadResults: [...results] });
        continue;
      }

      try {
        const uploadedDoc = await api.uploadDocument(file, (p) => set({ uploadProgress: p }));
        set((state) => ({
          documents: [uploadedDoc, ...state.documents]
        }));
        results.push({
          filename: file.name,
          status: "success"
        });
      } catch (error: any) {
        console.error(`Upload error for ${file.name}:`, error);
        
        let status: "duplicate" | "error" = "error";
        if (error.status === 409) {
          status = "duplicate";
        }
        
        results.push({
          filename: file.name,
          status,
          errorMsg: error.message || "업로드 중 오류가 발생했습니다."
        });
      }
      set({ uploadResults: [...results] });
    }

    set({
      isUploading: false,
      uploadingIndex: -1,
      uploadTotal: 0,
      uploadProgress: 0
    });

    return results;
  },

  updateDocMeta: async (docId, data) => {
    try {
      const updated = await api.updateDocumentMeta(docId, data);
      set((state) => ({
        documents: state.documents.map((d) =>
          d.document_id === docId ? { 
            ...d, 
            filename: updated.filename ?? d.filename,
            manufacturer: updated.manufacturer ?? d.manufacturer,
            model_series: updated.model_series ?? d.model_series,
            doc_type: updated.doc_type ?? d.doc_type,
          } : d
        ),
      }));
    } catch (error) {
      console.error("Failed to update document metadata:", error);
      throw error;
    }
  },

  deleteDoc: async (docId: string) => {
    try {
      await api.deleteDocument(docId);
      set((state) => ({
        documents: state.documents.filter((d) => d.document_id !== docId),
      }));
    } catch (error) {
      console.error("Failed to delete document:", error);
    }
  },

  downloadDoc: async (docId: string) => {
    try {
      await api.downloadDocument(docId);
    } catch (error) {
      console.error("Failed to download document:", error);
      alert("문서 다운로드에 실패했습니다.");
    }
  }
}));
