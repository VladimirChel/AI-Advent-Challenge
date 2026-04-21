from datetime import datetime

from pydantic import BaseModel, Field


class ChatCreate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    selected_provider: str | None = None
    selected_model: str | None = None


class ChatUpdate(BaseModel):
    title: str | None = Field(default=None, max_length=200)
    selected_provider: str | None = None
    selected_model: str | None = None


class ChatRead(BaseModel):
    id: str
    title: str
    selected_provider: str
    selected_model: str
    created_at: datetime
    updated_at: datetime

