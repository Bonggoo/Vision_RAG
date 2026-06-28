/**
 * 채팅 도메인 공유 타입 (M8)
 * 기존 src/store/useChatStore.ts 내부에 있던 타입을 이곳으로 추출.
 * store는 여기서 import 후 하위 호환을 위해 재export 한다.
 */

/** 참조 페이지 이미지 */
export interface ReferenceImage {
  pageNumber: number;
  imageBase64?: string; // GCS 미저장 대비 선택적 필드로 변경
  documentId?: string;
  documentName?: string;
}

/** 채팅 메시지 */
export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
  /** 사용자가 업로드한 장비 알람 이미지 (Base64) */
  image?: string;
  /** AI 추론 과정 로그 (reasoning 이벤트) */
  reasoningSteps?: string[];
  /** 참조 페이지 썸네일 (reference 이벤트) */
  references?: ReferenceImage[];

  /** 이 답변이 참조한 문서 ID/명 (맥락 강화용) */
  referenceDocumentId?: string;
  referenceDocumentName?: string;
  timestamp?: string;
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
  /** 세션 소유자 이메일 (멀티테넌시 격리용, GCS 저장 기준) */
  ownerEmail?: string;
}

export interface ClarificationCandidate {
  document_id: string;
  title: string;
  manufacturer: string;
  model_series: string;
  confidence: number;
}

export interface ClarificationState {
  content: string;
  candidates: ClarificationCandidate[];
  suggested_questions?: string[];
}
