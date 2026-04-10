from __future__ import annotations

import logging
import sys
from typing import Any

from mcp_stdio import read_message, write_message
from pipeline_runner import run_pipeline


logging.basicConfig(level=logging.INFO)

SERVER_NAME = "day19-mqtt-pipeline-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "pipeline_status",
        "description": "Returns basic status information for the Day19 MQTT pipeline server.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "run_mqtt_pipeline",
        "description": "Runs the full Day19 pipeline: collect MQTT data, build summary, and optionally send to Telegram.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "dry_run": {"type": "boolean"},
                "send_on_error": {"type": "boolean"},
            },
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

        if tool_name == "pipeline_status":
            return success_response(
                request_id,
                tool_result(
                    {
                        "ok": True,
                        "server": SERVER_NAME,
                        "version": SERVER_VERSION,
                        "tools": [tool["name"] for tool in TOOLS],
                    }
                ),
            )

        if tool_name == "run_mqtt_pipeline":
            dry_run = bool(arguments.get("dry_run", False))
            send_on_error = bool(arguments.get("send_on_error", False))
            payload = run_pipeline(send_enabled=not dry_run, send_on_error=send_on_error)
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
            logging.exception("Tool call failed")
            response = error_response(message.get("id"), -32000, str(exc))

        if response is not None:
            write_message(stdout=sys.stdout, message=response)


if __name__ == "__main__":
    main()
