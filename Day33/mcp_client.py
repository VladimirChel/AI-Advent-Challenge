from __future__ import annotations

import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

from config import (
    SUPPORT_MCP_SERVER_SCRIPT,
    SUPPORT_MCP_TIMEOUT_SECONDS,
    SUPPORT_MCP_WAIT_AFTER_START_SECONDS,
)


class MCPClientError(RuntimeError):
    pass


def read_message(stdin: Any) -> dict[str, Any] | None:
    content_length: int | None = None
    stream = getattr(stdin, "buffer", stdin)
    while True:
        line = stream.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8").strip()
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())
    if content_length is None:
        raise MCPClientError("MCP response is missing Content-Length header")
    payload = stream.read(content_length)
    if not payload:
        return None
    return json.loads(payload.decode("utf-8"))


def write_message(stdout: Any, message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    stream = getattr(stdout, "buffer", stdout)
    stream.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    stream.write(encoded)
    stream.flush()


class MCPClientSession:
    def __init__(
        self,
        server_script: str | Path = SUPPORT_MCP_SERVER_SCRIPT,
        *,
        startup_wait_seconds: float = SUPPORT_MCP_WAIT_AFTER_START_SECONDS,
        request_timeout_seconds: float = SUPPORT_MCP_TIMEOUT_SECONDS,
    ) -> None:
        self.server_script = Path(server_script).resolve()
        self.startup_wait_seconds = startup_wait_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.process: subprocess.Popen[bytes] | None = None
        self.request_id = 0

    def __enter__(self) -> "MCPClientSession":
        self.process = subprocess.Popen(
            [sys.executable, str(self.server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            cwd=str(self.server_script.parent),
        )
        self.initialize()
        if self.startup_wait_seconds > 0:
            time.sleep(self.startup_wait_seconds)
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self.process is None:
            return
        if self.process.poll() is None and self.process.stdin:
            self.process.stdin.close()
        try:
            self.process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=5)

    def initialize(self) -> dict[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "day33-support-service", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return response

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self._request("tools/call", {"name": name, "arguments": arguments or {}})
        structured = result.get("structuredContent")
        if isinstance(structured, dict):
            return structured
        content = result.get("content")
        if isinstance(content, list):
            text = "\n".join(
                item.get("text", "")
                for item in content
                if isinstance(item, dict) and item.get("type") == "text"
            )
            if text:
                return {"text": text}
        return result

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if not self.process or not self.process.stdin:
            raise MCPClientError("MCP client is not connected")
        write_message(self.process.stdin, {"jsonrpc": "2.0", "method": method, "params": params})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self.process or not self.process.stdin or not self.process.stdout:
            raise MCPClientError("MCP client is not connected")
        self.request_id += 1
        write_message(
            self.process.stdin,
            {"jsonrpc": "2.0", "id": self.request_id, "method": method, "params": params},
        )
        response = read_message(self.process.stdout)
        if response is None:
            raise MCPClientError("MCP server closed the connection")
        if response.get("id") != self.request_id:
            raise MCPClientError("Unexpected MCP response id")
        if "error" in response:
            raise MCPClientError(str(response["error"].get("message", "Unknown MCP error")))
        return dict(response.get("result", {}))
