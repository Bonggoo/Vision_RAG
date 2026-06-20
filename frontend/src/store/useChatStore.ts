import { create } from 'zustand';
import { v4 as uuidv4 } from 'uuid';
import { useAuthStore } from '@/store/useAuthStore';
import { api } from '@/lib/api';

/** 참조 페이지 이미지 */
export interface ReferenceImage {
  pageNumber: number;
  imageBase64?: string; // GCS 미저장 대비 선택적 필드로 변경
  documentId?: string;
  documentName?: string;
}

/** 추천 ToC 목차 카드 */
export interface TocCard {
  title: string;
  page: number;
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
  /** 추천 ToC 목차 후보군 (toc_cards 이벤트) */
  tocCards?: TocCard[];
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
}

interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  isLoading: boolean;
  clarificationState: ClarificationState | null;

  // 되묻기 액션
  setClarification: (state: ClarificationState | null) => void;
  clearClarification: () => void;

  // GCS 비동기 API 연동
  loadSessions: () => Promise<void>;
  createSession: (title?: string) => Promise<string>;
  deleteSession: (id: string) => Promise<void>;
  loadConversation: (id: string) => Promise<void>;
  renameSession: (sessionId: string, title: string) => Promise<void>;

  // 로컬 상태 동기화 액션
  setActiveSession: (id: string) => void;
  addMessage: (sessionId: string, message: Omit<Message, 'id'>) => void;
  appendAnswerChunk: (sessionId: string, chunk: string) => void;
  appendReasoning: (sessionId: string, text: string) => void;
  appendReference: (sessionId: string, ref: ReferenceImage) => void;
  setTocCards: (sessionId: string, cards: TocCard[]) => void;
  finishStreaming: (sessionId: string) => void;
  resetActiveSession: () => void;
  clearAllSessions: () => void;
}

/** 마지막 assistant 메시지를 업데이트하는 헬퍼 */
function updateLastAssistantMessage(
  sessions: ChatSession[],
  sessionId: string,
  updater: (msg: Message) => Message,
): ChatSession[] {
  return sessions.map((session) => {
    if (session.id !== sessionId) return session;
    const msgs = [...session.messages];
    const lastIdx = msgs.length - 1;
    if (lastIdx >= 0 && msgs[lastIdx].role === 'assistant') {
      msgs[lastIdx] = updater({ ...msgs[lastIdx] });
    }
    return { ...session, messages: msgs };
  });
}

export const useChatStore = create<ChatStore>()((set, get) => ({
  sessions: [],
  activeSessionId: null,
  isLoading: false,
  clarificationState: null,

  setClarification: (clarificationState) => set({ clarificationState }),
  
  clearClarification: () => set({ clarificationState: null }),

  loadSessions: async () => {
    set({ isLoading: true });
    try {
      const email = useAuthStore.getState().user?.email;
      if (!email) return;

      const data = await api.getConversations();
      // 백엔드 응답 ConversationInfo 리스트 매핑
      const GCSsessions: ChatSession[] = (data.conversations || []).map((c: any) => ({
        id: c.session_id,
        title: c.title || '제목 없음',
        messages: [], // 목록 조회 시에는 메시지는 비워둠 (상세 조회 시 로드)
        createdAt: c.created_at ? new Date(c.created_at).getTime() : Date.now(),
        ownerEmail: email,
      }));

      set({ sessions: GCSsessions });
      
      // 만약 활성화된 세션이 세션 목록에 없고 세션 목록이 비어있지 않다면 첫 번째 세션 로드
      const activeId = get().activeSessionId;
      if (activeId && !GCSsessions.some((s) => s.id === activeId)) {
        set({ activeSessionId: null });
      }
    } catch (e) {
      // 백엔드 미배포 시 로컬 세션 유지 (기존 세션 유지)
      console.warn('⚠️ 대화 목록 로드 실패 (백엔드 미배포 가능성). 로컬 세션 유지:', e);
    } finally {
      set({ isLoading: false });
    }
  },

  createSession: async (title = '새로운 대화') => {
    const email = useAuthStore.getState().user?.email;
    if (!email) throw new Error('로그인이 필요합니다.');

    // 20개 제한 체크
    if (get().sessions.length >= 20) {
      throw new Error('대화 세션은 최대 20개까지 생성할 수 있습니다. 기존 대화를 삭제해주세요.');
    }

    let sessionId: string;
    let createdAt: number = Date.now();

    try {
      // 백엔드 API로 세션 생성 시도
      const res = await api.createConversation(title);
      sessionId = res.session_id;
      createdAt = res.created_at ? new Date(res.created_at).getTime() : Date.now();
    } catch (e) {
      // 백엔드 미배포 시 로컬 UUID로 폴백
      console.warn('⚠️ 백엔드 세션 생성 실패. 로컬 세션으로 폴백:', e);
      sessionId = uuidv4();
    }

    const newSession: ChatSession = {
      id: sessionId,
      title,
      messages: [],
      createdAt,
      ownerEmail: email,
    };

    set((state) => ({
      sessions: [newSession, ...state.sessions],
      activeSessionId: newSession.id,
    }));

    return newSession.id;
  },

  deleteSession: async (id) => {
    try {
      await api.deleteConversation(id);
    } catch (e) {
      // 백엔드 삭제 실패해도 로컬에서는 제거 (폴백)
      console.warn('⚠️ 백엔드 대화 삭제 실패. 로컬에서만 제거:', e);
    }
    set((state) => ({
      sessions: state.sessions.filter((s) => s.id !== id),
      activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
    }));
  },

  loadConversation: async (id) => {
    set({ isLoading: true });
    try {
      const email = useAuthStore.getState().user?.email;
      if (!email) return;

      const data = await api.getConversation(id);
      if (!data) return;

      // 백엔드 메시지 리스트를 프론트엔드 포맷으로 변환
      const parsedMessages: Message[] = (data.messages || []).map((msg: any) => ({
        id: uuidv4(),
        role: msg.role,
        content: msg.content,
        image: msg.image || undefined,
        reasoningSteps: msg.reasoning_steps || undefined,
        // GCS에는 imageBase64가 저장되지 않으므로 빈 썸네일 구조로 복원
        references: msg.reference_pages ? msg.reference_pages.map((pNum: number) => ({
          pageNumber: pNum,
          imageBase64: '', 
          documentId: msg.reference_document_id || undefined,
          documentName: msg.reference_document_name || undefined,
        })) : undefined,
        tocCards: msg.toc_cards ? msg.toc_cards.map((c: any) => ({
          title: c.title,
          page: c.page,
        })) : undefined,
        referenceDocumentId: msg.reference_document_id || undefined,
        referenceDocumentName: msg.reference_document_name || undefined,
        timestamp: msg.timestamp,
      }));

      set((state) => ({
        sessions: state.sessions.map((s) =>
          s.id === id ? { ...s, messages: parsedMessages, title: data.title || s.title } : s
        ),
        activeSessionId: id,
      }));
    } catch (e) {
      console.error('❌ 대화 상세 로드 실패:', e);
    } finally {
      set({ isLoading: false });
    }
  },

  renameSession: async (sessionId, title) => {
    try {
      await api.renameConversation(sessionId, title);
    } catch (e) {
      // 백엔드 실패해도 로컬 제목은 변경
      console.warn('⚠️ 백엔드 제목 변경 실패. 로컬에서만 변경:', e);
    }
    set((state) => ({
      sessions: state.sessions.map((session) =>
        session.id === sessionId ? { ...session, title } : session
      ),
    }));
  },

  setActiveSession: (id) => set({ activeSessionId: id }),

  addMessage: (sessionId, message) =>
    set((state) => ({
      sessions: state.sessions.map((session) => {
        if (session.id === sessionId) {
          return {
            ...session,
            messages: [...session.messages, { ...message, id: uuidv4() }],
          };
        }
        return session;
      }),
    })),

  appendAnswerChunk: (sessionId, chunk) =>
    set((state) => ({
      sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
        ...msg,
        content: msg.content + chunk,
      })),
    })),

  appendReasoning: (sessionId, text) =>
    set((state) => ({
      sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
        ...msg,
        reasoningSteps: [...(msg.reasoningSteps || []), text],
      })),
    })),

  appendReference: (sessionId, ref) =>
    set((state) => ({
      sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => {
        const currentReferences = msg.references || [];
        
        // 중복 방지 (동일 문서 + 동일 페이지 번호)
        const isDuplicate = currentReferences.some(
          (r) => r.pageNumber === ref.pageNumber && r.documentId === ref.documentId
        );
        
        if (isDuplicate) {
          // 중복이지만 썸네일(imageBase64)이 업데이트 되었으면 해당 항목 업데이트
          return {
            ...msg,
            references: currentReferences.map((r) =>
              (r.pageNumber === ref.pageNumber && r.documentId === ref.documentId)
                ? { ...r, imageBase64: ref.imageBase64 || r.imageBase64 }
                : r
            ),
          };
        }

        return {
          ...msg,
          references: [...currentReferences, ref],
          referenceDocumentId: ref.documentId || msg.referenceDocumentId,
          referenceDocumentName: ref.documentName || msg.referenceDocumentName,
        };
      }),
    })),

  setTocCards: (sessionId, cards) =>
    set((state) => ({
      sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
        ...msg,
        tocCards: cards,
      })),
    })),

  finishStreaming: (sessionId) =>
    set((state) => ({
      sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
        ...msg,
        isStreaming: false,
      })),
    })),

  resetActiveSession: () => set({ activeSessionId: null }),

  clearAllSessions: () => set({ sessions: [], activeSessionId: null }),
}));
