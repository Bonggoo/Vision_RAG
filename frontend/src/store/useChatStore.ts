import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';

/** 참조 페이지 이미지 */
export interface ReferenceImage {
  pageNumber: number;
  imageBase64: string;
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
}

export interface ChatSession {
  id: string;
  title: string;
  messages: Message[];
  createdAt: number;
}

interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  createSession: (title?: string) => string;
  setActiveSession: (id: string) => void;
  deleteSession: (id: string) => void;
  addMessage: (sessionId: string, message: Omit<Message, 'id'>) => void;
  /** 스트리밍 답변 청크를 추가합니다 */
  appendAnswerChunk: (sessionId: string, chunk: string) => void;
  /** 추론 과정 텍스트를 추가합니다 */
  appendReasoning: (sessionId: string, text: string) => void;
  /** 참조 이미지를 추가합니다 */
  appendReference: (sessionId: string, ref: ReferenceImage) => void;
  /** 스트리밍 완료 처리 */
  finishStreaming: (sessionId: string) => void;
  /** 세션 제목 변경 */
  renameSession: (sessionId: string, title: string) => void;
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

export const useChatStore = create<ChatStore>()(
  persist(
    (set) => ({
      sessions: [],
      activeSessionId: null,

      createSession: (title = '새로운 대화') => {
        const newSession: ChatSession = {
          id: uuidv4(),
          title,
          messages: [],
          createdAt: Date.now(),
        };

        set((state) => {
          let updatedSessions = [newSession, ...state.sessions];
          if (updatedSessions.length > 20) {
            updatedSessions = updatedSessions.slice(0, 20);
          }
          return {
            sessions: updatedSessions,
            activeSessionId: newSession.id,
          };
        });

        return newSession.id;
      },

      setActiveSession: (id) => set({ activeSessionId: id }),

      deleteSession: (id) =>
        set((state) => ({
          sessions: state.sessions.filter((s) => s.id !== id),
          activeSessionId: state.activeSessionId === id ? null : state.activeSessionId,
        })),

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
          sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
            ...msg,
            references: [...(msg.references || []), ref],
          })),
        })),

      finishStreaming: (sessionId) =>
        set((state) => ({
          sessions: updateLastAssistantMessage(state.sessions, sessionId, (msg) => ({
            ...msg,
            isStreaming: false,
          })),
        })),

      renameSession: (sessionId, title) =>
        set((state) => ({
          sessions: state.sessions.map((session) =>
            session.id === sessionId ? { ...session, title } : session
          ),
        })),
    }),
    {
      name: 'vision-rag-chat-storage',
    },
  ),
);
