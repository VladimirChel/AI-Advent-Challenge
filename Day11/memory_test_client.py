#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
import textwrap
import urllib.error
import urllib.request
import uuid
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_MODEL = "openai/gpt-4o-mini"


@dataclass
class ClientConfig:
    base_url: str
    model: str
    user_id: str | None
    temperature: float
    max_tokens: int
    timeout: int
    verbose: bool


class MemoryTestClient:
    def __init__(self, config: ClientConfig):
        self.config = config

    def post_generate(
        self,
        *,
        messages: list[dict[str, str]],
        conversation_id: str,
        branch_id: str = "main",
        task_id: str | None = None,
        validation: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "branch_id": branch_id,
            "task_id": task_id,
            "model": self.config.model,
            "messages": messages,
            "user_id": self.config.user_id,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }
        if validation:
            payload["validation"] = validation

        url = self.config.base_url.rstrip("/") + "/generate"
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(request, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"HTTP {exc.code} while calling {url}\n{error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc}") from exc

    def get_json(self, path: str) -> dict[str, Any]:
        url = self.config.base_url.rstrip("/") + path
        try:
            with urllib.request.urlopen(url, timeout=self.config.timeout) as response:
                body = response.read().decode("utf-8")
                return json.loads(body)
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(
                f"HTTP {exc.code} while calling {url}\n{error_body}"
            ) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Cannot reach {url}: {exc}") from exc


def pretty_print_response(response: dict[str, Any], *, show_full_json: bool = False) -> None:
    print("=" * 80)
    print("assistant:")
    print(textwrap.fill(response.get("content", ""), width=100))
    print("-" * 80)
    print("conversation_id:", response.get("conversation_id"))
    print("branch_id:", response.get("branch_id"))
    print("task_id:", response.get("task_id"))
    print("latency_ms:", response.get("latency_ms"))
    print("finish_reason:", response.get("finish_reason"))

    memory_flags = {
        "short_term_used": response.get("short_term_used"),
        "short_term_messages_used": response.get("short_term_messages_used"),
        "working_memory_used": response.get("working_memory_used"),
        "long_term_used": response.get("long_term_used"),
        "long_term_facts_count": response.get("long_term_facts_count"),
        "long_term_summary_used": response.get("long_term_summary_used"),
        "retrieval_used": response.get("retrieval_used"),
        "retrieval_messages_used": response.get("retrieval_messages_used"),
    }
    print("memory:", json.dumps(memory_flags, ensure_ascii=False, indent=2))

    usage = response.get("usage") or {}
    if usage:
        print("usage:", json.dumps(usage, ensure_ascii=False, indent=2))

    if show_full_json:
        print("full_response:")
        print(json.dumps(response, ensure_ascii=False, indent=2))
    print("=" * 80)


def run_single_message(client: MemoryTestClient, args: argparse.Namespace) -> int:
    response = client.post_generate(
        conversation_id=args.conversation_id,
        branch_id=args.branch_id,
        task_id=args.task_id,
        messages=[{"role": "user", "content": args.message}],
    )
    pretty_print_response(response, show_full_json=args.json)
    return 0


def run_short_term_scenario(client: MemoryTestClient, args: argparse.Namespace) -> int:
    conversation_id = args.conversation_id or f"mem-short-{uuid.uuid4()}"
    seed_messages = [
        "Меня зовут Алексей.",
        "Я работаю над CRM для стоматологий.",
        "Мой любимый язык — Python.",
        "Запомни: дедлайн демо в пятницу в 15:00.",
    ]

    print(f"scenario=short_term conversation_id={conversation_id}")
    for idx, text in enumerate(seed_messages, start=1):
        print(f"\n[seed {idx}] user: {text}")
        response = client.post_generate(
            conversation_id=conversation_id,
            branch_id=args.branch_id,
            messages=[{"role": "user", "content": text}],
        )
        pretty_print_response(response, show_full_json=args.json)

    question = args.question or "Как меня зовут и когда дедлайн демо?"
    print(f"\n[check] user: {question}")
    response = client.post_generate(
        conversation_id=conversation_id,
        branch_id=args.branch_id,
        messages=[{"role": "user", "content": question}],
    )
    pretty_print_response(response, show_full_json=args.json)
    return 0


def run_working_memory_scenario(client: MemoryTestClient, args: argparse.Namespace) -> int:
    conversation_id = args.conversation_id or f"mem-task-{uuid.uuid4()}"
    task_id = args.task_id or "task-memory-demo"
    prompts = [
        "Нужно подготовить API-клиент для теста памяти и сохранить план работ.",
        "Теперь предложи следующий шаг по этой задаче и краткий статус.",
    ]

    print(f"scenario=working_memory conversation_id={conversation_id} task_id={task_id}")
    for idx, text in enumerate(prompts, start=1):
        print(f"\n[step {idx}] user: {text}")
        response = client.post_generate(
            conversation_id=conversation_id,
            branch_id=args.branch_id,
            task_id=task_id,
            messages=[{"role": "user", "content": text}],
        )
        pretty_print_response(response, show_full_json=args.json)
    return 0


def run_custom_dialog(client: MemoryTestClient, args: argparse.Namespace) -> int:
    conversation_id = args.conversation_id or f"mem-custom-{uuid.uuid4()}"
    raw_messages = json.loads(args.messages_json)
    if not isinstance(raw_messages, list) or not raw_messages:
        raise SystemExit("messages-json must be a non-empty JSON array")

    normalized_messages: list[dict[str, str]] = []
    for item in raw_messages:
        if not isinstance(item, dict) or "role" not in item or "content" not in item:
            raise SystemExit("Each message must be an object with role and content")
        normalized_messages.append({"role": str(item["role"]), "content": str(item["content"])})

    response = client.post_generate(
        conversation_id=conversation_id,
        branch_id=args.branch_id,
        task_id=args.task_id,
        messages=normalized_messages,
    )
    pretty_print_response(response, show_full_json=args.json)
    return 0


def run_healthcheck(client: MemoryTestClient, _args: argparse.Namespace) -> int:
    print(json.dumps(client.get_json("/health"), ensure_ascii=False, indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI-клиент для ручного тестирования memory layers через /generate"
    )
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Base URL API, например http://127.0.0.1:8000")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Модель для generate")
    parser.add_argument("--user-id", default=None, help="user_id для запросов")
    parser.add_argument("--temperature", default=0.2, type=float)
    parser.add_argument("--max-tokens", default=500, type=int)
    parser.add_argument("--timeout", default=60, type=int)
    parser.add_argument("--json", action="store_true", help="Печатать полный JSON ответа")
    parser.add_argument("--verbose", action="store_true")

    subparsers = parser.add_subparsers(dest="command", required=True)

    health = subparsers.add_parser("health", help="Проверить /health")
    health.set_defaults(func=run_healthcheck)

    single = subparsers.add_parser("ask", help="Один запрос к /generate")
    single.add_argument("message", help="Текст пользовательского сообщения")
    single.add_argument("--conversation-id", default=f"mem-ask-{uuid.uuid4()}")
    single.add_argument("--branch-id", default="main")
    single.add_argument("--task-id", default=None)
    single.set_defaults(func=run_single_message)

    short_term = subparsers.add_parser("short-term", help="Сценарий проверки short-term memory")
    short_term.add_argument("--conversation-id", default=None)
    short_term.add_argument("--branch-id", default="main")
    short_term.add_argument("--question", default=None)
    short_term.set_defaults(func=run_short_term_scenario)

    working = subparsers.add_parser("working-memory", help="Сценарий проверки working memory/task memory")
    working.add_argument("--conversation-id", default=None)
    working.add_argument("--branch-id", default="main")
    working.add_argument("--task-id", default=None)
    working.set_defaults(func=run_working_memory_scenario)

    custom = subparsers.add_parser("custom", help="Отправить массив messages как JSON")
    custom.add_argument("messages_json", help='Например: "[{\"role\":\"user\",\"content\":\"Привет\"}]"')
    custom.add_argument("--conversation-id", default=None)
    custom.add_argument("--branch-id", default="main")
    custom.add_argument("--task-id", default=None)
    custom.set_defaults(func=run_custom_dialog)

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    config = ClientConfig(
        base_url=args.base_url,
        model=args.model,
        user_id=args.user_id,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        timeout=args.timeout,
        verbose=args.verbose,
    )
    client = MemoryTestClient(config)
    return int(args.func(client, args) or 0)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("Interrupted", file=sys.stderr)
        raise SystemExit(130)
