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


class MCPSettings(BaseModel):
    enabled: bool = False
    server_script: str | None = None
    wait_after_start_seconds: float | None = Field(default=None, ge=0, le=30)
    tool_call_timeout_seconds: float | None = Field(default=None, ge=1, le=300)
    max_tool_roundtrips: int | None = Field(default=None, ge=1, le=10)


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
    show_task_transition_in_chat: bool = True
    mcp: MCPSettings | None = None


class TaskStatePayload(BaseModel):
    task_id: str
    status: str
    stage: str
    expected_action: str
    current_step: str | None = None
    blocked_reason: str | None = None
    allowed_events: list[str] = Field(default_factory=list)


class TaskTransitionPayload(BaseModel):
    applied: bool
    from_status: str | None = None
    to_status: str | None = None
    from_stage: str | None = None
    to_stage: str | None = None
    event: str | None = None
    reason: str | None = None


class TaskTransitionErrorPayload(BaseModel):
    code: str
    message: str


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

    project_invariants_used: bool = False
    project_invariants_count: int = 0
    invariant_check_passed: bool = True
    invariant_violations: list[str] = Field(default_factory=list)

    task_state: TaskStatePayload | None = None
    task_transition: TaskTransitionPayload | None = None
    task_transition_error: TaskTransitionErrorPayload | None = None
    mcp_used: bool = False
    mcp_server: str | None = None
    mcp_tools_offered: int = 0
    mcp_tool_calls: list[str] = Field(default_factory=list)
