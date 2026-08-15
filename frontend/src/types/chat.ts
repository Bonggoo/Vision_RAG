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

/**
 * 되묻기 카드의 표시 모드.
 * - 'ambiguous': 후보가 여럿이라 되묻는 경우. confidence 퍼센트가 선택에 도움이 된다.
 * - 'no_match' : 질문과 일치하는 문서를 못 찾은 경우. confidence 는 전부 바닥값이라
 *                퍼센트를 보여주면 '조금은 관련 있음'으로 오독되므로 숨긴다.
 */
export type ClarificationMode = 'ambiguous' | 'no_match';

export interface ClarificationState {
  content: string;
  candidates: ClarificationCandidate[];
  suggested_questions?: string[];
  mode?: ClarificationMode;
}
