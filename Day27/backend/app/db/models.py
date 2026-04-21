from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class ChatModel(Base):
    __tablename__ = "chats"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    title: Mapped[str] = mapped_column(String(200), default="New chat")
    selected_provider: Mapped[str] = mapped_column(String(100))
    selected_model: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    messages: Mapped[list["MessageModel"]] = relationship(
        back_populates="chat",
        cascade="all, delete-orphan",
        order_by="MessageModel.created_at",
    )


class MessageModel(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    chat_id: Mapped[str] = mapped_column(ForeignKey("chats.id", ondelete="CASCADE"))
    role: Mapped[str] = mapped_column(String(20))
    content: Mapped[str] = mapped_column(Text)
    provider: Mapped[str] = mapped_column(String(100))
    model: Mapped[str] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="complete")
    token_input: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_output: Mapped[int | None] = mapped_column(Integer, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    chat: Mapped[ChatModel] = relationship(back_populates="messages")

