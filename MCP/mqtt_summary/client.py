from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from mcp_stdio import read_message, write_message


class MCPClient:
    def __init__(self, server_script: Path) -> None:
        self._server_script = server_script
        self._process: subprocess.Popen[bytes] | None = None
        self._request_id = 0

    def __enter__(self) -> "MCPClient":
        self._process = subprocess.Popen(
            [sys.executable, str(self._server_script)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
        self.initialize()
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._process and self._process.poll() is None:
            if self._process.stdin:
                self._process.stdin.close()
            self._process.wait(timeout=5)

    def initialize(self) -> dict[str, Any]:
        response = self._request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "mqtt-summary-client", "version": "0.1.0"},
            },
        )
        self._notify("notifications/initialized", {})
        return response

    def list_tools(self) -> dict[str, Any]:
        return self._request("tools/list", {})

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        return self._request("tools/call", {"name": name, "arguments": arguments or {}})

    def _notify(self, method: str, params: dict[str, Any]) -> None:
        if not self._process or not self._process.stdin:
            raise RuntimeError("Client is not connected")
        write_message(
            stdout=self._process.stdin,
            message={"jsonrpc": "2.0", "method": method, "params": params},
        )

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        if not self._process or not self._process.stdin or not self._process.stdout:
            raise RuntimeError("Client is not connected")

        self._request_id += 1
        write_message(
            stdout=self._process.stdin,
            message={"jsonrpc": "2.0", "id": self._request_id, "method": method, "params": params},
        )
        response = read_message(stdin=self._process.stdout)
        if response is None:
            raise RuntimeError("Server closed the connection")
        if "error" in response:
            raise RuntimeError(response["error"]["message"])
        return response["result"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Simple MCP client for MQTT summary.")
    parser.add_argument("command", choices=["tools", "status", "summary"], help="Which MCP request to run.")
    parser.add_argument("--readings-file", help="Path to JSON file with readings array.")
    parser.add_argument("--title", default="MQTT monitoring summary", help="Summary title.")
    parser.add_argument("--mode", default="brief", choices=["brief", "compact"], help="Summary output mode.")
    parser.add_argument("--min-value", type=float, help="Optional minimum threshold.")
    parser.add_argument("--max-value", type=float, help="Optional maximum threshold.")
    args = parser.parse_args()

    server_script = Path(__file__).with_name("server.py")

    with MCPClient(server_script) as client:
        if args.command == "tools":
            result = client.list_tools()
        elif args.command == "status":
            result = client.call_tool("mqtt_summary_status")
        else:
            if not args.readings_file:
                raise SystemExit("--readings-file is required for command 'summary'")
            readings = json.loads(Path(args.readings_file).read_text(encoding="utf-8-sig"))
            thresholds: dict[str, float] = {}
            if args.min_value is not None:
                thresholds["min_value"] = args.min_value
            if args.max_value is not None:
                thresholds["max_value"] = args.max_value
            result = client.call_tool(
                "build_mqtt_summary",
                {
                    "readings": readings,
                    "title": args.title,
                    "mode": args.mode,
                    "thresholds": thresholds or None,
                },
            )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
