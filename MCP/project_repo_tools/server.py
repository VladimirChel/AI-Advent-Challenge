from __future__ import annotations

import sys
import traceback
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from repo_tools import check_invariants, count_files, create_document, find_files, git_branch, list_dir, read_file, search_text, tree_dir


SERVER_NAME = "project-repo-tools"
SERVER_VERSION = "0.3.0"

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
    {
        "name": "tree_dir",
        "description": "Return a recursive directory tree inside the project root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "path": {"type": "string"},
                "max_depth": {"type": "integer", "minimum": 0, "maximum": 20},
                "max_entries": {"type": "integer", "minimum": 1, "maximum": 10000},
            },
            "required": ["project_root"],
            "additionalProperties": False,
        },
    },
    {
        "name": "find_files",
        "description": "Find files inside the project root by glob pattern, optional regex on filename or relative path. For README-like files anywhere in the repo, prefer glob='**/*' and name_regex='readme' with case_sensitive=false instead of a root-only glob like 'README*'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "glob": {"type": "string"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 5000},
                "name_regex": {"type": "string"},
                "path_regex": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            },
            "required": ["project_root"],
            "additionalProperties": False,
        },
    },
    {
        "name": "count_files",
        "description": "Count files inside the project root by glob pattern and optional case-insensitive regex filters. Use this for exact counts like README files. For README-like files anywhere in the repo, prefer glob='**/*' and name_regex='readme' with case_sensitive=false instead of a root-only glob like 'README*'.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "glob": {"type": "string"},
                "name_regex": {"type": "string"},
                "path_regex": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
            },
            "required": ["project_root"],
            "additionalProperties": False,
        },
    },
    {
        "name": "search_text",
        "description": "Search text across project files using a regex pattern.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "pattern": {"type": "string"},
                "glob": {"type": "string"},
                "case_sensitive": {"type": "boolean"},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 2000},
                "context_chars": {"type": "integer", "minimum": 20, "maximum": 500},
            },
            "required": ["project_root", "pattern"],
            "additionalProperties": False,
        },
    },
    {
        "name": "check_invariants",
        "description": "Check files against JSON rules with required and forbidden regex patterns.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "rules_path": {"type": "string"},
                "glob": {"type": "string"},
                "max_files": {"type": "integer", "minimum": 1, "maximum": 5000},
            },
            "required": ["project_root", "rules_path"],
            "additionalProperties": False,
        },
    },
    {
        "name": "create_document",
        "description": "Create only README.md or report.html inside the project root.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project_root": {"type": "string"},
                "path": {"type": "string"},
                "file_type": {"type": "string", "enum": ["readme_md", "report_html"]},
                "title": {"type": "string"},
                "content": {"type": "string"},
            },
            "required": ["project_root", "path", "file_type"],
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
        if tool_name == "tree_dir":
            return success_response(
                request_id,
                tool_result(
                    tree_dir(
                        arguments["project_root"],
                        arguments.get("path", "."),
                        int(arguments.get("max_depth", 4)),
                        int(arguments.get("max_entries", 500)),
                    )
                ),
            )
        if tool_name == "find_files":
            return success_response(
                request_id,
                tool_result(
                    find_files(
                        arguments["project_root"],
                        arguments.get("glob", "**/*"),
                        int(arguments.get("max_results", 200)),
                        arguments.get("name_regex"),
                        arguments.get("path_regex"),
                        bool(arguments.get("case_sensitive", False)),
                    )
                ),
            )
        if tool_name == "count_files":
            return success_response(
                request_id,
                tool_result(
                    count_files(
                        arguments["project_root"],
                        arguments.get("glob", "**/*"),
                        arguments.get("name_regex"),
                        arguments.get("path_regex"),
                        bool(arguments.get("case_sensitive", False)),
                    )
                ),
            )
        if tool_name == "search_text":
            return success_response(
                request_id,
                tool_result(
                    search_text(
                        arguments["project_root"],
                        arguments["pattern"],
                        arguments.get("glob", "**/*"),
                        bool(arguments.get("case_sensitive", False)),
                        int(arguments.get("max_results", 200)),
                        int(arguments.get("context_chars", 120)),
                    )
                ),
            )
        if tool_name == "check_invariants":
            return success_response(
                request_id,
                tool_result(
                    check_invariants(
                        arguments["project_root"],
                        arguments["rules_path"],
                        arguments.get("glob", "**/*"),
                        int(arguments.get("max_files", 500)),
                    )
                ),
            )
        if tool_name == "create_document":
            return success_response(
                request_id,
                tool_result(
                    create_document(
                        arguments["project_root"],
                        arguments["path"],
                        arguments["file_type"],
                        str(arguments.get("title", "")),
                        str(arguments.get("content", "")),
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
