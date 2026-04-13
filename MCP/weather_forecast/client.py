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
                "clientInfo": {"name": "weather-forecast-client", "version": "0.1.0"},
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
    parser = argparse.ArgumentParser(description="Simple MCP client for weather forecast.")
    parser.add_argument("command", choices=["tools", "status", "geocode", "current", "forecast"])
    parser.add_argument("--location", help="Human-readable location name, e.g. Yekaterinburg.")
    parser.add_argument("--latitude", type=float, help="Latitude for direct lookup.")
    parser.add_argument("--longitude", type=float, help="Longitude for direct lookup.")
    parser.add_argument("--timezone", help="Timezone for the forecast, defaults to auto or geocoded timezone.")
    parser.add_argument("--language", help="Language code for geocoding, e.g. en or ru.")
    parser.add_argument("--count", type=int, default=5, help="How many geocoding candidates to return.")
    parser.add_argument("--days", type=int, default=3, help="How many forecast days to return.")
    args = parser.parse_args()

    server_script = Path(__file__).with_name("server.py")

    with MCPClient(server_script) as client:
        if args.command == "tools":
            result = client.list_tools()
        elif args.command == "status":
            result = client.call_tool("weather_status")
        elif args.command == "geocode":
            if not args.location:
                raise SystemExit("--location is required for command 'geocode'")
            result = client.call_tool(
                "weather_geocode",
                {
                    "location": args.location,
                    "count": args.count,
                    "language": args.language,
                },
            )
        elif args.command == "current":
            if not args.location and (args.latitude is None or args.longitude is None):
                raise SystemExit("Provide --location or both --latitude and --longitude for command 'current'")
            result = client.call_tool(
                "get_current_weather",
                {
                    "location": args.location,
                    "latitude": args.latitude,
                    "longitude": args.longitude,
                    "timezone": args.timezone,
                    "language": args.language,
                },
            )
        else:
            if not args.location and (args.latitude is None or args.longitude is None):
                raise SystemExit("Provide --location or both --latitude and --longitude for command 'forecast'")
            result = client.call_tool(
                "get_weather_forecast",
                {
                    "location": args.location,
                    "latitude": args.latitude,
                    "longitude": args.longitude,
                    "days": args.days,
                    "timezone": args.timezone,
                    "language": args.language,
                },
            )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
