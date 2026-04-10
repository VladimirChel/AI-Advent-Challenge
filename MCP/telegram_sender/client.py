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
                "clientInfo": {"name": "telegram-sender-client", "version": "0.1.0"},
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
    parser = argparse.ArgumentParser(description="Simple MCP client for Telegram sender.")
    parser.add_argument("command", choices=["tools", "status", "me", "send"], help="Which MCP request to run.")
    parser.add_argument("--text", help="Message text for send.")
    parser.add_argument("--chat-id", help="Telegram chat id. Optional if TELEGRAM_DEFAULT_CHAT_ID is set.")
    parser.add_argument("--parse-mode", help="Telegram parse mode, e.g. MarkdownV2 or HTML.")
    parser.add_argument("--disable-web-page-preview", action="store_true", help="Disable link preview.")
    parser.add_argument("--disable-notification", action="store_true", help="Send silently.")
    parser.add_argument("--protect-content", action="store_true", help="Protect forwarded content.")
    parser.add_argument("--message-thread-id", type=int, help="Forum topic/thread id.")
    args = parser.parse_args()

    server_script = Path(__file__).with_name("server.py")

    with MCPClient(server_script) as client:
        if args.command == "tools":
            result = client.list_tools()
        elif args.command == "status":
            result = client.call_tool("telegram_sender_status")
        elif args.command == "me":
            result = client.call_tool("telegram_get_me")
        else:
            if not args.text:
                raise SystemExit("--text is required for command 'send'")
            result = client.call_tool(
                "send_telegram_message",
                {
                    "text": args.text,
                    "chat_id": args.chat_id,
                    "parse_mode": args.parse_mode,
                    "disable_web_page_preview": args.disable_web_page_preview,
                    "disable_notification": args.disable_notification,
                    "protect_content": args.protect_content,
                    "message_thread_id": args.message_thread_id,
                },
            )

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
