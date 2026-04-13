from __future__ import annotations

import json
import time
from typing import Any

from .policies import ExecutionPolicy, PolicyEngine, PolicySnapshot, PolicyViolation
from .registry import ServerRegistry, ToolRegistry
from .router import DefaultToolRouter, RoutingContext, ToolRouter
from .types import ChatMessage, ExecutionResult, ExecutionTrace, ToolCallingModel, ToolResult, TraceEvent


class OrchestrationError(RuntimeError):
    def __init__(self, message: str, *, trace: ExecutionTrace) -> None:
        super().__init__(message)
        self.trace = trace


class Orchestrator:
    def __init__(
        self,
        *,
        server_registry: ServerRegistry,
        router: ToolRouter | None = None,
        policy: ExecutionPolicy | None = None,
    ) -> None:
        self.server_registry = server_registry
        self.router = router or DefaultToolRouter()
        self.policy = policy or ExecutionPolicy()

    def execute(
        self,
        *,
        model: ToolCallingModel,
        messages: list[ChatMessage],
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        transcript = [
            ChatMessage(
                role=message.role,
                content=message.content,
                tool_call_id=message.tool_call_id,
                tool_calls=list(message.tool_calls),
            )
            for message in messages
        ]
        trace = ExecutionTrace()
        snapshot = PolicySnapshot()
        engine = PolicyEngine(self.policy)

        if self.server_registry.is_empty():
            final_response = model.complete(messages=transcript, tools=[], metadata=metadata)
            trace.model_usages.append(final_response.usage)
            trace.stop_reason = "completed_without_tools"
            return ExecutionResult(final_response=final_response, trace=trace, transcript=transcript)

        with self.server_registry.open_pool() as pool:
            tool_registry = ToolRegistry()
            for server_id, session in pool.sessions.items():
                trace.server_ids.append(server_id)
                registered_tools = tool_registry.register_from_session(server_id, session)
                trace.tools_offered += len(registered_tools)
                trace.available_tools.extend(
                    [
                        {
                            "server_id": tool.server_id,
                            "tool_name": tool.name,
                            "tool_alias": tool.alias,
                            "description": tool.description,
                            "input_schema": tool.input_schema,
                        }
                        for tool in registered_tools
                    ]
                )

            step = 1
            event_index = 1
            while True:
                try:
                    engine.check_before_model_step(step=step, trace=trace, snapshot=snapshot)
                    routing = self.router.route(
                        RoutingContext(
                            step=step,
                            messages=transcript,
                            tools=tool_registry.all(),
                            trace=trace,
                            policy=self.policy,
                            snapshot=snapshot,
                        )
                    )
                    if routing.stop_reason:
                        trace.stop_reason = routing.stop_reason
                        raise OrchestrationError(routing.stop_reason, trace=trace)

                    model_messages = list(transcript)
                    if routing.system_prompt:
                        model_messages.append(ChatMessage(role="system", content=routing.system_prompt))

                    started = time.perf_counter()
                    response = model.complete(
                        messages=model_messages,
                        tools=routing.allowed_tools,
                        metadata=metadata,
                    )
                    elapsed_ms = int((time.perf_counter() - started) * 1000)
                    trace.model_usages.append(response.usage)
                    trace.events.append(
                        TraceEvent(
                            index=event_index,
                            kind="model",
                            step=step,
                            content_preview=(response.message.content or "")[:1000],
                            finish_reason=response.finish_reason,
                            elapsed_ms=elapsed_ms,
                        )
                    )
                    event_index += 1

                    if not response.tool_calls:
                        trace.stop_reason = "completed"
                        return ExecutionResult(final_response=response, trace=trace, transcript=transcript)

                    transcript.append(
                        ChatMessage(
                            role="assistant",
                            content=response.message.content or "",
                            tool_calls=[
                                {
                                    "id": call.call_id,
                                    "type": "function",
                                    "function": {
                                        "name": call.alias,
                                        "arguments": json.dumps(call.arguments, ensure_ascii=False),
                                    },
                                }
                                for call in response.tool_calls
                            ],
                        )
                    )

                    for call in response.tool_calls:
                        definition = tool_registry.get(call.alias)
                        engine.check_before_tool_call(
                            server_id=definition.server_id,
                            tool_name=definition.name,
                            call=call,
                            trace=trace,
                            snapshot=snapshot,
                        )
                        session = pool.sessions[definition.server_id]

                        started = time.perf_counter()
                        try:
                            raw_result = session.call_tool(definition.name, call.arguments)
                            rendered = session.extract_tool_text(raw_result)
                            tool_result = ToolResult(
                                call_id=call.call_id,
                                server_id=definition.server_id,
                                tool_name=definition.name,
                                tool_alias=definition.alias,
                                arguments=call.arguments,
                                content=rendered,
                                elapsed_ms=int((time.perf_counter() - started) * 1000),
                                raw_result=raw_result,
                            )
                        except Exception as exc:
                            tool_result = ToolResult(
                                call_id=call.call_id,
                                server_id=definition.server_id,
                                tool_name=definition.name,
                                tool_alias=definition.alias,
                                arguments=call.arguments,
                                content=f"Tool error: {exc}",
                                is_error=True,
                                error_message=str(exc),
                                elapsed_ms=int((time.perf_counter() - started) * 1000),
                            )
                            if not self.policy.allow_partial_failures:
                                trace.stop_reason = "tool_error"
                                raise OrchestrationError(str(exc), trace=trace) from exc

                        trace.events.append(
                            TraceEvent(
                                index=event_index,
                                kind="tool",
                                step=step,
                                server_id=tool_result.server_id,
                                tool_name=tool_result.tool_name,
                                tool_alias=tool_result.tool_alias,
                                arguments=tool_result.arguments,
                                content_preview=tool_result.content[:1000],
                                error=tool_result.error_message,
                                elapsed_ms=tool_result.elapsed_ms,
                            )
                        )
                        event_index += 1

                        engine.record_tool_result(
                            server_id=definition.server_id,
                            tool_name=definition.name,
                            arguments=call.arguments,
                            result=tool_result,
                            trace=trace,
                            snapshot=snapshot,
                        )
                        transcript.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=call.call_id,
                                content=tool_result.content,
                            )
                        )

                    step += 1
                except PolicyViolation as exc:
                    raise OrchestrationError(exc.reason, trace=trace) from exc
