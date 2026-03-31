from enum import Enum
from typing import Any
from pydantic import BaseModel, Field
from llm.schemas import ChatMessage


class MemoryPolicy(BaseModel):
    short_term_enabled: bool = True
    working_memory_enabled: bool = True
    long_term_enabled: bool = True
    summary_enabled: bool = True
    sticky_facts_enabled: bool = True
    retrieval_enabled: bool = True
    short_term_limit: int = 20
    retrieval_limit: int = 6


class TaskStatus(str, Enum):
    active = "active"
    paused = "paused"
    done = "done"
    cancelled = "cancelled"


class TaskMemory(BaseModel):
    task_id: str
    status: TaskStatus = TaskStatus.active
    goal: str | None = None
    current_step: str | None = None
    plan: list[str] = Field(default_factory=list)
    completed_steps: list[str] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    task_state: dict[str, Any] = Field(default_factory=dict)
    created_at: str | None = None
    updated_at: str | None = None


class StickyFact(BaseModel):
    key: str
    value: str
    memory_kind: str = "knowledge"
    confidence: float = 0.8
    source: str = "llm"
    updated_at: str | None = None


class RetrievedMemoryItem(BaseModel):
    source_type: str
    source_ref: str
    score: float
    content: str


class AgentMemoryContext(BaseModel):
    short_term_messages: list[ChatMessage] = Field(default_factory=list)
    working_memory: TaskMemory | None = None
    long_term_summary: str | None = None
    long_term_facts: list[StickyFact] = Field(default_factory=list)
    retrieved_items: list[RetrievedMemoryItem] = Field(default_factory=list)