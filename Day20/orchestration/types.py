from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Protocol, runtime_checkable


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str
    tool_call_id: str | None = None
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ToolDefinition:
    server_id: str
    name: str
    description: str = ""
    input_schema: dict[str, Any] = field(
        default_factory=lambda: {"type": "object", "properties": {}, "additionalProperties": False}
    )

    @property
    def alias(self) -> str:
        return f"{self.server_id}__{self.name}"


@dataclass(slots=True)
class ToolCall:
    call_id: str
    alias: str
    arguments: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class ToolResult:
    call_id: str
    server_id: str
    tool_name: str
    tool_alias: str
    arguments: dict[str, Any] = field(default_factory=dict)
    content: str = ""
    is_error: bool = False
    error_message: str | None = None
    elapsed_ms: int | None = None
    raw_result: Any = None


@dataclass(slots=True)
class ModelResponse:
    message: ChatMessage
    tool_calls: list[ToolCall] = field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, Any] = field(default_factory=dict)
    raw_response: Any = None


@dataclass(slots=True)
class RoutingDecision:
    allowed_tools: list[ToolDefinition]
    system_prompt: str | None = None
    stop_reason: str | None = None


@dataclass(slots=True)
class TraceEvent:
    index: int
    kind: str
    step: int
    server_id: str | None = None
    tool_name: str | None = None
    tool_alias: str | None = None
    arguments: dict[str, Any] = field(default_factory=dict)
    content_preview: str | None = None
    error: str | None = None
    finish_reason: str | None = None
    elapsed_ms: int | None = None


@dataclass(slots=True)
class ExecutionTrace:
    server_ids: list[str] = field(default_factory=list)
    tools_offered: int = 0
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    events: list[TraceEvent] = field(default_factory=list)
    model_usages: list[dict[str, Any]] = field(default_factory=list)
    stop_reason: str | None = None

    @property
    def tool_calls(self) -> list[str]:
        return [
            f"{event.server_id}.{event.tool_name}"
            for event in self.events
            if event.kind == "tool" and event.server_id and event.tool_name
        ]

    @property
    def tool_trace(self) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        for event in self.events:
            if event.kind != "tool":
                continue
            result.append(
                {
                    "step": event.step,
                    "server_id": event.server_id,
                    "tool_name": event.tool_name,
                    "tool_alias": event.tool_alias,
                    "arguments": event.arguments,
                    "result_preview": event.content_preview,
                    "error": event.error,
                    "elapsed_ms": event.elapsed_ms,
                }
            )
        return result


@dataclass(slots=True)
class ExecutionResult:
    final_response: ModelResponse | None
    trace: ExecutionTrace
    transcript: list[ChatMessage]

    @property
    def final_text(self) -> str:
        if not self.final_response:
            return ""
        return self.final_response.message.content


@runtime_checkable
class ToolServerSession(Protocol):
    def list_tools(self) -> list[dict[str, Any]]:
        ...

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> Any:
        ...

    def extract_tool_text(self, result: Any) -> str:
        ...


ServerSessionFactory = Callable[[], Any]


@runtime_checkable
class ToolCallingModel(Protocol):
    def complete(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        ...
