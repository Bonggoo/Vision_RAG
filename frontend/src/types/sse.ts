/**
 * /chat/stream SSE 이벤트 타입 (M8)
 * page.tsx 의 스트림 파서가 처리하는 `data.type` 별 페이로드를 역설계해 정의.
 * (런타임 연결은 후속 작업(M5: useChatStream 훅 분리)에서 적용)
 */
import type { ClarificationCandidate } from './chat';

/** AI 추론 과정 한 줄 */
export interface SSEReasoningEvent {
  type: 'reasoning';
  content: string;
}

/** 참조 페이지 썸네일 */
export interface SSEReferenceEvent {
  type: 'reference';
  page_number: number;
  image_base64?: string;
  document_id?: string;
  document_name?: string;
}

/** 답변 본문 청크 */
export interface SSEAnswerEvent {
  type: 'answer';
  content: string;
}

/** 되묻기 (문서 후보 + 보강 질문) */
export interface SSEClarificationEvent {
  type: 'clarification';
  content: string;
  candidates?: ClarificationCandidate[];
  suggested_questions?: string[];
}

/** 오류 메시지 */
export interface SSEErrorEvent {
  type: 'error';
  content: string;
}

/** 스트림 종료 */
export interface SSEDoneEvent {
  type: 'done';
}

/** /chat/stream 이 내보내는 모든 SSE 이벤트의 판별 유니온 */
export type SSEEvent =
  | SSEReasoningEvent
  | SSEReferenceEvent
  | SSEAnswerEvent
  | SSEClarificationEvent
  | SSEErrorEvent
  | SSEDoneEvent;
