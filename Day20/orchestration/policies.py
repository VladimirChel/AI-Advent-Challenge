from __future__ import annotations

import json
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .types import ExecutionTrace, ToolCall, ToolResult


@dataclass(slots=True)
class ExecutionPolicy:
    max_steps: int = 6
    max_calls_per_server: int = 5
    max_identical_calls: int = 2
    max_consecutive_failures: int = 2
    wall_clock_timeout_seconds: float = 60.0
    allow_partial_failures: bool = True


@dataclass(slots=True)
class PolicySnapshot:
    started_at: float = field(default_factory=time.monotonic)
    per_server_calls: dict[str, int] = field(default_factory=lambda: defaultdict(int))
    call_signatures: Counter[str] = field(default_factory=Counter)
    consecutive_failures: int = 0

    def elapsed_seconds(self) -> float:
        return time.monotonic() - self.started_at


class PolicyViolation(RuntimeError):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


class PolicyEngine:
    def __init__(self, policy: ExecutionPolicy) -> None:
        self.policy = policy

    def check_before_model_step(self, step: int, trace: ExecutionTrace, snapshot: PolicySnapshot) -> None:
        if step > self.policy.max_steps:
            trace.stop_reason = "max_steps_exceeded"
            raise PolicyViolation("max_steps_exceeded")
        if snapshot.elapsed_seconds() > self.policy.wall_clock_timeout_seconds:
            trace.stop_reason = "timeout_exceeded"
            raise PolicyViolation("timeout_exceeded")

    def check_before_tool_call(
        self,
        *,
        server_id: str,
        tool_name: str,
        call: ToolCall,
        trace: ExecutionTrace,
        snapshot: PolicySnapshot,
    ) -> None:
        if snapshot.elapsed_seconds() > self.policy.wall_clock_timeout_seconds:
            trace.stop_reason = "timeout_exceeded"
            raise PolicyViolation("timeout_exceeded")
        if snapshot.per_server_calls[server_id] >= self.policy.max_calls_per_server:
            trace.stop_reason = f"server_limit_exceeded:{server_id}"
            raise PolicyViolation(f"server_limit_exceeded:{server_id}")

        signature = self._signature(server_id=server_id, tool_name=tool_name, arguments=call.arguments)
        if snapshot.call_signatures[signature] >= self.policy.max_identical_calls:
            trace.stop_reason = "anti_loop_triggered"
            raise PolicyViolation("anti_loop_triggered")

    def record_tool_result(
        self,
        *,
        server_id: str,
        tool_name: str,
        arguments: dict[str, object],
        result: ToolResult,
        trace: ExecutionTrace,
        snapshot: PolicySnapshot,
    ) -> None:
        snapshot.per_server_calls[server_id] += 1
        signature = self._signature(server_id=server_id, tool_name=tool_name, arguments=arguments)
        snapshot.call_signatures[signature] += 1

        if result.is_error:
            snapshot.consecutive_failures += 1
            if snapshot.consecutive_failures > self.policy.max_consecutive_failures:
                trace.stop_reason = "too_many_failures"
                raise PolicyViolation("too_many_failures")
        else:
            snapshot.consecutive_failures = 0

    @staticmethod
    def _signature(*, server_id: str, tool_name: str, arguments: dict[str, object]) -> str:
        return json.dumps(
            {
                "server_id": server_id,
                "tool_name": tool_name,
                "arguments": arguments,
            },
            sort_keys=True,
            ensure_ascii=False,
        )
