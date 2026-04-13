from __future__ import annotations

import json
import unittest
from contextlib import contextmanager
from unittest.mock import patch

from orchestration import ChatMessage, ExecutionPolicy, OrchestrationError, Orchestrator, ServerRegistry
from orchestration.registry import ToolRegistry
from orchestration.types import ModelResponse, ToolCall


class FakeSession:
    def __init__(self, tools, results=None, errors=None):
        self._tools = tools
        self._results = results or {}
        self._errors = errors or {}

    def list_tools(self):
        return self._tools

    def call_tool(self, name, arguments=None):
        key = (name, json.dumps(arguments or {}, sort_keys=True, ensure_ascii=False))
        if key in self._errors:
            raise RuntimeError(self._errors[key])
        return self._results[key]

    def extract_tool_text(self, result):
        if isinstance(result, str):
            return result
        return json.dumps(result, ensure_ascii=False)


@contextmanager
def fake_factory(session):
    yield session


class ScriptedModel:
    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = 0
        self.seen_tools = []
        self.seen_messages = []
        self.seen_metadata = []

    def complete(self, *, messages, tools, metadata=None):
        self.seen_messages.append(messages)
        self.seen_tools.append(tools)
        self.seen_metadata.append(metadata)
        response = self._responses[self.calls]
        self.calls += 1
        return response


class OrchestrationTests(unittest.TestCase):
    def test_sanitizes_array_schema_without_items(self):
        registry = ToolRegistry()
        session = FakeSession(
            tools=[
                {
                    "name": "broken",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "readings": {
                                "type": "array",
                            }
                        },
                    },
                }
            ]
        )

        tools = registry.register_from_session("ops", session)

        self.assertEqual(tools[0].input_schema["properties"]["readings"]["items"], {})

    def test_chains_calls_across_servers(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status", "description": "Get status"}],
                    results={("status", "{}"): "ops-ok"},
                )
            ),
        )
        registry.register(
            "wiki",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "lookup", "description": "Lookup docs"}],
                    results={("lookup", '{"topic": "ops-ok"}'): "wiki-ok"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Checking"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Cross-reference"),
                    tool_calls=[ToolCall(call_id="2", alias="wiki__lookup", arguments={"topic": "ops-ok"})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Final answer"),
                ),
            ]
        )

        result = Orchestrator(server_registry=registry).execute(
            model=model,
            messages=[ChatMessage(role="user", content="help")],
        )

        self.assertEqual(result.final_text, "Final answer")
        self.assertEqual(result.trace.tool_calls, ["ops.status", "wiki.lookup"])
        self.assertEqual(result.trace.stop_reason, "completed")

    def test_allows_partial_failures_when_enabled(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    errors={("status", "{}"): "boom"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Trying"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Recovered with partial data"),
                ),
            ]
        )

        result = Orchestrator(
            server_registry=registry,
            policy=ExecutionPolicy(allow_partial_failures=True),
        ).execute(
            model=model,
            messages=[ChatMessage(role="user", content="help")],
        )

        self.assertEqual(result.final_text, "Recovered with partial data")
        self.assertEqual(result.trace.tool_trace[0]["error"], "boom")

    def test_stops_on_identical_loop(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    results={("status", "{}"): "still-running"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 1"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 2"),
                    tool_calls=[ToolCall(call_id="2", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 3"),
                    tool_calls=[ToolCall(call_id="3", alias="ops__status", arguments={})],
                ),
            ]
        )

        with self.assertRaises(OrchestrationError) as ctx:
            Orchestrator(
                server_registry=registry,
                policy=ExecutionPolicy(max_identical_calls=2),
            ).execute(
                model=model,
                messages=[ChatMessage(role="user", content="loop")],
            )

        self.assertEqual(ctx.exception.trace.stop_reason, "anti_loop_triggered")

    def test_stops_when_max_steps_exceeded(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    results={("status", "{}"): "working"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 1"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 2"),
                    tool_calls=[ToolCall(call_id="2", alias="ops__status", arguments={})],
                ),
            ]
        )

        with self.assertRaises(OrchestrationError) as ctx:
            Orchestrator(
                server_registry=registry,
                policy=ExecutionPolicy(max_steps=1, max_identical_calls=5),
            ).execute(
                model=model,
                messages=[ChatMessage(role="user", content="keep checking")],
            )

        self.assertEqual(ctx.exception.trace.stop_reason, "max_steps_exceeded")

    def test_stops_when_server_limit_exceeded(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    results={("status", "{}"): "ok"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 1"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 2"),
                    tool_calls=[ToolCall(call_id="2", alias="ops__status", arguments={})],
                ),
            ]
        )

        with self.assertRaises(OrchestrationError) as ctx:
            Orchestrator(
                server_registry=registry,
                policy=ExecutionPolicy(max_calls_per_server=1, max_identical_calls=5),
            ).execute(
                model=model,
                messages=[ChatMessage(role="user", content="check twice")],
            )

        self.assertEqual(ctx.exception.trace.stop_reason, "server_limit_exceeded:ops")

    def test_stops_when_timeout_exceeded_before_second_step(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    results={("status", "{}"): "ok"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 1"),
                    tool_calls=[ToolCall(call_id="1", alias="ops__status", arguments={})],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Round 2"),
                    tool_calls=[ToolCall(call_id="2", alias="ops__status", arguments={})],
                ),
            ]
        )

        elapsed_values = [0.0, 0.0, 0.2]

        def fake_elapsed_seconds(_snapshot):
            if elapsed_values:
                return elapsed_values.pop(0)
            return 0.2

        with patch("orchestration.policies.PolicySnapshot.elapsed_seconds", autospec=True, side_effect=fake_elapsed_seconds):
            with self.assertRaises(OrchestrationError) as ctx:
                Orchestrator(
                    server_registry=registry,
                    policy=ExecutionPolicy(wall_clock_timeout_seconds=0.1, max_identical_calls=5),
                ).execute(
                    model=model,
                    messages=[ChatMessage(role="user", content="wait")],
                )

        self.assertEqual(ctx.exception.trace.stop_reason, "timeout_exceeded")

    def test_executes_multiple_tool_calls_in_single_model_response(self):
        registry = ServerRegistry()
        registry.register(
            "ops",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "status"}],
                    results={("status", "{}"): "ops-ok"},
                )
            ),
        )
        registry.register(
            "wiki",
            lambda: fake_factory(
                FakeSession(
                    tools=[{"name": "lookup"}],
                    results={("lookup", '{"topic": "ops-ok"}'): "wiki-ok"},
                )
            ),
        )
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Use both"),
                    tool_calls=[
                        ToolCall(call_id="1", alias="ops__status", arguments={}),
                        ToolCall(call_id="2", alias="wiki__lookup", arguments={"topic": "ops-ok"}),
                    ],
                ),
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Combined answer"),
                ),
            ]
        )

        result = Orchestrator(server_registry=registry).execute(
            model=model,
            messages=[ChatMessage(role="user", content="combine")],
        )

        self.assertEqual(result.final_text, "Combined answer")
        self.assertEqual(result.trace.tool_calls, ["ops.status", "wiki.lookup"])
        self.assertEqual(
            [message.role for message in result.transcript],
            ["user", "assistant", "tool", "tool"],
        )

    def test_completes_without_servers_and_without_tools(self):
        registry = ServerRegistry()
        model = ScriptedModel(
            [
                ModelResponse(
                    message=ChatMessage(role="assistant", content="Direct answer"),
                )
            ]
        )

        result = Orchestrator(server_registry=registry).execute(
            model=model,
            messages=[ChatMessage(role="user", content="hello")],
            metadata={"user": "u-1"},
        )

        self.assertEqual(result.final_text, "Direct answer")
        self.assertEqual(result.trace.stop_reason, "completed_without_tools")
        self.assertEqual(model.seen_tools[0], [])
        self.assertEqual(model.seen_metadata[0], {"user": "u-1"})


if __name__ == "__main__":
    unittest.main()
