from __future__ import annotations

from typing import Any

from .types import ChatMessage, ModelResponse, ToolCall, ToolDefinition


class OpenAIChatCompletionsModel:
    def __init__(self, client: Any, *, model: str, request_options: dict[str, Any] | None = None) -> None:
        self.client = client
        self.model = model
        self.request_options = dict(request_options or {})

    def complete(
        self,
        *,
        messages: list[ChatMessage],
        tools: list[ToolDefinition],
        metadata: dict[str, Any] | None = None,
    ) -> ModelResponse:
        params: dict[str, Any] = {
            "model": self.model,
            "messages": [self._serialize_message(message) for message in messages],
            **self.request_options,
        }
        if metadata and metadata.get("user"):
            params["user"] = metadata["user"]

        if tools:
            params["tools"] = [self._serialize_tool(tool) for tool in tools]
            params["tool_choice"] = "auto"

        response = self.client.chat.completions.create(**params)
        choice = response.choices[0] if getattr(response, "choices", None) else None
        message = getattr(choice, "message", None)
        tool_calls = list(getattr(message, "tool_calls", None) or [])

        return ModelResponse(
            message=ChatMessage(
                role="assistant",
                content=getattr(message, "content", None) or "",
            ),
            tool_calls=[
                ToolCall(
                    call_id=tool_call.id,
                    alias=tool_call.function.name,
                    arguments=self._coerce_arguments(tool_call.function.arguments),
                )
                for tool_call in tool_calls
            ],
            finish_reason=getattr(choice, "finish_reason", None),
            usage=self.extract_usage(response),
            raw_response=response,
        )

    @staticmethod
    def extract_usage(response: Any) -> dict[str, Any]:
        usage = getattr(response, "usage", None)
        if not usage:
            return {}
        return {
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
            "total_tokens": getattr(usage, "total_tokens", None),
        }

    @staticmethod
    def aggregate_usage(usages: list[dict[str, Any]]) -> dict[str, Any]:
        total_prompt_tokens = 0
        total_completion_tokens = 0
        total_tokens = 0
        saw_usage = False

        for usage in usages:
            if not usage:
                continue
            saw_usage = True
            total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
            total_completion_tokens += int(usage.get("completion_tokens") or 0)
            total_tokens += int(usage.get("total_tokens") or 0)

        if not saw_usage:
            return {}

        return {
            "prompt_tokens": total_prompt_tokens,
            "completion_tokens": total_completion_tokens,
            "total_tokens": total_tokens,
        }

    @staticmethod
    def _coerce_arguments(raw_arguments: Any) -> dict[str, Any]:
        if isinstance(raw_arguments, dict):
            return raw_arguments
        if isinstance(raw_arguments, str) and raw_arguments.strip():
            import json

            return dict(json.loads(raw_arguments))
        return {}

    @staticmethod
    def _serialize_message(message: ChatMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "role": message.role,
            "content": message.content,
        }
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = message.tool_calls
        return payload

    @staticmethod
    def _serialize_tool(tool: ToolDefinition) -> dict[str, Any]:
        description = tool.description.strip()
        if description:
            description = f"[server:{tool.server_id} tool:{tool.name}] {description}"
        else:
            description = f"Tool '{tool.name}' from MCP server '{tool.server_id}'."

        return {
            "type": "function",
            "function": {
                "name": tool.alias,
                "description": description,
                "parameters": tool.input_schema,
            },
        }
