from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SupportAnswerRequest(BaseModel):
    question: str = Field(..., min_length=3, max_length=4000)
    ticket_id: str | None = Field(default=None, min_length=1, max_length=100)
    user_id: str | None = Field(default=None, min_length=1, max_length=100)
    user_name: str | None = Field(default=None, min_length=1, max_length=200)
    conversation_id: str | None = Field(default=None, min_length=1, max_length=100)


class SourceItem(BaseModel):
    source: str
    section: str
    chunk_id: str
    score: float | None = None


class UserSummary(BaseModel):
    user_id: str
    username: str | None = None
    name: str | None = None
    plan: str | None = None
    locale: str | None = None
    account_status: str | None = None
    tags: list[str] = Field(default_factory=list)


class TicketSummary(BaseModel):
    ticket_id: str
    subject: str | None = None
    status: str | None = None
    priority: str | None = None
    category: str | None = None
    product_area: str | None = None


class SuggestedTicket(BaseModel):
    ticket_id: str
    subject: str | None = None
    status: str | None = None
    priority: str | None = None
    created_at: str | None = None


class SupportAnswerResponse(BaseModel):
    answer: str
    question: str
    user_summary: UserSummary | None = None
    ticket_summary: TicketSummary | None = None
    suggested_tickets: list[SuggestedTicket] = Field(default_factory=list)
    sources: list[SourceItem] = Field(default_factory=list)
    used_rag: bool = False
    used_ticket_context: bool = False
    used_user_context: bool = False
    needs_user_identity: bool = False
    assistant_metadata: dict[str, Any] = Field(default_factory=dict)


class SupportContextBundle(BaseModel):
    user: dict[str, Any] | None = None
    ticket: dict[str, Any] | None = None
    related_tickets: list[dict[str, Any]] = Field(default_factory=list)


class RetrievedChunk(BaseModel):
    rank: int
    score: float
    chunk_id: str
    source: str
    section: str
    text: str
    title: str | None = None
