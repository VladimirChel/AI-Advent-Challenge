from app.core.config import get_settings
from app.db.models import ChatModel
from app.db.session import get_session
from app.schemas.chat import ChatCreate, ChatRead, ChatUpdate


class ChatService:
    @staticmethod
    def _to_schema(chat: ChatModel) -> ChatRead:
        return ChatRead(
            id=chat.id,
            title=chat.title,
            selected_provider=chat.selected_provider,
            selected_model=chat.selected_model,
            created_at=chat.created_at,
            updated_at=chat.updated_at,
        )

    def create_chat(self, payload: ChatCreate) -> ChatRead:
        with get_session() as session:
            chat = ChatModel(
                title=payload.title or "New chat",
                selected_provider=payload.selected_provider or get_settings().default_provider,
                selected_model=payload.selected_model or get_settings().default_model,
            )
            session.add(chat)
            session.commit()
            session.refresh(chat)
            return self._to_schema(chat)

    def list_chats(self) -> list[ChatRead]:
        with get_session() as session:
            chats = session.query(ChatModel).order_by(ChatModel.updated_at.desc()).all()
            return [self._to_schema(chat) for chat in chats]

    def get_chat(self, chat_id: str) -> ChatRead | None:
        with get_session() as session:
            chat = session.get(ChatModel, chat_id)
            return None if chat is None else self._to_schema(chat)

    def update_chat(self, chat_id: str, payload: ChatUpdate) -> ChatRead | None:
        from app.db.models import utc_now

        with get_session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat is None:
                return None
            if payload.title is not None:
                chat.title = payload.title
            if payload.selected_provider is not None:
                chat.selected_provider = payload.selected_provider
            if payload.selected_model is not None:
                chat.selected_model = payload.selected_model
            chat.updated_at = utc_now()
            session.commit()
            session.refresh(chat)
            return self._to_schema(chat)

    def delete_chat(self, chat_id: str) -> bool:
        with get_session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat is None:
                return False
            session.delete(chat)
            session.commit()
            return True

    def touch_chat(self, chat_id: str) -> None:
        from app.db.models import utc_now

        with get_session() as session:
            chat = session.get(ChatModel, chat_id)
            if chat is None:
                return
            chat.updated_at = utc_now()
            session.commit()


chat_service = ChatService()
