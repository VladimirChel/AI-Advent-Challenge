from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from openai import OpenAI

from config import PROXYAPI_API_KEY, PROXYAPI_BASE_URL, REQUEST_TIMEOUT_SECONDS
from llm.mcp_client import MCPClientSession
from llm.schemas import ChatMessage, MCPSettings

client = OpenAI(
    api_key=PROXYAPI_API_KEY,
    base_url=PROXYAPI_BASE_URL,
    timeout=REQUEST_TIMEOUT_SECONDS,
)


@dataclass(slots=True)
class MCPExecutionResult:
    used: bool = False
    server_script: str | None = None
    tools_offered: int = 0
    tool_calls: list[str] = field(default_factory=list)
    responses: list[Any] = field(default_factory=list)


def _serialize_message(message: ChatMessage | dict[str, Any]) -> dict[str, Any]:
    if isinstance(message, ChatMessage):
        return message.model_dump()
    return dict(message)


def _build_completion_params(
    *,
    model: str,
    messages: list[ChatMessage | dict[str, Any]],
    temperature: float,
    max_tokens: int,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    user_id: str | None,
    tools: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    params: dict[str, Any] = {
        "model": model,
        "messages": [_serialize_message(message) for message in messages],
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "user": user_id,
    }

    if tools:
        params["tools"] = tools
        params["tool_choice"] = "auto"

    if "gpt-5" in model:
        params["max_completion_tokens"] = max_tokens
    else:
        params["max_tokens"] = max_tokens

    return params


def call_chat_completion(
    *,
    model: str,
    messages: list[ChatMessage | dict[str, Any]],
    temperature: float,
    max_tokens: int,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    user_id: str | None,
    tools: list[dict[str, Any]] | None = None,
) -> Any:
    params = _build_completion_params(
        model=model,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        user_id=user_id,
        tools=tools,
    )
    return client.chat.completions.create(**params)


def call_chat_completion_with_mcp(
    *,
    model: str,
    messages: list[ChatMessage | dict[str, Any]],
    temperature: float,
    max_tokens: int,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    user_id: str | None,
    mcp_settings: MCPSettings | None,
) -> tuple[Any, MCPExecutionResult]:
    if not mcp_settings or not mcp_settings.enabled or not mcp_settings.server_script:
        response = call_chat_completion(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            top_p=top_p,
            presence_penalty=presence_penalty,
            frequency_penalty=frequency_penalty,
            user_id=user_id,
        )
        return response, MCPExecutionResult(responses=[response])

    tool_messages = [_serialize_message(message) for message in messages]
    execution = MCPExecutionResult(used=True, server_script=mcp_settings.server_script)

    with MCPClientSession(
        mcp_settings.server_script,
        startup_wait_seconds=mcp_settings.wait_after_start_seconds or 0.0,
        request_timeout_seconds=mcp_settings.tool_call_timeout_seconds or 20.0,
    ) as mcp_session:
        mcp_tools = mcp_session.list_tools()
        execution.tools_offered = len(mcp_tools)
        openai_tools = mcp_session.to_openai_tools(mcp_tools)

        max_roundtrips = mcp_settings.max_tool_roundtrips or 4
        for _ in range(max_roundtrips):
            response = call_chat_completion(
                model=model,
                messages=tool_messages,
                temperature=temperature,
                max_tokens=max_tokens,
                top_p=top_p,
                presence_penalty=presence_penalty,
                frequency_penalty=frequency_penalty,
                user_id=user_id,
                tools=openai_tools,
            )
            execution.responses.append(response)

            choice = response.choices[0] if getattr(response, "choices", None) else None
            assistant_message = getattr(choice, "message", None)
            tool_calls = list(getattr(assistant_message, "tool_calls", None) or [])
            if not tool_calls:
                return response, execution

            tool_messages.append(
                {
                    "role": "assistant",
                    "content": getattr(assistant_message, "content", None) or "",
                    "tool_calls": [
                        {
                            "id": tool_call.id,
                            "type": "function",
                            "function": {
                                "name": tool_call.function.name,
                                "arguments": tool_call.function.arguments,
                            },
                        }
                        for tool_call in tool_calls
                    ],
                }
            )

            for tool_call in tool_calls:
                raw_arguments = tool_call.function.arguments or "{}"
                arguments = json.loads(raw_arguments) if raw_arguments.strip() else {}
                result = mcp_session.call_tool(tool_call.function.name, arguments)
                execution.tool_calls.append(tool_call.function.name)
                tool_messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": tool_call.id,
                        "content": mcp_session.extract_tool_text(result),
                    }
                )

    raise RuntimeError("MCP tool roundtrip limit exceeded before the model produced final text")


def extract_text_from_chat_completion(resp: Any) -> tuple[str, str | None]:
    content_parts: list[str] = []
    finish_reason = None

    if not hasattr(resp, "choices") or not resp.choices:
        return "", None

    for choice in resp.choices:
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)

        if isinstance(message_content, str) and message_content:
            content_parts.append(message_content)

        if finish_reason is None:
            finish_reason = getattr(choice, "finish_reason", None)

    return "\n".join(content_parts), finish_reason


def get_usage(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if not usage:
        return {}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def aggregate_usage(responses: list[Any]) -> dict[str, Any]:
    total_prompt_tokens = 0
    total_completion_tokens = 0
    total_tokens = 0
    saw_usage = False

    for response in responses:
        usage = get_usage(response)
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
