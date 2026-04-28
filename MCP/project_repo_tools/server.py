from __future__ import annotations

import sys
import traceback
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from repo_tools import git_branch, list_dir, read_file


SERVER_NAME = "project-repo-tools"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "git_branch",
        "description": "Return git branches for a local repository.",
        "inputSchema": {
            "type": "object",
            "properties": {"project_root": {"type": "string"}},
            "required": ["project_root"],
            "additionalProperties": False,
        },
    },
    {
        "name": "list_dir",
        "description": "List files and folders inside the project root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "path": {"type": "string"},
            },
            "required": ["project_root"],
            "additionalProperties": False,
        },
    },
    {
        "name": "read_file",
        "description": "Read a text file from inside the project root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "path": {"type": "string"},
                "max_chars": {"type": "integer", "minimum": 200, "maximum": 50000},
            },
            "required": ["project_root", "path"],
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

        if tool_name == "git_branch":
            return success_response(request_id, tool_result(git_branch(arguments["project_root"])))
        if tool_name == "list_dir":
            return success_response(
                request_id,
                tool_result(list_dir(arguments["project_root"], arguments.get("path", "."))),
            )
        if tool_name == "read_file":
            return success_response(
                request_id,
                tool_result(
                    read_file(
                        arguments["project_root"],
                        arguments["path"],
                        int(arguments.get("max_chars", 12000)),
                    )
                ),
            )
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
