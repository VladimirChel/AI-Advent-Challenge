from typing import Any, Literal
from pydantic import BaseModel, Field


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=50000)


class ResponseValidationRules(BaseModel):
    min_output_length: int | None = Field(default=None, ge=1, le=20000)
    max_output_length: int | None = Field(default=None, ge=1, le=200000)
    must_contain: list[str] = Field(default_factory=list)
    forbid_phrases: list[str] = Field(default_factory=list)
    require_json: bool = False


class GenerateRequest(BaseModel):
    conversation_id: str | None = None
    branch_id: str = "main"
    task_id: str | None = None
    model: str
    messages: list[ChatMessage]
    user_id: str | None = None
    temperature: float = 0.2
    max_tokens: int = 800
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    validation: ResponseValidationRules | None = None


class GenerateResponse(BaseModel):
    request_id: str
    conversation_id: str
    branch_id: str
    task_id: str | None = None
    model: str
    content: str
    finish_reason: str | None = None
    usage: dict[str, Any] = Field(default_factory=dict)
    latency_ms: int

    short_term_used: bool = False
    short_term_messages_used: int = 0

    working_memory_used: bool = False
    long_term_used: bool = False
    long_term_facts_count: int = 0
    long_term_summary_used: bool = False
    retrieval_used: bool = False
    retrieval_messages_used: int = 0