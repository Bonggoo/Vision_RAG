import { create } from 'zustand';
import { persist } from 'zustand/middleware';
import { v4 as uuidv4 } from 'uuid';

export interface Message {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isStreaming?: boolean;
}

export interface ChatSession {
  id: string;
  documentId: string | null;
  title: string;
  messages: Message[];
  createdAt: number;
}

interface ChatStore {
  sessions: ChatSession[];
  activeSessionId: string | null;
  createSession: (documentId: string | null, title?: string) => string;
  setActiveSession: (id: string) => void;
  deleteSession: (id: string) => void;
  addMessage: (sessionId: string, message: Omit<Message, 'id'>) => void;
  updateStreamingMessage: (sessionId: string, contentChunk: string, isDone: boolean) => void;
}

export const useChatStore = create<ChatStore>()(
  persist(
    (set, get) => ({
      sessions: [],
      activeSessionId: null,
      
      createSession: (documentId, title = '새로운 대화') => {
        const newSession: ChatSession = {
          id: uuidv4(),
          documentId,
          title,
          messages: [],
          createdAt: Date.now(),
        };
        
        set((state) => {
          // 최대 20개 유지 로직
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
      
      deleteSession: (id) => set((state) => ({
        sessions: state.sessions.filter(s => s.id !== id),
        activeSessionId: state.activeSessionId === id ? null : state.activeSessionId
      })),
      
      addMessage: (sessionId, message) => set((state) => ({
        sessions: state.sessions.map(session => {
          if (session.id === sessionId) {
            return {
              ...session,
              messages: [...session.messages, { ...message, id: uuidv4() }]
            };
          }
          return session;
        })
      })),
      
      updateStreamingMessage: (sessionId, contentChunk, isDone) => set((state) => ({
        sessions: state.sessions.map(session => {
          if (session.id === sessionId) {
            const lastMsg = session.messages[session.messages.length - 1];
            if (lastMsg && lastMsg.role === 'assistant') {
              const updatedMessages = [...session.messages];
              updatedMessages[updatedMessages.length - 1] = {
                ...lastMsg,
                content: lastMsg.content + contentChunk,
                isStreaming: !isDone
              };
              return { ...session, messages: updatedMessages };
            }
          }
          return session;
        })
      }))
    }),
    {
      name: 'vision-rag-chat-storage',
    }
  )
);
