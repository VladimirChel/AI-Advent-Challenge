from __future__ import annotations

import logging
import sys
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from summary_service import build_summary


logging.basicConfig(level=logging.INFO)

SERVER_NAME = "mqtt-summary-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "mqtt_summary_status",
        "description": "Returns summary server status and supported modes.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "build_mqtt_summary",
        "description": "Builds a concise deterministic summary from mqtt readings.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "readings": {"type": "array"},
                "title": {"type": "string"},
                "mode": {"type": "string"},
                "thresholds": {"type": "object"},
            },
            "required": ["readings"],
            "additionalProperties": False,
        },
    },
]


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def tool_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [{"type": "text", "text": str(payload)}],
        "structuredContent": payload,
        "isError": False,
    }


def handle_request(message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        return success_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return success_response(request_id, {"tools": TOOLS})

    if method == "tools/call":
        params = message.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "mqtt_summary_status":
            return success_response(
                request_id,
                tool_result(
                    {
                        "ok": True,
                        "summary_mode": "deterministic",
                        "supported_modes": ["brief", "compact"],
                    }
                ),
            )

        if tool_name == "build_mqtt_summary":
            readings = arguments.get("readings")
            if not isinstance(readings, list):
                return error_response(request_id, -32602, "Missing required argument: readings")
            payload = build_summary(
                readings=readings,
                title=arguments.get("title"),
                mode=str(arguments.get("mode") or "brief"),
                thresholds=arguments.get("thresholds"),
            )
            return success_response(request_id, tool_result(payload))

        return error_response(request_id, -32601, f"Unknown tool: {tool_name}")

    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    while True:
        message = read_message(stdin=sys.stdin)
        if message is None:
            break
        if "id" not in message:
            handle_request(message)
            continue

        try:
            response = handle_request(message)
        except Exception as exc:  # noqa: BLE001
            write_log(f"Tool call failed: {exc}")
            response = error_response(message.get("id"), -32000, str(exc))

        if response is not None:
            write_message(stdout=sys.stdout, message=response)


if __name__ == "__main__":
    main()
