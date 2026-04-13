from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from orchestration import ChatMessage, ExecutionPolicy, OpenAIChatCompletionsModel, Orchestrator, ServerRegistry


def _binary_stream(stream: Any) -> Any:
    return getattr(stream, "buffer", stream)


def read_message(stdin: Any) -> dict[str, Any] | None:
    content_length: int | None = None
    binary_stdin = _binary_stream(stdin)

    while True:
        line = binary_stdin.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8").strip()
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())

    if content_length is None:
        raise ValueError("Missing Content-Length header")

    body = binary_stdin.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stdout: Any, message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    binary_stdout = _binary_stream(stdout)
    binary_stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    binary_stdout.write(encoded)
    binary_stdout.flush()


class MCPToolCallError(RuntimeError):
    pass


class StdioMCPClientSession:
    def __init__(
        self,
        server_script: str | Path,
        *,
        startup_wait_seconds: float = 0.0,
        request_timeout_seconds: float = 20.0,
    ) -> None:
        self._server_script = Path(server_script).resolve()
        self._startup_wait_seconds = startup_wait_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def __enter__(self) -> "StdioMCPClientSession":
        self._process = subprocess.Popen(
            [sys.executable, str(self._server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            cwd=str(self._server_script.parent),
        )
        self.initialize()
        if self._startup_wait_seconds > 0:
            time.sleep(self._startup_wait_seconds)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if not self._process:
            return
        if self._process.poll() is None and self._process.stdin:
            self._process.stdin.close()
        try:
            self._process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

    def initialize(self) -> dict[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "day20-example", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return response

    def list_tools(self) -> list[dict[str, Any]]:
        result = self._request("tools/list", {})
        return list(result.get("tools", []))

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        return dict(result)

    @staticmethod
    def extract_tool_text(result: dict[str, Any]) -> str:
        structured = result.get("structuredContent")
        if structured is not None:
            return json.dumps(structured, ensure_ascii=False)

        content = result.get("content")
        if isinstance(content, list):
            text_parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            return "\n".join(part for part in text_parts if part)

        return json.dumps(result, ensure_ascii=False)

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("MCP client is not connected")
        write_message(
            stdout=self._process.stdin,
            message={"jsonrpc": "2.0", "method": method, "params": params},
        )

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("MCP client is not connected")

        self._request_id += 1
        write_message(
            stdout=self._process.stdin,
            message={"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params},
        )

        response = self._read_response()
        if response is None:
            raise RuntimeError("MCP server closed the connection")
        if response.get("id") != self._request_id:
            raise RuntimeError("MCP server returned an unexpected response id")
        if "error" in response:
            raise MCPToolCallError(response["error"]["message"])
        return dict(response["result"])

    def _read_response(self) -> dict[str, Any] | None:
        deadline = time.time() + self._request_timeout_seconds
        while time.time() < deadline:
            if self._process and self._process.poll() is not None:
                raise RuntimeError(f"MCP server exited with code {self._process.returncode}")
            response = read_message(stdin=self._process.stdout)
            if response is not None:
                return response
        raise TimeoutError(f"MCP request timed out after {self._request_timeout_seconds:.1f}s")


def build_registry(project_root: Path) -> ServerRegistry:
    mcp_root = project_root / "MCP"
    registry = ServerRegistry()

    registry.register(
        "weather",
        lambda: StdioMCPClientSession(
            mcp_root / "weather_forecast" / "server.py",
            startup_wait_seconds=0.2,
            request_timeout_seconds=20.0,
        ),
    )
    registry.register(
        "telegram",
        lambda: StdioMCPClientSession(
            mcp_root / "telegram_sender" / "server.py",
            startup_wait_seconds=0.2,
            request_timeout_seconds=20.0,
        ),
    )
    return registry


def build_prompt(location: str) -> str:
    return (
        f"Узнай текущую погоду в {location}. "
        "Если данные о погоде получены успешно, подготовь короткое понятное сообщение на русском "
        "и отправь его через Telegram. "
        "Если Telegram не настроен или отправка невозможна, не придумывай успех, а просто дай итоговый ответ с причиной. "
        "В финальном ответе кратко перечисли, какие MCP-инструменты были использованы."
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Practical Day20 orchestration example using real MCP stdio servers."
    )
    parser.add_argument("--location", default="Екатеринбург", help="Location for the weather request.")
    parser.add_argument("--model", default="gpt-4.1-mini", help="OpenAI model name.")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        print("OPENAI_API_KEY is not set.", file=sys.stderr)
        return 1

    try:
        from openai import OpenAI
    except ImportError:
        print("The 'openai' package is required. Install it with: pip install openai", file=sys.stderr)
        return 1

    project_root = PROJECT_ROOT.parents[0]
    registry = build_registry(project_root)
    client = OpenAI()
    model = OpenAIChatCompletionsModel(
        client=client,
        model=args.model,
        request_options={"temperature": 0},
    )

    orchestrator = Orchestrator(
        server_registry=registry,
        policy=ExecutionPolicy(
            max_steps=4,
            max_calls_per_server=3,
            max_identical_calls=2,
            wall_clock_timeout_seconds=45.0,
            allow_partial_failures=True,
        ),
    )

    result = orchestrator.execute(
        model=model,
        messages=[ChatMessage(role="user", content=build_prompt(args.location))],
        metadata={"user": "day20-example"},
    )

    print("Final answer:")
    print(result.final_text)
    print()
    print(f"Stop reason: {result.trace.stop_reason}")
    print(f"Tool calls: {result.trace.tool_calls}")
    print("Tool trace:")
    print(json.dumps(result.trace.tool_trace, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
