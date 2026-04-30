#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


DEFAULT_API_URL = os.environ.get("SUPPORT_API_URL", "http://127.0.0.1:8010").rstrip("/")
DEFAULT_HISTORY_DIR = Path.home() / ".support_assistant_cli"


def enable_windows_ansi() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-11)
        mode = ctypes.c_uint32()
        if kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            kernel32.SetConsoleMode(handle, mode.value | 0x0004)
    except Exception:
        pass


enable_windows_ansi()


class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RED = "\033[31m"
    GREEN = "\033[32m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


@dataclass
class UIState:
    api_url: str
    ticket_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    suggested_tickets: list[dict[str, Any]] = field(default_factory=list)
    conversation: list[dict[str, Any]] = field(default_factory=list)


class SupportCLIError(RuntimeError):
    pass


class SupportAPIClient:
    def __init__(self, api_url: str) -> None:
        self.api_url = api_url.rstrip("/")

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.api_url}/health", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.URLError as exc:
            raise SupportCLIError(
                f"Не удалось подключиться к сервису поддержки по адресу {self.api_url}."
            ) from exc

    def ask(
        self,
        *,
        question: str,
        ticket_id: str | None,
        user_id: str | None,
        user_name: str | None,
    ) -> dict[str, Any]:
        payload = {
            "question": question,
            "ticket_id": ticket_id,
            "user_id": user_id,
            "user_name": user_name,
        }
        request = urllib.request.Request(
            f"{self.api_url}/support/answer",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=180) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise SupportCLIError(f"Сервис вернул HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise SupportCLIError("Сервис недоступен. Проверь, что Day33 backend запущен.") from exc


BANNER = f"""{C.CYAN}{C.BOLD}
╔══════════════════════════════════════════════════════╗
║              SUPPORT ASSISTANT DAY33                ║
║          мини-интерфейс поддержки пользователей     ║
╚══════════════════════════════════════════════════════╝{C.RESET}
"""

HELP = f"""{C.BOLD}Команды:{C.RESET}
  /help                 показать справку
  /ticket <id>          установить ticket_id
  /user <id>            установить user_id
  /name <text>          представиться по имени или username
  `<номер>`             выбрать тикет из предложенного списка
  /status               показать текущий контекст
  /backend <url>        сменить URL backend
  /clear                очистить историю сессии
  /save [file]          сохранить историю в JSON
  /exit                 выход
"""


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def resolve_history_dir() -> Path:
    candidates = [
        DEFAULT_HISTORY_DIR,
        Path(__file__).resolve().parent / "output" / "history",
    ]
    for path in candidates:
        try:
            path.mkdir(parents=True, exist_ok=True)
            return path
        except PermissionError:
            continue
    raise SupportCLIError("Не удалось создать каталог для сохранения истории.")


def print_info(text: str) -> None:
    print(f"{C.GRAY}› {text}{C.RESET}")


def print_error(text: str) -> None:
    print(f"{C.RED}{C.BOLD}Ошибка:{C.RESET} {text}")


def print_user_prompt(text: str) -> None:
    print(f"{C.GREEN}{C.BOLD}you{C.RESET} {C.DIM}›{C.RESET} {text}")


def print_assistant_header() -> None:
    print(f"{C.MAGENTA}{C.BOLD}support{C.RESET} {C.DIM}›{C.RESET} ", end="")


def print_sources_block(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    print(f"\n{C.BLUE}{C.BOLD}Источники:{C.RESET}")
    for item in sources[:4]:
        source = item.get("source", "")
        section = item.get("section", "")
        score = item.get("score")
        score_text = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
        print(f"{C.BLUE}  - {source} | {section}{score_text}{C.RESET}")


def print_ticket_suggestions(tickets: list[dict[str, Any]]) -> None:
    if not tickets:
        return
    print(f"\n{C.CYAN}{C.BOLD}Последние тикеты:{C.RESET}")
    for index, ticket in enumerate(tickets, start=1):
        ticket_id = ticket.get("ticket_id", "")
        subject = ticket.get("subject", "")
        status = ticket.get("status", "")
        print(f"{C.CYAN}  {index}. {ticket_id} | {subject} | {status}{C.RESET}")


def save_chat(state: UIState, file_path: str | None = None) -> Path:
    history_dir = resolve_history_dir()
    path = Path(file_path) if file_path else history_dir / f"support_chat_{now_stamp()}.json"
    data = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "api_url": state.api_url,
        "ticket_id": state.ticket_id,
        "user_id": state.user_id,
        "user_name": state.user_name,
        "suggested_tickets": state.suggested_tickets,
        "conversation": state.conversation,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def print_status(state: UIState) -> None:
    print_info(f"Backend: {state.api_url}")
    print_info(f"ticket_id: {state.ticket_id or 'not set'}")
    print_info(f"user_id: {state.user_id or 'not set'}")
    print_info(f"user_name: {state.user_name or 'not set'}")
    print_info(f"suggested tickets: {len(state.suggested_tickets)}")
    print_info(f"messages in session: {len(state.conversation)}")


def handle_command(raw: str, state: UIState, client: SupportAPIClient) -> tuple[bool, SupportAPIClient]:
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print(HELP)
    elif cmd == "/ticket":
        state.ticket_id = arg or None
        state.suggested_tickets.clear()
        print_info(f"ticket_id: {state.ticket_id or 'cleared'}")
    elif cmd == "/user":
        state.user_id = arg or None
        print_info(f"user_id: {state.user_id or 'cleared'}")
    elif cmd == "/name":
        state.user_name = arg or None
        state.ticket_id = None
        state.suggested_tickets.clear()
        print_info(f"user_name: {state.user_name or 'cleared'}")
    elif cmd == "/status":
        print_status(state)
    elif cmd == "/backend":
        if not arg:
            print_error("Укажи URL, например: /backend http://127.0.0.1:8010")
        else:
            state.api_url = arg.rstrip("/")
            client = SupportAPIClient(state.api_url)
            client.health()
            print_info(f"Новый backend: {state.api_url}")
    elif cmd == "/clear":
        state.conversation.clear()
        state.suggested_tickets.clear()
        print_info("История сессии очищена.")
    elif cmd == "/save":
        path = save_chat(state, arg or None)
        print_info(f"История сохранена: {path}")
    elif cmd in {"/exit", "/quit"}:
        return False, client
    else:
        print_error("Неизвестная команда. Введи /help")
    return True, client


def interactive_loop(state: UIState, client: SupportAPIClient) -> int:
    print(BANNER)
    print_info(f"Backend: {state.api_url}")
    print_info("Введи /help для списка команд.")
    if state.ticket_id or state.user_id or state.user_name:
        print_status(state)
    else:
        print_info("Сначала представьтесь: напишите имя или username.")
    print()

    while True:
        try:
            raw = input(f"{C.GREEN}{C.BOLD}you{C.RESET} {C.DIM}›{C.RESET} ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nДо встречи.")
            return 0

        if not raw:
            continue

        if raw.startswith("/"):
            try:
                keep_running, client = handle_command(raw, state, client)
                if not keep_running:
                    print("До встречи.")
                    return 0
            except SupportCLIError as exc:
                print_error(str(exc))
            print()
            continue

        if raw.isdigit() and state.suggested_tickets:
            index = int(raw) - 1
            if 0 <= index < len(state.suggested_tickets):
                state.ticket_id = str(state.suggested_tickets[index].get("ticket_id", "") or "")
                state.suggested_tickets.clear()
                print_info(f"Выбран ticket_id: {state.ticket_id}")
            else:
                print_error("Нет тикета с таким номером.")
            print()
            continue

        if not state.ticket_id and not state.user_id and not state.user_name:
            state.user_name = raw
            print_info(f"Спасибо. Запомнил представление: {state.user_name}")
            print_info("Теперь можете задать вопрос по продукту.")
            print()
            continue

        try:
            result = client.ask(
                question=raw,
                ticket_id=state.ticket_id,
                user_id=state.user_id,
                user_name=state.user_name,
            )
        except SupportCLIError as exc:
            print_error(str(exc))
            print()
            continue

        answer = str(result.get("answer", "")).strip()
        if result.get("needs_user_identity"):
            print_assistant_header()
            print(answer)
            print()
            state.user_name = None
            state.user_id = None
            state.suggested_tickets.clear()
            print_info("Представьтесь ещё раз точнее: можно указать username.")
            print()
            continue

        resolved_summary = result.get("user_summary") or {}
        if resolved_summary.get("user_id"):
            state.user_id = resolved_summary.get("user_id")
        if resolved_summary.get("username"):
            state.user_name = resolved_summary.get("username")
        state.suggested_tickets = list(result.get("suggested_tickets", []))

        state.conversation.append(
            {
                "question": raw,
                "answer": answer,
                "ticket_id": state.ticket_id,
                "user_id": state.user_id,
                "user_name": state.user_name,
                "suggested_tickets": state.suggested_tickets,
                "sources": result.get("sources", []),
            }
        )

        print_assistant_header()
        print(answer)
        print_ticket_suggestions(state.suggested_tickets)
        print_sources_block(result.get("sources", []))
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Красивый CLI для Day33 Support Assistant",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Адрес Day33 backend")
    parser.add_argument("--ticket", default="", help="Начальный ticket_id")
    parser.add_argument("--user", default="", help="Начальный user_id")
    parser.add_argument("--name", default="", help="Начальное имя или username")
    parser.add_argument("--prompt", default="", help="Одноразовый запрос без интерактивного режима")
    parser.add_argument("--save", default="", help="Сохранить историю в JSON-файл")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = SupportAPIClient(args.api_url)
    state = UIState(
        api_url=args.api_url,
        ticket_id=args.ticket or None,
        user_id=args.user or None,
        user_name=args.name or None,
    )

    try:
        client.health()
    except SupportCLIError as exc:
        print_error(str(exc))
        return 1

    if args.prompt:
        print_user_prompt(args.prompt)
        try:
            result = client.ask(
                question=args.prompt,
                ticket_id=state.ticket_id,
                user_id=state.user_id,
                user_name=state.user_name,
            )
        except SupportCLIError as exc:
            print_error(str(exc))
            return 1
        if result.get("needs_user_identity"):
            print_assistant_header()
            print(str(result.get("answer", "")).strip())
            return 1
        answer = str(result.get("answer", "")).strip()
        state.suggested_tickets = list(result.get("suggested_tickets", []))
        state.conversation.append(
            {
                "question": args.prompt,
                "answer": answer,
                "ticket_id": state.ticket_id,
                "user_id": state.user_id,
                "user_name": state.user_name,
                "suggested_tickets": state.suggested_tickets,
                "sources": result.get("sources", []),
            }
        )
        print_assistant_header()
        print(answer)
        print_ticket_suggestions(state.suggested_tickets)
        print_sources_block(result.get("sources", []))
        if args.save:
            path = save_chat(state, args.save)
            print_info(f"История сохранена: {path}")
        return 0

    code = interactive_loop(state, client)
    if args.save:
        path = save_chat(state, args.save)
        print_info(f"История сохранена: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
