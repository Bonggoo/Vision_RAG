import { create } from "zustand";
import { api } from "@/lib/api";

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
  deleteDoc: (docId: string) => Promise<void>;
}

export const useDocumentStore = create<DocumentStore>((set) => ({
  documents: [],
  isUploading: false,

  fetchDocuments: async () => {
    try {
      const data = await api.getDocuments();
      set({ documents: data.documents || [] });
    } catch (error) {
      console.error("Failed to fetch documents:", error);
    }
  },

  uploadDocument: async (file: File) => {
    set({ isUploading: true });
    try {
      const data = await api.uploadDocument(file);
      set((state) => ({
        documents: [data, ...state.documents],
        isUploading: false,
      }));
      return data;
    } catch (error) {
      set({ isUploading: false });
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
}));
