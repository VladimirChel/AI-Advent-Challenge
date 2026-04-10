from __future__ import annotations

import json
import os
import socket
import ssl
from typing import Any
from urllib import error, request

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


def load_dotenv(dotenv_path: str | None = None) -> None:
    dotenv_path = dotenv_path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, encoding="utf-8") as dotenv_file:
        for raw_line in dotenv_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class TelegramBotClient:
    def __init__(self) -> None:
        load_dotenv()
        self._bot_token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
        self._default_chat_id = os.getenv("TELEGRAM_DEFAULT_CHAT_ID", "").strip() or None
        self._default_parse_mode = os.getenv("TELEGRAM_DEFAULT_PARSE_MODE", "").strip() or None
        self._api_base = "https://api.telegram.org"

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(self._bot_token),
            "default_chat_id": self._default_chat_id,
            "default_parse_mode": self._default_parse_mode,
        }

    def get_me(self) -> dict[str, Any]:
        return self._call("getMe", {})

    def send_message(
        self,
        text: str,
        chat_id: str | int | None = None,
        parse_mode: str | None = None,
        disable_web_page_preview: bool = False,
        disable_notification: bool = False,
        protect_content: bool = False,
        message_thread_id: int | None = None,
    ) -> dict[str, Any]:
        resolved_chat_id = chat_id if chat_id not in (None, "") else self._default_chat_id
        if resolved_chat_id in (None, ""):
            raise ValueError("chat_id is required when TELEGRAM_DEFAULT_CHAT_ID is not configured")
        if not text.strip():
            raise ValueError("text must not be empty")

        payload: dict[str, Any] = {
            "chat_id": resolved_chat_id,
            "text": text,
            "disable_notification": disable_notification,
            "protect_content": protect_content,
        }

        resolved_parse_mode = parse_mode or self._default_parse_mode
        if resolved_parse_mode:
            payload["parse_mode"] = resolved_parse_mode
        if disable_web_page_preview:
            payload["link_preview_options"] = {"is_disabled": True}
        if message_thread_id is not None:
            payload["message_thread_id"] = message_thread_id

        return self._call("sendMessage", payload)

    def _call(self, method: str, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._bot_token:
            raise RuntimeError("Missing TELEGRAM_BOT_TOKEN in environment or .env")

        url = f"{self._api_base}/bot{self._bot_token}/{method}"
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            url=url,
            data=body,
            headers={"Content-Type": "application/json; charset=utf-8"},
            method="POST",
        )

        try:
            with request.urlopen(http_request, timeout=30) as response:
                response_data = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Telegram API HTTP {exc.code}: {error_body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Telegram API connection error: {exc.reason}") from exc
        except ssl.SSLError as exc:
            raise RuntimeError(
                "Telegram API SSL error. Check system certificates, proxy/VPN settings, or corporate HTTPS interception. "
                f"Original error: {exc}"
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError("Telegram API request timed out after 30 seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"Telegram API OS/network error: {exc}") from exc

        parsed = json.loads(response_data)
        if not parsed.get("ok"):
            raise RuntimeError(f"Telegram API error: {parsed}")
        return parsed["result"]
