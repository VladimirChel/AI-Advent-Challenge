from __future__ import annotations

import sys
import traceback
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from support_store import find_user_tickets, get_ticket, get_user, resolve_user_identity


SERVER_NAME = "support-context"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "get_user",
        "description": "Return user profile by user_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"user_id": {"type": "string"}},
            "required": ["user_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_ticket",
        "description": "Return support ticket by ticket_id.",
        "inputSchema": {
            "type": "object",
            "properties": {"ticket_id": {"type": "string"}},
            "required": ["ticket_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_user_tickets",
        "description": "Return recent tickets for the user.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "user_id": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20},
            },
            "required": ["user_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "resolve_user_identity",
        "description": "Match an introduced name or username to a user account.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
            },
            "required": ["query"],
            "additionalProperties": False,
        },
    },
]


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


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

        if tool_name == "get_user":
            return success_response(request_id, tool_result(get_user(arguments["user_id"])))
        if tool_name == "get_ticket":
            return success_response(request_id, tool_result(get_ticket(arguments["ticket_id"])))
        if tool_name == "find_user_tickets":
            return success_response(
                request_id,
                tool_result(find_user_tickets(arguments["user_id"], int(arguments.get("limit", 5)))),
            )
        if tool_name == "resolve_user_identity":
            return success_response(request_id, tool_result(resolve_user_identity(arguments["query"])))
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
            write_log(traceback.format_exc())
            response = error_response(message.get("id"), -32000, f"Internal server error: {exc}")
        if response is not None:
            write_message(stdout=sys.stdout, message=response)


if __name__ == "__main__":
    main()
