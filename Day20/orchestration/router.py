from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .policies import ExecutionPolicy, PolicySnapshot
from .types import ChatMessage, ExecutionTrace, RoutingDecision, ToolDefinition


@dataclass(slots=True)
class RoutingContext:
    step: int
    messages: list[ChatMessage]
    tools: list[ToolDefinition]
    trace: ExecutionTrace
    policy: ExecutionPolicy
    snapshot: PolicySnapshot


class ToolRouter(Protocol):
    def route(self, context: RoutingContext) -> RoutingDecision:
        ...


class DefaultToolRouter:
    def route(self, context: RoutingContext) -> RoutingDecision:
        tool_aliases = ", ".join(tool.alias for tool in context.tools) or "none"
        server_ids = ", ".join(context.trace.server_ids) or "none"
        system_prompt = (
            "You can use tools from multiple MCP servers. "
            f"Available servers: {server_ids}. "
            "Each tool name is namespaced as 'server_id__tool_name'. "
            f"Currently available tool aliases: {tool_aliases}. "
            "Use tools only when they materially improve the answer, avoid repeating the same call, "
            "and produce the final answer once you have enough information."
        )
        return RoutingDecision(
            allowed_tools=context.tools,
            system_prompt=system_prompt,
        )
