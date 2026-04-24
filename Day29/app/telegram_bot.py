from __future__ import annotations

import html
import time
from typing import Any

import requests

from app.analytics import AnalyticsStore
from app.config import AppConfig
from app.report_parser import build_snapshots
from app.service import DebtAssistantService


class TelegramBot:
    def __init__(self, config: AppConfig) -> None:
        if not config.telegram_bot_token:
            raise ValueError("TELEGRAM_BOT_TOKEN is required")
        self.config = config
        self.base_url = f"https://api.telegram.org/bot{config.telegram_bot_token}"
        self.offset = 0
        self.anonymized_mode_by_chat: dict[int, bool] = {}

    def _allowed(self, chat_id: int) -> bool:
        raw = self.config.telegram_allowed_chat_ids.strip()
        if not raw:
            return True
        allowed = {item.strip() for item in raw.split(",") if item.strip()}
        return str(chat_id) in allowed

    def get_updates(self) -> list[dict[str, Any]]:
        response = requests.get(
            f"{self.base_url}/getUpdates",
            params={
                "offset": self.offset,
                "timeout": self.config.telegram_poll_timeout_seconds,
                "allowed_updates": ["message"],
            },
            timeout=self.config.telegram_poll_timeout_seconds + 10,
        )
        response.raise_for_status()
        payload = response.json()
        if not payload.get("ok"):
            raise RuntimeError(f"Telegram API error: {payload}")
        return payload.get("result", [])

    def send_message(self, chat_id: int, text: str) -> None:
        response = requests.post(
            f"{self.base_url}/sendMessage",
            json={
                "chat_id": chat_id,
                "text": text,
                "parse_mode": self.config.telegram_parse_mode,
                "disable_web_page_preview": True,
            },
            timeout=30,
        )
        response.raise_for_status()

    def run(self) -> None:
        print("Telegram bot polling started")
        while True:
            updates = self.get_updates()
            for update in updates:
                self.offset = update["update_id"] + 1
                message = update.get("message") or {}
                chat = message.get("chat") or {}
                chat_id = chat.get("id")
                text = (message.get("text") or "").strip()
                if not chat_id or not text:
                    continue
                if not self._allowed(int(chat_id)):
                    self.send_message(int(chat_id), "Этот чат не разрешен для MVP-бота.")
                    continue
                self.handle_message(int(chat_id), text)
            time.sleep(1)

    def handle_message(self, chat_id: int, text: str) -> None:
        command = self._extract_command(text)
        anonymized = self.anonymized_mode_by_chat.get(chat_id, False)

        if command == "/start":
            self.send_message(
                chat_id,
                "Бот по дебиторской задолженности запущен.\n"
                "Команды: /help, /today, /top, /reload, /anon_on, /anon_off, /mode",
            )
            return
        if command == "/help":
            self.send_message(
                chat_id,
                "Команды и примеры:\n"
                "- /today\n"
                "- /top\n"
                "- /reload\n"
                "- /anon_on\n"
                "- /anon_off\n"
                "- /mode\n"
                "- какая общая дебиторка сегодня\n"
                "- топ должников\n"
                "- что у Григорьева Юлия Алексеевна\n"
                "- как изменилась просрочка за 3 дня",
            )
            return
        if command == "/anon_on":
            self.anonymized_mode_by_chat[chat_id] = True
            self.send_message(chat_id, "Режим обезличенных данных включен.")
            return
        if command == "/anon_off":
            self.anonymized_mode_by_chat[chat_id] = False
            self.send_message(chat_id, "Режим обезличенных данных выключен.")
            return
        if command == "/mode":
            self.send_message(chat_id, f"Текущий режим: {'обезличенный' if anonymized else 'обычный'}.")
            return
        if command == "/today":
            self._answer_and_send(chat_id, "/today", anonymized=anonymized)
            return
        if command == "/top":
            self._answer_and_send(chat_id, "/top", anonymized=anonymized)
            return
        if command == "/reload":
            paths = build_snapshots(self.config.documents_dir, self.config.snapshots_dir)
            self.send_message(chat_id, f"Индекс обновлен. Снимков: {len(paths)}")
            return

        self._answer_and_send(chat_id, text, anonymized=anonymized)

    def _answer_and_send(self, chat_id: int, text: str, anonymized: bool) -> None:
        store = AnalyticsStore.from_dir(self.config.snapshots_dir)
        service = DebtAssistantService(self.config, store)
        answer = service.answer(
            text,
            conversation_id=f"telegram-{chat_id}",
            anonymized=anonymized,
        )
        self.send_message(chat_id, html.escape(answer.text))

    @staticmethod
    def _extract_command(text: str) -> str | None:
        normalized = text.strip()
        if not normalized.startswith("/"):
            return None
        first_token = normalized.split()[0]
        command = first_token.split("@", 1)[0]
        return command.casefold()
