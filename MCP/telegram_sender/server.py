from __future__ import annotations

import logging
import sys
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from telegram_sender import TelegramBotClient


logging.basicConfig(level=logging.INFO)

SERVER_NAME = "telegram-sender-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "telegram_sender_status",
        "description": "Returns whether the Telegram bot token and default chat id are configured.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "telegram_get_me",
        "description": "Returns Telegram bot profile information using getMe.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "send_telegram_message",
        "description": "Sends a Telegram message through the configured bot.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "chat_id": {"type": ["string", "integer"]},
                "parse_mode": {"type": "string"},
                "disable_web_page_preview": {"type": "boolean"},
                "disable_notification": {"type": "boolean"},
                "protect_content": {"type": "boolean"},
                "message_thread_id": {"type": "integer"},
            },
            "required": ["text"],
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
        "content": [
            {
                "type": "text",
                "text": str(payload),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def handle_request(message: dict[str, Any], bot: TelegramBotClient) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        return success_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
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

        if tool_name == "telegram_sender_status":
            return success_response(request_id, tool_result(bot.status()))

        if tool_name == "telegram_get_me":
            return success_response(request_id, tool_result(bot.get_me()))

        if tool_name == "send_telegram_message":
            text = arguments.get("text")
            if not text:
                return error_response(request_id, -32602, "Missing required argument: text")
            result = bot.send_message(
                text=text,
                chat_id=arguments.get("chat_id"),
                parse_mode=arguments.get("parse_mode"),
                disable_web_page_preview=bool(arguments.get("disable_web_page_preview", False)),
                disable_notification=bool(arguments.get("disable_notification", False)),
                protect_content=bool(arguments.get("protect_content", False)),
                message_thread_id=arguments.get("message_thread_id"),
            )
            return success_response(request_id, tool_result(result))

        return error_response(request_id, -32601, f"Unknown tool: {tool_name}")

    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    bot = TelegramBotClient()

    while True:
        message = read_message(stdin=sys.stdin)
        if message is None:
            break
        if "id" not in message:
            handle_request(message, bot)
            continue

        try:
            response = handle_request(message, bot)
        except Exception as exc:  # noqa: BLE001
            write_log(f"Tool call failed: {exc}")
            response = error_response(message.get("id"), -32000, str(exc))

        if response is not None:
            write_message(stdout=sys.stdout, message=response)


if __name__ == "__main__":
    main()
