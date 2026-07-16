/**
 * 백엔드 REST API 응답 타입 (M8)
 * 응답 형태는 src/lib/api.ts 의 각 함수와 src/store/*.ts 의 매핑 코드를 보고 역설계함.
 */

// ─── 문서 (documents) ───────────────────────────────────────────

/** 근접 중복으로 감지된 기존 문서 참조 (감지 전용, 비차단) */
export interface SimilarDocument {
  document_id: string;
  filename: string;
  score: number;   // ToC 지문 Jaccard 유사도 (0.0~1.0)
  reason: string;  // "toc" | "metadata"
}

/** 문서 목록 항목 (GET /documents 응답의 개별 문서 / 문서 메타 수정 응답) */
export interface DocumentInfo {
  document_id: string;
  filename: string;
  original_filename?: string;
  total_pages: number;
  uploaded_at?: string;
  status: string;
  file_hash?: string;
  manufacturer?: string;
  model_series?: string;
  doc_type?: string;
  /** 업로드 원본 확장자 (예: "pdf", "docx") — 비-PDF는 서버에서 PDF로 변환됨 */
  source_format?: string;
  similar_documents?: SimilarDocument[];
}

/** GET /documents 응답 */
export interface DocumentListResponse {
  documents: DocumentInfo[];
}

/**
 * 업로드(비동기 분석 트리거 / 동기 Fallback) 응답.
 * uploadDocument 가 반환하는 임시 문서 객체를 포함하며 DocumentInfo 와 호환된다.
 */
export interface UploadDocumentResponse {
  document_id: string;
  filename: string;
  total_pages: number;
  toc?: unknown[];
  status: string;
  file_hash?: string;
  uploaded_at?: string;
  /** 업로드 원본 확장자 (예: "pdf", "docx") */
  source_format?: string;
}

// ─── 대화 (conversations) ────────────────────────────────────────

/** 대화 목록 항목 (GET /conversations/ 의 개별 항목) */
export interface ConversationInfo {
  session_id: string;
  title?: string;
  created_at?: string;
}

/** GET /conversations/ 응답 */
export interface ConversationListResponse {
  conversations: ConversationInfo[];
}

/** POST /conversations/ (대화 생성) 응답 */
export interface CreateConversationResponse {
  session_id: string;
  created_at?: string;
}

/** 대화 상세의 개별 메시지 (GET /conversations/{id} 의 messages 항목) */
export interface ConversationMessage {
  role: 'user' | 'assistant';
  content: string;
  image?: string;
  reasoning_steps?: string[];
  reference_pages?: number[];
  reference_document_id?: string;
  reference_document_name?: string;
  timestamp?: string;
}

/** GET /conversations/{id} (대화 상세) 응답 */
export interface ConversationDetail {
  title?: string;
  messages: ConversationMessage[];
}
