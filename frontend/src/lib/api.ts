const API_BASE_URL = process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000';

export const api = {
  // 문서 업로드
  uploadDocument: async (file: File) => {
    const formData = new FormData();
    formData.append('file', file);
    
    const res = await fetch(`${API_BASE_URL}/upload`, {
      method: 'POST',
      body: formData,
    });
    
    if (!res.ok) {
      throw new Error(`Upload failed: ${res.statusText}`);
    }
    return res.json();
  },
  
  // 전체 문서 목록 조회
  getDocuments: async () => {
    const res = await fetch(`${API_BASE_URL}/documents`);
    if (!res.ok) {
      throw new Error('Failed to fetch documents');
    }
    return res.json();
  },
  
  // 스트리밍 채팅 시작은 SSE 특성상 별도 처리 (EventSource 또는 fetch stream)
};
