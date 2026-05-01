from typing import Any, Literal
from pydantic import BaseModel, Field
from config import TASK_SHOW_TRANSITIONS


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=50000)


class ResponseValidationRules(BaseModel):
    min_output_length: int | None = Field(default=None, ge=1, le=20000)
    max_output_length: int | None = Field(default=None, ge=1, le=200000)
    must_contain: list[str] = Field(default_factory=list)
    forbid_phrases: list[str] = Field(default_factory=list)
    require_json: bool = False


class MCPServerConfig(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=100)
    enabled: bool = True
    server_script: str
    wait_after_start_seconds: float | None = Field(default=None, ge=0, le=30)
    tool_call_timeout_seconds: float | None = Field(default=None, ge=1, le=300)


class MCPSettings(BaseModel):
    enabled: bool = False
    server_script: str | None = None
    servers: list[MCPServerConfig] = Field(default_factory=list)
    wait_after_start_seconds: float | None = Field(default=None, ge=0, le=30)
    tool_call_timeout_seconds: float | None = Field(default=None, ge=1, le=300)
    max_tool_roundtrips: int | None = Field(default=None, ge=1, le=10)


class RAGSettings(BaseModel):
    enabled: bool = False
    strategy: Literal["fixed", "structure"] = "structure"
    index_file: str | None = None
    metadata_file: str | None = None
    embed_model: str = Field(default="bge-m3", min_length=1, max_length=200)
    ollama_url: str = Field(default="http://localhost:11434", min_length=1, max_length=500)
    top_k: int = Field(default=5, ge=1, le=20)
    min_relevance_score: float = Field(default=0.75, ge=0, le=10)
    dense_search_enabled: bool = True
    lexical_rerank_enabled: bool = True
    lexical_fallback_enabled: bool = True


class ProjectSettings(BaseModel):
    id: str | None = Field(default=None, min_length=1, max_length=200)
    root: str | None = None
    index_dir: str | None = None
    index_file: str | None = None
    metadata_file: str | None = None


class GenerateRequest(BaseModel):
    conversation_id: str | None = None
    branch_id: str = "main"
    task_id: str | None = None
    chat_mode: Literal["default", "rag_task_chat", "project_help"] = "rag_task_chat"
    provider_id: str | None = Field(default=None, min_length=1, max_length=100)
    model: str
    messages: list[ChatMessage]
    user_id: str | None = None
    temperature: float = 0.2
    max_tokens: int = 800
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    validation: ResponseValidationRules | None = None
    show_task_transition_in_chat: bool = TASK_SHOW_TRANSITIONS
    include_sources_in_content: bool = True
    include_citations_in_content: bool = True
    mcp: MCPSettings | None = None
    rag: RAGSettings | None = None
    project: ProjectSettings | None = None


class RAGChunkPayload(BaseModel):
    rank: int
    score: float
    chunk_id: str
    title: str = ""
    source: str
    section: str
    text: str


class SourcePayload(BaseModel):
    source: str
    section: str
    chunk_id: str


class CitationPayload(BaseModel):
    source: str
    section: str
    chunk_id: str
    quote: str
    score: float | None = None


class TaskStatePayload(BaseModel):
    task_id: str
    status: str
    stage: str
    expected_action: str
    current_step: str | None = None
    blocked_reason: str | None = None
    allowed_events: list[str] = Field(default_factory=list)
    goal: str | None = None
    constraints: list[str] = Field(default_factory=list)
    fixed_terms: list[str] = Field(default_factory=list)
    clarified_points: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)


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
    provider_id: str | None = None
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
    rag_used: bool = False
    rag_chunks_used: int = 0
    rag_strategy: str | None = None
    rag_chunks: list[RAGChunkPayload] = Field(default_factory=list)
    sources: list[SourcePayload] = Field(default_factory=list)
    citations: list[CitationPayload] = Field(default_factory=list)

    project_invariants_used: bool = False
    project_invariants_count: int = 0
    invariant_check_passed: bool = True
    invariant_violations: list[str] = Field(default_factory=list)

    task_state: TaskStatePayload | None = None
    task_transition: TaskTransitionPayload | None = None
    task_transition_error: TaskTransitionErrorPayload | None = None
    active_mode: str = "default"
    project_id: str | None = None
    project_help_route: str | None = None
    mcp_used: bool = False
    mcp_server: str | None = None
    mcp_servers: list[str] = Field(default_factory=list)
    mcp_tools_offered: int = 0
    mcp_available_tools: list[dict[str, Any]] = Field(default_factory=list)
    mcp_tool_calls: list[str] = Field(default_factory=list)
    mcp_tool_trace: list[dict[str, Any]] = Field(default_factory=list)
