import { create } from 'zustand';
import { api } from '@/lib/api';

export interface Document {
  document_id: string;
  filename: string;
  total_pages: number;
  uploaded_at?: string;
  status: string;
}

interface DocumentStore {
  documents: Document[];
  isUploading: boolean;
  fetchDocuments: () => Promise<void>;
  uploadDocument: (file: File) => Promise<Document>;
}

export const useDocumentStore = create<DocumentStore>((set) => ({
  documents: [],
  isUploading: false,
  
  fetchDocuments: async () => {
    try {
      const data = await api.getDocuments();
      set({ documents: data.documents || [] });
    } catch (error) {
      console.error('Failed to fetch documents:', error);
    }
  },
  
  uploadDocument: async (file: File) => {
    set({ isUploading: true });
    try {
      const data = await api.uploadDocument(file);
      // 업로드 성공 후 목록에 추가
      set((state) => ({ 
        documents: [data, ...state.documents],
        isUploading: false 
      }));
      return data;
    } catch (error) {
      set({ isUploading: false });
      throw error;
    }
  }
}));
