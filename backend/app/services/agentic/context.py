"""파이프라인 실행 컨텍스트."""
from app.utils.logger import logger

from .sse import sse_event

# 대화 목록에 표시할 제목 최대 길이
CONVERSATION_TITLE_CHARS = 25


class PipelineContext:
    """파이프라인 전역 상태와 SSE 수집/대화 저장을 캡슐화합니다.

    각 stage 는 이 컨텍스트를 공유하며 SSE 이벤트를 yield 합니다.
    early exit 가 필요한 stage 는 `yield await ctx.finish()` 후 `return` 하고,
    orchestrator 가 `ctx.done` 을 확인해 파이프라인을 종료합니다.
    """

    def __init__(
        self,
        document_id: str | None,
        question: str,
        chat_history: list[dict] | None,
        image: str | None,
        user_email: str | None,
        session_id: str | None,
        previous_reference: dict | None,
    ):
        self.document_id = document_id
        self.question = question
        self.chat_history = chat_history
        self.image = image
        self.user_email = user_email
        self.session_id = session_id
        self.previous_reference = previous_reference

        # SSE 수집 상태 (대화 저장용)
        self.collected_answer = ""
        self.collected_reasoning: list[str] = []
        self.collected_references: list[dict] = []
        self.selected_doc_filename = ""

        # 종료 신호 (early exit 를 orchestrator 에 전달)
        self.done = False

        # stage 간 공유되는 1차 페이지 선택 산출물
        self.coarse_pages: list[int] = [1]
        self.coarse_title = ""

    # ─── SSE 이벤트 생성 (수집 겸용) ─────────────────────────────────────────

    def reasoning(self, content: str) -> str:
        """reasoning 이벤트를 만들고 수집 목록에 추가합니다. `yield ctx.reasoning(...)`."""
        self.collected_reasoning.append(content)
        return sse_event("reasoning", content=content)

    def add_answer(self, content: str) -> str:
        """answer 이벤트를 만들고 누적합니다. `yield ctx.add_answer(...)`."""
        self.collected_answer += content
        return sse_event("answer", content=content)

    def error(self, content: str) -> str:
        """error 이벤트를 만듭니다. `yield ctx.error(...)`."""
        return sse_event("error", content=content)

    def clarification(self, content: str, candidates: list[dict], suggested_questions: list[str]) -> str:
        """되묻기 이벤트를 만듭니다 (문서 후보 카드 + 추천 질문)."""
        return sse_event(
            "clarification",
            content=content,
            candidates=candidates,
            suggested_questions=suggested_questions,
        )

    def reference(self, page_number: int, image_base64: str) -> str:
        """참조 페이지 썸네일 이벤트를 만들고 수집 목록에 추가합니다."""
        self.collected_references.append({"page_number": page_number})
        return sse_event(
            "reference",
            page_number=page_number,
            image_base64=image_base64,
            document_id=str(self.document_id),
            document_name=self.selected_doc_filename,
        )

    # ─── 종료 처리 ───────────────────────────────────────────────────────────

    async def save_conversation(self) -> None:
        """수집된 메시지를 저장합니다 (모든 종료 경로에서 호출).

        저장 실패는 답변 전달을 막지 않도록 로그만 남기고 삼킵니다.
        """
        has_content = bool(self.collected_answer or self.collected_reasoning)
        if not (self.session_id and self.user_email and has_content):
            return
        try:
            from app.services.conversation_service import save_message_async

            user_msg = {"role": "user", "content": self.question, "image": self.image}
            assistant_msg = {
                "role": "assistant",
                "content": self.collected_answer,
                "reasoning_steps": self.collected_reasoning,
                "reference_pages": [ref["page_number"] for ref in self.collected_references],
                "reference_document_id": str(self.document_id) if self.document_id else None,
                "reference_document_name": self.selected_doc_filename if self.document_id else None,
            }
            title = (
                self.question[:CONVERSATION_TITLE_CHARS] + "..."
                if len(self.question) > CONVERSATION_TITLE_CHARS
                else self.question
            )
            await save_message_async(
                self.user_email, self.session_id, user_msg, assistant_msg, title=title
            )
        except Exception as e:
            logger.error(f"❌ [Pipeline] 대화 저장 실패 (무시): {e}")

    async def finish(self) -> str:
        """종료 처리: 대화 저장 + done 이벤트 생성 + done 플래그 설정."""
        await self.save_conversation()
        self.done = True
        return sse_event("done")
