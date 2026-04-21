from uuid import uuid4

from app.db.models import MessageModel, utc_now
from app.db.session import get_session
from app.schemas.chat import ChatRead
from app.schemas.message import MessageCreate, MessageExchange, MessageRead
from app.schemas.provider import ChatRequest
from app.services.chat_service import chat_service
from app.services.model_service import model_service


class MessageService:
    @staticmethod
    def _to_schema(message: MessageModel) -> MessageRead:
        return MessageRead(
            id=message.id,
            chat_id=message.chat_id,
            role=message.role,
            content=message.content,
            provider=message.provider,
            model=message.model,
            status=message.status,
            token_input=message.token_input,
            token_output=message.token_output,
            latency_ms=message.latency_ms,
            error_text=message.error_text,
            created_at=message.created_at,
        )

    def list_messages(self, chat_id: str) -> list[MessageRead]:
        with get_session() as session:
            messages = (
                session.query(MessageModel)
                .filter(MessageModel.chat_id == chat_id)
                .order_by(MessageModel.created_at.asc())
                .all()
            )
            return [self._to_schema(message) for message in messages]

    def delete_chat_messages(self, chat_id: str) -> None:
        with get_session() as session:
            session.query(MessageModel).filter(MessageModel.chat_id == chat_id).delete()
            session.commit()

    def _append_message(self, chat_id: str, message: MessageRead) -> MessageRead:
        with get_session() as session:
            record = MessageModel(
                id=message.id,
                chat_id=chat_id,
                role=message.role,
                content=message.content,
                provider=message.provider,
                model=message.model,
                status=message.status,
                token_input=message.token_input,
                token_output=message.token_output,
                latency_ms=message.latency_ms,
                error_text=message.error_text,
                created_at=message.created_at,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_schema(record)

    def _build_user_message(self, chat: ChatRead, payload: MessageCreate) -> MessageRead:
        return MessageRead(
            id=str(uuid4()),
            chat_id=chat.id,
            role="user",
            content=payload.content,
            provider=payload.provider or chat.selected_provider,
            model=payload.model or chat.selected_model,
            status="complete",
            created_at=utc_now(),
        )

    def _history_to_provider_messages(self, chat_id: str) -> list[dict[str, str]]:
        return [
            {"role": message.role, "content": message.content}
            for message in self.list_messages(chat_id)
            if message.role in {"user", "assistant", "system"}
        ]

    async def create_message_exchange(self, chat: ChatRead, payload: MessageCreate) -> MessageExchange:
        user_message = self._append_message(chat.id, self._build_user_message(chat, payload))
        provider_name = payload.provider or chat.selected_provider
        model_name = payload.model or chat.selected_model
        request = ChatRequest(
            chat_id=chat.id,
            provider=provider_name,
            model=model_name,
            messages=self._history_to_provider_messages(chat.id),
            temperature=payload.settings.temperature,
            max_tokens=payload.settings.max_tokens,
            stream=False,
            system_prompt=payload.settings.system_prompt,
        )
        response = await model_service.generate(request)
        assistant_message = self._append_message(
            chat.id,
            MessageRead(
                id=str(uuid4()),
                chat_id=chat.id,
                role="assistant",
                content=response.content,
                provider=response.provider,
                model=response.model,
                status="complete",
                token_input=response.usage.get("input_tokens"),
                token_output=response.usage.get("output_tokens"),
                latency_ms=response.latency_ms,
                created_at=utc_now(),
            ),
        )
        chat_service.touch_chat(chat.id)
        return MessageExchange(user_message=user_message, assistant_message=assistant_message)

    async def stream_message_exchange(self, chat: ChatRead, payload: MessageCreate):
        user_message = self._append_message(chat.id, self._build_user_message(chat, payload))
        provider_name = payload.provider or chat.selected_provider
        model_name = payload.model or chat.selected_model
        request = ChatRequest(
            chat_id=chat.id,
            provider=provider_name,
            model=model_name,
            messages=self._history_to_provider_messages(chat.id),
            temperature=payload.settings.temperature,
            max_tokens=payload.settings.max_tokens,
            stream=True,
            system_prompt=payload.settings.system_prompt,
        )
        assistant_message_id = str(uuid4())
        full_text = ""
        yield {
            "event": "start",
            "data": {
                "chat_id": chat.id,
                "message_id": assistant_message_id,
                "provider": provider_name,
                "model": model_name,
                "user_message_id": user_message.id,
            },
        }
        async for chunk in model_service.stream_generate(request):
            full_text += chunk
            yield {"event": "token", "data": {"message_id": assistant_message_id, "delta": chunk}}

        self._append_message(
            chat.id,
            MessageRead(
                id=assistant_message_id,
                chat_id=chat.id,
                role="assistant",
                content=full_text.strip(),
                provider=provider_name,
                model=model_name,
                status="complete",
                token_input=max(len(payload.content.split()), 1) * 4,
                token_output=max(len(full_text.split()), 1) * 3,
                latency_ms=250,
                created_at=utc_now(),
            ),
        )
        chat_service.touch_chat(chat.id)
        yield {
            "event": "end",
            "data": {
                "message_id": assistant_message_id,
                "full_text": full_text.strip(),
                "usage": {
                    "input_tokens": max(len(payload.content.split()), 1) * 4,
                    "output_tokens": max(len(full_text.split()), 1) * 3,
                },
                "latency_ms": 250,
            },
        }


message_service = MessageService()
