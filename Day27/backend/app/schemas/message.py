from datetime import datetime

from pydantic import BaseModel, Field


class MessageSettings(BaseModel):
    temperature: float = Field(default=0.7, ge=0.0, le=2.0)
    max_tokens: int = Field(default=1024, ge=1, le=8192)
    system_prompt: str = Field(default="")


class MessageCreate(BaseModel):
    content: str = Field(min_length=1, max_length=12000)
    provider: str | None = None
    model: str | None = None
    settings: MessageSettings = Field(default_factory=MessageSettings)


class MessageRead(BaseModel):
    id: str
    chat_id: str
    role: str
    content: str
    provider: str
    model: str
    status: str
    token_input: int | None = None
    token_output: int | None = None
    latency_ms: int | None = None
    error_text: str | None = None
    created_at: datetime


class MessageExchange(BaseModel):
    user_message: MessageRead
    assistant_message: MessageRead


class StreamEvent(BaseModel):
    event: str
    data: dict[str, object]

