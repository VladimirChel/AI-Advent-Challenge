#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
import textwrap
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

import requests

DEFAULT_HOST = os.environ.get("OLLAMA_HOST", "http://83.146.86.213:11434").rstrip("/")
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "")
DEFAULT_TIMEOUT = 300
HISTORY_DIR = Path.home() / ".ollama_cli"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)


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
    YELLOW = "\033[33m"
    BLUE = "\033[34m"
    MAGENTA = "\033[35m"
    CYAN = "\033[36m"
    GRAY = "\033[90m"


@dataclass
class Message:
    role: str
    content: str


@dataclass
class ChatState:
    model: str
    host: str = DEFAULT_HOST
    system_prompt: str = ""
    messages: list[dict[str, str]] = field(default_factory=list)

    def build_messages(self) -> list[dict[str, str]]:
        msgs: list[dict[str, str]] = []
        if self.system_prompt.strip():
            msgs.append({"role": "system", "content": self.system_prompt.strip()})
        msgs.extend(self.messages)
        return msgs


class OllamaCLIError(Exception):
    pass


class OllamaClient:
    def __init__(self, host: str, timeout: int = DEFAULT_TIMEOUT) -> None:
        self.host = host.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    def _url(self, path: str) -> str:
        return f"{self.host}{path}"

    def check(self) -> None:
        try:
            response = self.session.get(self._url("/api/tags"), timeout=10)
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaCLIError(
                f"Не удалось подключиться к Ollama по адресу {self.host}. "
                f"Проверь, что сервер запущен: ollama serve"
            ) from exc

    def list_models(self) -> list[str]:
        try:
            response = self.session.get(self._url("/api/tags"), timeout=20)
            response.raise_for_status()
            data = response.json()
            return [m["name"] for m in data.get("models", [])]
        except requests.RequestException as exc:
            raise OllamaCLIError(f"Не удалось получить список моделей: {exc}") from exc

    def chat_stream(self, model: str, messages: list[dict[str, str]]) -> str:
        payload = {"model": model, "messages": messages, "stream": True}
        try:
            with self.session.post(
                self._url("/api/chat"), json=payload, stream=True, timeout=self.timeout
            ) as response:
                response.raise_for_status()
                collected: list[str] = []
                for line in response.iter_lines(decode_unicode=True):
                    if not line:
                        continue
                    chunk = json.loads(line)
                    if "error" in chunk:
                        raise OllamaCLIError(str(chunk["error"]))
                    message = chunk.get("message", {})
                    part = message.get("content", "")
                    if part:
                        print(part, end="", flush=True)
                        collected.append(part)
                print()
                return "".join(collected).strip()
        except requests.HTTPError as exc:
            detail = ""
            try:
                detail = exc.response.text
            except Exception:
                pass
            raise OllamaCLIError(f"Ошибка HTTP: {exc}. {detail}".strip()) from exc
        except requests.RequestException as exc:
            raise OllamaCLIError(f"Ошибка запроса к Ollama: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise OllamaCLIError(f"Не удалось разобрать потоковый ответ Ollama: {exc}") from exc


BANNER = f"""{C.CYAN}{C.BOLD}
╔══════════════════════════════════════════════════════╗
║                    OLLAMA CLI                       ║
║          локальный терминал для моделей             ║
╚══════════════════════════════════════════════════════╝{C.RESET}
"""

HELP = f"""{C.BOLD}Команды:{C.RESET}
  /help                 показать эту справку
  /models               список доступных моделей
  /model <name>         переключить модель
  /system <text>        задать system prompt
  /clear                очистить историю диалога
  /save [file]          сохранить чат в JSON
  /host <url>           сменить адрес Ollama
  /exit                 выход
"""


def now_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def print_box(title: str, body: str, color: str = C.BLUE) -> None:
    width = 58
    print(f"{color}{C.BOLD}┌{'─' * width}┐{C.RESET}")
    print(f"{color}{C.BOLD}│ {title:<56} │{C.RESET}")
    print(f"{color}{C.BOLD}└{'─' * width}┘{C.RESET}")
    if body:
        print(body)


def print_info(text: str) -> None:
    print(f"{C.GRAY}› {text}{C.RESET}")


def print_error(text: str) -> None:
    print(f"{C.RED}{C.BOLD}Ошибка:{C.RESET} {text}")


def print_user_prompt(text: str) -> None:
    print(f"{C.GREEN}{C.BOLD}you{C.RESET} {C.DIM}›{C.RESET} {text}")


def print_assistant_header(model: str) -> None:
    print(f"{C.MAGENTA}{C.BOLD}{model}{C.RESET} {C.DIM}›{C.RESET} ", end="")


def save_chat(state: ChatState, file_path: str | None = None) -> Path:
    path = Path(file_path) if file_path else HISTORY_DIR / f"chat_{now_stamp()}.json"
    data = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "host": state.host,
        "model": state.model,
        "system_prompt": state.system_prompt,
        "messages": state.messages,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def resolve_model(client: OllamaClient, preferred: str) -> str:
    models = client.list_models()
    if not models:
        raise OllamaCLIError("У Ollama нет загруженных моделей. Сначала выполни, например: ollama pull llama3.2")
    if preferred:
        if preferred in models:
            return preferred
        raise OllamaCLIError(
            f"Модель '{preferred}' не найдена. Доступные: {', '.join(models)}"
        )
    return models[0]


def handle_command(raw: str, state: ChatState, client: OllamaClient) -> bool:
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print(HELP)
    elif cmd == "/models":
        models = client.list_models()
        body = "\n".join(
            [f"{'★' if m == state.model else ' '} {m}" for m in models]
        ) or "Нет моделей"
        print_box("Доступные модели", body, C.CYAN)
    elif cmd == "/model":
        if not arg:
            print_error("Укажи модель: /model llama3.2")
        else:
            models = client.list_models()
            if arg not in models:
                print_error(f"Модель '{arg}' не найдена.")
            else:
                state.model = arg
                print_info(f"Текущая модель: {state.model}")
    elif cmd == "/system":
        state.system_prompt = arg
        print_info("System prompt обновлён." if arg else "System prompt очищен.")
    elif cmd == "/clear":
        state.messages.clear()
        print_info("История чата очищена.")
    elif cmd == "/save":
        path = save_chat(state, arg or None)
        print_info(f"Чат сохранён: {path}")
    elif cmd == "/host":
        if not arg:
            print_error("Укажи URL, например: /host http://localhost:11434")
        else:
            state.host = arg.rstrip("/")
            client.host = state.host
            client.check()
            print_info(f"Новый адрес Ollama: {state.host}")
    elif cmd in {"/exit", "/quit"}:
        return False
    else:
        print_error("Неизвестная команда. Введи /help")
    return True


def interactive_loop(state: ChatState, client: OllamaClient) -> int:
    print(BANNER)
    print_info(f"Сервер: {state.host}")
    print_info(f"Модель: {state.model}")
    print_info("Введи /help для списка команд. Ctrl+C или /exit для выхода.")
    if state.system_prompt:
        print_info("System prompt уже задан.")
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
                if not handle_command(raw, state, client):
                    print("До встречи.")
                    return 0
            except OllamaCLIError as exc:
                print_error(str(exc))
            print()
            continue

        state.messages.append({"role": "user", "content": raw})
        print_assistant_header(state.model)
        try:
            answer = client.chat_stream(state.model, state.build_messages())
            state.messages.append({"role": "assistant", "content": answer})
        except OllamaCLIError as exc:
            print_error(str(exc))
            state.messages.pop()
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Красивый CLI для локального Ollama",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("-m", "--model", default=DEFAULT_MODEL, help="Имя модели")
    parser.add_argument("--host", default=DEFAULT_HOST, help="Адрес Ollama")
    parser.add_argument("-s", "--system", default="", help="System prompt")
    parser.add_argument("-p", "--prompt", default="", help="Одноразовый запрос без интерактивного режима")
    parser.add_argument("--save", default="", help="Сохранить чат в указанный JSON-файл")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = OllamaClient(args.host)

    try:
        client.check()
        model = resolve_model(client, args.model)
    except OllamaCLIError as exc:
        print_error(str(exc))
        return 1

    state = ChatState(model=model, host=args.host, system_prompt=args.system)

    if args.prompt:
        state.messages.append({"role": "user", "content": args.prompt})
        print_user_prompt(args.prompt)
        print_assistant_header(state.model)
        try:
            answer = client.chat_stream(state.model, state.build_messages())
        except OllamaCLIError as exc:
            print_error(str(exc))
            return 1
        state.messages.append({"role": "assistant", "content": answer})
        if args.save:
            path = save_chat(state, args.save)
            print_info(f"Чат сохранён: {path}")
        return 0

    code = interactive_loop(state, client)
    if args.save:
        path = save_chat(state, args.save)
        print_info(f"Чат сохранён: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
