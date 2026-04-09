from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config import MCP_SERVER_SCRIPT, MCP_TOOL_CALL_TIMEOUT_SECONDS, MCP_WAIT_AFTER_START_SECONDS
from mcp_stdio import read_message, write_message


class MCPToolCallError(RuntimeError):
    pass


class MCPClientSession:
    def __init__(
        self,
        server_script: str | Path = MCP_SERVER_SCRIPT,
        *,
        startup_wait_seconds: float = MCP_WAIT_AFTER_START_SECONDS,
        request_timeout_seconds: float = MCP_TOOL_CALL_TIMEOUT_SECONDS,
    ) -> None:
        self._server_script = Path(server_script).resolve()
        self._startup_wait_seconds = startup_wait_seconds
        self._request_timeout_seconds = request_timeout_seconds
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def __enter__(self) -> "MCPClientSession":
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
            self._process.wait(timeout=max(5.0, self._request_timeout_seconds))
        except subprocess.TimeoutExpired:
            self._process.kill()
            self._process.wait(timeout=5)

    def initialize(self) -> dict[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "day18-scheduled-agent", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return response

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    @staticmethod
    def extract_tool_payload(result: dict[str, Any]) -> Any:
        if "structuredContent" in result:
            return result["structuredContent"]
        content = result.get("content")
        if isinstance(content, list):
            text_parts = [
                str(item.get("text", ""))
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            ]
            if text_parts:
                joined = "\n".join(part for part in text_parts if part)
                try:
                    return json.loads(joined)
                except json.JSONDecodeError:
                    return joined
        return result

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
        response = read_message(stdin=self._process.stdout)
        if response is None:
            raise RuntimeError("MCP server closed the connection")
        if response.get("id") != self._request_id:
            raise RuntimeError("MCP server returned an unexpected response id")
        if "error" in response:
            raise MCPToolCallError(response["error"]["message"])
        return dict(response["result"])
