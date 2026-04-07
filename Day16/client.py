from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
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
                "clientInfo": {"name": "wb-temperature-client", "version": "0.1.0"},
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
    parser = argparse.ArgumentParser(description="Simple MCP client for Wireen Board temperatures.")
    parser.add_argument(
        "command",
        choices=["tools", "status", "sensors", "latest", "sensor", "shell"],
        help="Which MCP request to run.",
    )
    parser.add_argument("--sensor-id", help="Sensor id for the sensor command.")
    parser.add_argument(
        "--wait-seconds",
        type=float,
        default=3.0,
        help="How long to wait after server start so MQTT can connect and receive retained values.",
    )
    args = parser.parse_args()

    server_script = Path(__file__).with_name("server.py")

    with MCPClient(server_script) as client:
        if args.wait_seconds > 0:
            time.sleep(args.wait_seconds)
        if args.command == "shell":
            run_shell(client)
            return
        if args.command == "tools":
            result = client.list_tools()
        elif args.command == "status":
            result = client.call_tool("mqtt_status")
        elif args.command == "sensors":
            result = client.call_tool("list_temperature_sensors")
        elif args.command == "latest":
            result = client.call_tool("get_latest_temperatures")
        else:
            if not args.sensor_id:
                raise SystemExit("--sensor-id is required for command 'sensor'")
            result = client.call_tool("get_temperature_sensor", {"sensor_id": args.sensor_id})

    print(json.dumps(result, ensure_ascii=False, indent=2))


def run_shell(client: MCPClient) -> None:
    print("Interactive MCP shell. Commands: tools, status, sensors, latest, sensor <sensor_id>, exit")
    while True:
        try:
            raw_command = input("> ").strip()
        except EOFError:
            print()
            break

        if not raw_command:
            continue
        if raw_command in {"exit", "quit"}:
            break

        try:
            command, *rest = raw_command.split(maxsplit=1)
            if command == "tools":
                result = client.list_tools()
            elif command == "status":
                result = client.call_tool("mqtt_status")
            elif command == "sensors":
                result = client.call_tool("list_temperature_sensors")
            elif command == "latest":
                result = client.call_tool("get_latest_temperatures")
            elif command == "sensor":
                if not rest:
                    print("Usage: sensor <sensor_id>")
                    continue
                result = client.call_tool("get_temperature_sensor", {"sensor_id": rest[0]})
            else:
                print(f"Unknown command: {command}")
                continue
        except Exception as exc:  # noqa: BLE001
            print(f"Error: {exc}")
            continue

        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
