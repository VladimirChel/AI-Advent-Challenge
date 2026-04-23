from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import sys
from typing import Any

from openai import OpenAI

from config import DEFAULT_LLM_PROVIDER, LLM_PROVIDERS, REQUEST_TIMEOUT_SECONDS
from llm.mcp_client import MCPClientSession
from llm.schemas import ChatMessage, MCPServerConfig, MCPSettings

DAY20_PATH = Path(__file__).resolve().parents[2] / "Day20"
if str(DAY20_PATH) not in sys.path:
    sys.path.append(str(DAY20_PATH))

from orchestration import ExecutionPolicy, OpenAIChatCompletionsModel, OrchestrationError, Orchestrator, ServerRegistry
from orchestration import ChatMessage as OrchestrationChatMessage
from orchestration import normalize_server_id

_clients: dict[str, OpenAI] = {}


def list_llm_providers() -> list[dict[str, str]]:
    return [
        {
            "id": provider["id"],
            "name": provider.get("name") or provider["id"],
            "base_url": provider["base_url"],
            "default_model": provider.get("default_model") or "",
        }
        for provider in LLM_PROVIDERS
    ]


def resolve_provider_id(provider_id: str | None) -> str:
    requested = (provider_id or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER
    provider_ids = {provider["id"] for provider in LLM_PROVIDERS}
    if requested in provider_ids:
        return requested
    if LLM_PROVIDERS:
        return LLM_PROVIDERS[0]["id"]
    return DEFAULT_LLM_PROVIDER


def get_openai_client(provider_id: str | None = None) -> OpenAI:
    resolved_provider_id = resolve_provider_id(provider_id)
    if resolved_provider_id in _clients:
        return _clients[resolved_provider_id]

    provider = next(item for item in LLM_PROVIDERS if item["id"] == resolved_provider_id)
    _clients[resolved_provider_id] = OpenAI(
        api_key=provider.get("api_key") or "local-no-key-required",
        base_url=provider["base_url"],
        timeout=REQUEST_TIMEOUT_SECONDS,
    )
    return _clients[resolved_provider_id]


@dataclass(slots=True)
class MCPExecutionResult:
    used: bool = False
    server_script: str | None = None
    servers: list[str] = field(default_factory=list)
    tools_offered: int = 0
    available_tools: list[dict[str, Any]] = field(default_factory=list)
    tool_calls: list[str] = field(default_factory=list)
    tool_trace: list[dict[str, Any]] = field(default_factory=list)
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
    provider_id: str | None = None,
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
    return get_openai_client(provider_id).chat.completions.create(**params)


def call_chat_completion_with_mcp(
    *,
    provider_id: str | None = None,
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
    server_configs = _resolve_mcp_server_configs(mcp_settings)
    if not mcp_settings or not mcp_settings.enabled or not server_configs:
        response = call_chat_completion(
            provider_id=provider_id,
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

    registry = ServerRegistry()
    for server_config in server_configs:
        registry.register(
            server_config.id or "server",
            lambda server_config=server_config: MCPClientSession(
                server_config.server_script,
                startup_wait_seconds=server_config.wait_after_start_seconds or 0.0,
                request_timeout_seconds=server_config.tool_call_timeout_seconds or 20.0,
            ),
            server_script=server_config.server_script,
        )

    request_options = _build_completion_params(
        model=model,
        messages=[],
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        presence_penalty=presence_penalty,
        frequency_penalty=frequency_penalty,
        user_id=user_id,
    )
    request_options.pop("model", None)
    request_options.pop("messages", None)
    request_options.pop("user", None)

    orchestration_model = OpenAIChatCompletionsModel(
        client=get_openai_client(provider_id),
        model=model,
        request_options=request_options,
    )
    orchestrator = Orchestrator(
        server_registry=registry,
        policy=ExecutionPolicy(
            max_steps=mcp_settings.max_tool_roundtrips or 4,
            max_calls_per_server=mcp_settings.max_tool_roundtrips or 4,
            wall_clock_timeout_seconds=REQUEST_TIMEOUT_SECONDS,
            allow_partial_failures=True,
        ),
    )

    try:
        result = orchestrator.execute(
            model=orchestration_model,
            messages=[
                OrchestrationChatMessage(
                    role=serialized["role"],
                    content=serialized["content"],
                    tool_call_id=serialized.get("tool_call_id"),
                    tool_calls=list(serialized.get("tool_calls", [])),
                )
                for serialized in (_serialize_message(message) for message in messages)
            ],
            metadata={"user": user_id},
        )
    except OrchestrationError as exc:
        if exc.trace.stop_reason == "max_steps_exceeded":
            raise RuntimeError("MCP tool roundtrip limit exceeded before the model produced final text") from exc
        raise RuntimeError(f"MCP orchestration failed: {exc.trace.stop_reason or str(exc)}") from exc

    final_response = result.final_response.raw_response if result.final_response else None
    if final_response is None:
        raise RuntimeError("MCP orchestration completed without a model response")

    execution = MCPExecutionResult(
        used=True,
        server_script=server_configs[0].server_script,
        servers=[server_config.server_script for server_config in server_configs],
        tools_offered=result.trace.tools_offered,
        available_tools=list(result.trace.available_tools),
        tool_calls=result.trace.tool_calls,
        tool_trace=result.trace.tool_trace,
        responses=list(result.trace.model_usages),
    )
    return final_response, execution


def _resolve_mcp_server_configs(mcp_settings: MCPSettings | None) -> list[MCPServerConfig]:
    if not mcp_settings or not mcp_settings.enabled:
        return []

    servers = [server for server in mcp_settings.servers if server.enabled and server.server_script]
    if servers:
        normalized: list[MCPServerConfig] = []
        for index, server in enumerate(servers, start=1):
            normalized.append(
                server.model_copy(
                    update={
                        "id": normalize_server_id(server.id or f"server_{index}"),
                    }
                )
            )
        return normalized

    if not mcp_settings.server_script:
        return []

    return [
        MCPServerConfig(
            id="server_1",
            server_script=mcp_settings.server_script,
            wait_after_start_seconds=mcp_settings.wait_after_start_seconds,
            tool_call_timeout_seconds=mcp_settings.tool_call_timeout_seconds,
        )
    ]


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
    if isinstance(resp, dict):
        return {
            "prompt_tokens": resp.get("prompt_tokens"),
            "completion_tokens": resp.get("completion_tokens"),
            "total_tokens": resp.get("total_tokens"),
        }

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
