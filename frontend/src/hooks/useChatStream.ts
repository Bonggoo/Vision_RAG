import { useRef } from "react";
import { useChatStore } from "@/store/useChatStore";
import { authFetch, API_BASE_URL } from "@/lib/api";
import type { SSEEvent } from "@/types/sse";

/**
 * /chat/stream SSE 스트리밍을 캡슐화한 커스텀 훅 (M5)
 *
 * 기존 page.tsx 의 handleChatSubmit / handleStopStreaming 에 인라인돼 있던
 * fetch 호출 · reader 파싱 루프 · 이벤트 switch · abortController · previous_reference
 * 구성을 그대로 옮겨온 것이다. 백엔드 계약(이벤트 타입/페이로드 필드) 및 런타임 동작은
 * 한 글자도 바뀌지 않았으며, 단순히 위치만 이동했다.
 */
export function useChatStream() {
  const {
    sessions,
    activeSessionId,
    createSession,
    addMessage,
    appendAnswerChunk,
    appendReasoning,
    appendReference,
    finishStreaming,
    renameSession,
    setClarification,
    clearClarification,
  } = useChatStore();

  const abortControllerRef = useRef<AbortController | null>(null);

  const submit = async (text: string, image?: string, selectedDocId?: string) => {
    let targetSessionId = activeSessionId;

    const defaultTitle = text.trim()
      ? (text.length > 25 ? text.slice(0, 25) + "..." : text)
      : "📸 알람 사진 질문";

    // 활성 세션이 없으면 자동으로 새 세션 생성
    if (!targetSessionId) {
      targetSessionId = await createSession(defaultTitle);
    } else {
      // 기존 세션이 있고 첫 메시지인 경우 제목 변경
      const currentSession = sessions.find((s) => s.id === targetSessionId);
      if (currentSession && currentSession.messages.length === 0) {
        await renameSession(targetSessionId, defaultTitle);
      }
    }

    if (!targetSessionId) return;

    // 되묻기 시 재질문인 경우, 기존 빈 대화 흐름이 꼬이지 않도록 clarificationState 초기화
    clearClarification();

    addMessage(targetSessionId, { role: "user", content: text, image });
    addMessage(targetSessionId, {
      role: "assistant",
      content: "",
      isStreaming: true,
      reasoningSteps: [],
      references: [],
    });

    // 기존 요청 중단
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const currentSession = sessions.find((s) => s.id === targetSessionId);

      // 대화 히스토리 추출
      const prevMessages = currentSession
        ? currentSession.messages
            .filter((m) => !m.isStreaming && m.content)
            .slice(-6)
            .map((m) => ({ role: m.role, content: m.content.slice(0, 300) }))
        : [];

      // 맥락 유지용 직전 참조 정보 추출 (#3)
      const lastAssistant = currentSession?.messages.filter((m) => m.role === "assistant").pop();
      const previousReference = lastAssistant?.referenceDocumentId ? {
        document_id: lastAssistant.referenceDocumentId,
        document_name: lastAssistant.referenceDocumentName,
        manufacturer: null,
        referenced_pages: lastAssistant.references?.map((r) => r.pageNumber) || [],
      } : undefined;

      const response = await authFetch(`${API_BASE_URL}/chat/stream`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          document_id: selectedDocId || undefined,
          message: text,
          chat_history: prevMessages.length > 0 ? prevMessages : undefined,
          image: image || undefined,
          session_id: targetSessionId,
          previous_reference: previousReference,
        }),
        signal: controller.signal,
      });

      // 응답 상태 체크 (서버 오류 처리)
      if (!response.ok) {
        throw new Error(`서버 오류 (${response.status})`);
      }

      const reader = response.body?.getReader();
      const decoder = new TextDecoder("utf-8");
      let buffer = "";
      let streamDone = false;

      if (reader) {
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split("\n");
          buffer = lines.pop() || "";

          for (const line of lines) {
            if (!line.startsWith("data: ")) continue;
            try {
              const data = JSON.parse(line.slice(6)) as SSEEvent;
              switch (data.type) {
                case "reasoning":
                  appendReasoning(targetSessionId, data.content);
                  break;
                case "reference":
                  appendReference(targetSessionId, {
                    pageNumber: data.page_number,
                    imageBase64: data.image_base64,
                    documentId: data.document_id,      // 신규
                    documentName: data.document_name,   // 신규
                  });
                  break;

                case "answer":
                  appendAnswerChunk(targetSessionId, data.content);
                  break;
                case "clarification": // 되묻기 이벤트 처리 (문서 후보 + 보강 질문)
                  setClarification({
                    content: data.content,
                    candidates: data.candidates || [],
                    suggested_questions: data.suggested_questions,
                  });
                  finishStreaming(targetSessionId);
                  streamDone = true;
                  break;
                case "error":
                  appendAnswerChunk(targetSessionId, `\n\n> ⚠️ 오류: ${data.content}\n`);
                  break;
                case "done":
                  finishStreaming(targetSessionId);
                  streamDone = true;
                  break;
              }
            } catch {
              /* JSON parse error */
            }
          }
          // done 이벤트 수신 시 while 루프 탈출
          if (streamDone) break;
        }
      }
      // done 이벤트를 못 받고 스트림이 끝난 경우에만 finishStreaming 호출
      if (!streamDone) {
        finishStreaming(targetSessionId);
      }
    } catch (error: any) {
      if (error.name === 'AbortError') {
        // 사용자가 의도적으로 중단 → 에러 메시지 표시하지 않음
        console.log('사용자가 스트리밍을 중단했습니다.');
      } else {
        console.error(error);
        appendAnswerChunk(targetSessionId, `\n\n> ⚠️ ${error.message || '네트워크 오류가 발생했습니다.'}`);
      }
      finishStreaming(targetSessionId);
    } finally {
      abortControllerRef.current = null;
    }
  };

  /** 스트리밍 중단 핸들러 */
  const stop = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (activeSessionId) {
      finishStreaming(activeSessionId);
    }
  };

  return { submit, stop };
}
