#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request


DEFAULT_API_URL = os.environ.get("PROJECT_HELP_API_URL", "http://127.0.0.1:8000").rstrip("/")
DEFAULT_MODEL = os.environ.get("PROJECT_HELP_MODEL", "gpt-4o-mini")
DEFAULT_PROJECT_ID = os.environ.get("PROJECT_HELP_PROJECT_ID", "aspia")
DEFAULT_HISTORY_DIR = Path.home() / ".project_help_cli"


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
class ProjectHelpState:
    api_url: str
    timeout: float = 60.0
    token: str = ""
    provider_id: str = ""
    model: str = DEFAULT_MODEL
    conversation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    branch_id: str = "main"
    task_id: str = ""
    project_id: str = DEFAULT_PROJECT_ID
    project_root: str = ""
    index_dir: str = ""
    include_history: bool = True
    require_json: bool = False
    show_task_transition: bool = True
    show_diagnostics: bool = True
    allow_citations: bool = True
    show_links: bool = True
    auto_help_mode: bool = True
    history: list[dict[str, str]] = field(default_factory=list)
    last_response: Any = None


class ProjectHelpCLIError(RuntimeError):
    pass


class ProjectHelpAPIClient:
    def __init__(self, state: ProjectHelpState) -> None:
        self.state = state

    def health(self) -> dict[str, Any]:
        request = urllib.request.Request(f"{self.state.api_url}/health", headers=self._headers(), method="GET")
        return self._send(request)

    def generate(self, user_message: str) -> dict[str, Any] | str:
        payload = build_payload(self.state, user_message)
        request = urllib.request.Request(
            f"{self.state.api_url}/generate",
            data=json.dumps(payload).encode("utf-8"),
            headers=self._headers(content_type=True),
            method="POST",
        )
        response = self._send(request)
        self.state.conversation_id = str(payload["conversation_id"])
        return response

    def _headers(self, *, content_type: bool = False) -> dict[str, str]:
        headers: dict[str, str] = {}
        if content_type:
            headers["Content-Type"] = "application/json"
        if self.state.token.strip():
            headers["Authorization"] = f"Bearer {self.state.token.strip()}"
        return headers

    def _send(self, request: urllib.request.Request) -> dict[str, Any] | str:
        try:
            with urllib.request.urlopen(request, timeout=self.state.timeout) as response:
                raw_body = response.read().decode("utf-8", errors="replace")
                content_type = response.headers.get("Content-Type", "")
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise ProjectHelpCLIError(f"Сервис вернул HTTP {exc.code}: {details}") from exc
        except urllib.error.URLError as exc:
            raise ProjectHelpCLIError(
                f"Не удалось подключиться к Project Help сервису по адресу {self.state.api_url}."
            ) from exc

        if "application/json" in content_type.lower():
            try:
                parsed = json.loads(raw_body)
            except json.JSONDecodeError:
                return raw_body
            return parsed
        return raw_body


BANNER = f"""{C.CYAN}{C.BOLD}
╔══════════════════════════════════════════════════════╗
║               PROJECT HELP CLIENT DAY31             ║
║         консольный клиент для LLM Assistant         ║
╚══════════════════════════════════════════════════════╝{C.RESET}
"""

HELP = f"""{C.BOLD}Команды:{C.RESET}
  /help                  показать справку
  /status                показать текущий контекст
  /health                проверить backend
  /backend <url>         сменить URL backend
  /model <name>          сменить модель
  /provider <id>         сменить provider_id
  /project <id>          сменить project_id
  /root <path>           установить project_root
  /index <path>          установить index_dir
  /branch <id>           сменить branch_id
  /task <id>             сменить task_id
  /conversation <id>     установить conversation_id вручную
  /new                   начать новый диалог
  /history on|off        включить/выключить history
  /json on|off           включить/выключить require_json
  /transitions on|off    включить/выключить show_task_transition_in_chat
  /diagnostics on|off    включить/выключить диагностический вывод
  /citations on|off      разрешить/запретить цитаты в ответе
  /links on|off          показывать/скрывать ссылки и блок источников
  /autohelp on|off       автоматически отправлять обычные вопросы как /help
  /payload [text]        показать JSON payload
  /raw                   показать сырой ответ последнего запроса
  /save [file]           сохранить историю в JSON
  /clear                 очистить историю сессии
  /exit                  выход
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
    raise ProjectHelpCLIError("Не удалось создать каталог для сохранения истории.")


def print_info(text: str) -> None:
    print(f"{C.GRAY}› {text}{C.RESET}")


def print_error(text: str) -> None:
    print(f"{C.RED}{C.BOLD}Ошибка:{C.RESET} {text}")


def print_user_prompt(text: str) -> None:
    print(f"{C.GREEN}{C.BOLD}you{C.RESET} {C.DIM}›{C.RESET} {text}")


def print_assistant_header() -> None:
    print(f"{C.MAGENTA}{C.BOLD}assistant{C.RESET} {C.DIM}›{C.RESET} ", end="")


def print_sources_block(sources: list[dict[str, Any]]) -> None:
    if not sources:
        return
    print(f"\n{C.BLUE}{C.BOLD}Источники:{C.RESET}")
    for item in sources[:6]:
        source = item.get("source", "")
        section = item.get("section", "")
        chunk_id = item.get("chunk_id", "")
        score = item.get("score")
        score_text = f" score={score:.3f}" if isinstance(score, (int, float)) else ""
        chunk_text = f" | {chunk_id}" if chunk_id else ""
        print(f"{C.BLUE}  - {source} | {section}{chunk_text}{score_text}{C.RESET}")


def print_response_meta(body: dict[str, Any]) -> None:
    usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
    meta_lines = [
        f"request_id: {body.get('request_id') or '-'}",
        f"active_mode: {body.get('active_mode') or '-'}",
        f"project_id: {body.get('project_id') or '-'}",
        f"project_help_route: {body.get('project_help_route') or '-'}",
        f"provider_id: {body.get('provider_id') or '-'}",
        f"model: {body.get('model') or '-'}",
        f"latency_ms: {body.get('latency_ms') or '-'}",
        f"rag_used: {body.get('rag_used')}",
        f"rag_chunks_used: {body.get('rag_chunks_used')}",
        f"mcp_used: {body.get('mcp_used')}",
        f"mcp_tool_calls: {body.get('mcp_tool_calls')}",
        f"tokens_total: {usage.get('total_tokens') or '-'}",
    ]
    print(f"\n{C.CYAN}{C.BOLD}Метаданные:{C.RESET}")
    for line in meta_lines:
        print(f"{C.CYAN}  {line}{C.RESET}")


def print_status(state: ProjectHelpState) -> None:
    print_info(f"Backend: {state.api_url}")
    print_info(f"timeout: {state.timeout}")
    print_info(f"provider_id: {state.provider_id or 'not set'}")
    print_info(f"model: {state.model}")
    print_info(f"conversation_id: {state.conversation_id}")
    print_info(f"branch_id: {state.branch_id}")
    print_info(f"task_id: {state.task_id or 'not set'}")
    print_info(f"project_id: {state.project_id or 'not set'}")
    print_info(f"project_root: {state.project_root or 'not set'}")
    print_info(f"index_dir: {state.index_dir or 'not set'}")
    print_info(f"include_history: {state.include_history}")
    print_info(f"require_json: {state.require_json}")
    print_info(f"show_task_transition: {state.show_task_transition}")
    print_info(f"show_diagnostics: {state.show_diagnostics}")
    print_info(f"allow_citations: {state.allow_citations}")
    print_info(f"show_links: {state.show_links}")
    print_info(f"auto_help_mode: {state.auto_help_mode}")
    print_info(f"messages in session: {len(state.history)}")


def normalize_toggle(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"on", "true", "1", "yes"}:
        return True
    if normalized in {"off", "false", "0", "no"}:
        return False
    raise ProjectHelpCLIError("Ожидалось on|off.")


def extract_assistant_text(body: Any) -> str:
    if isinstance(body, dict):
        for key in ("content", "text", "message", "answer", "response"):
            value = body.get(key)
            if value:
                return str(value).strip()
        return ""
    if body is None:
        return ""
    return str(body).strip()


def apply_response_preferences(state: ProjectHelpState, text: str) -> str:
    result = text
    if not state.allow_citations:
        result = re.sub(r"(?is)\n*цитаты:\n.*$", "", result)
        result = "\n".join(line for line in result.splitlines() if not line.lstrip().startswith(">"))
    if not state.show_links:
        result = re.sub(r"(?is)\n*источники:\n.*?(?=\n[А-ЯA-Z][^:\n]{0,80}:\n|\Z)", "", result)
        result = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", r"\1", result)
        result = re.sub(r"https?://\S+", "", result)
        result = re.sub(r"\bwww\.\S+", "", result)
        result = re.sub(r"[ \t]+$", "", result, flags=re.MULTILINE)
    result = re.sub(r"\n{3,}", "\n\n", result).strip()
    return result


def build_user_message(state: ProjectHelpState, prompt: str) -> str:
    normalized_prompt = prompt.strip()
    if state.auto_help_mode and normalized_prompt and not normalized_prompt.startswith("/help"):
        normalized_prompt = f"/help {normalized_prompt}"

    instructions: list[str] = []
    if not state.allow_citations:
        instructions.append("Не используй цитаты из документации или кода.")
    if not state.show_links:
        instructions.append("Не добавляй ссылки, URL и markdown-ссылки в ответ.")
    if not instructions:
        return normalized_prompt
    suffix = "\n\nТребования к формату ответа:\n- " + "\n- ".join(instructions)
    return normalized_prompt + suffix


def resolve_effective_index_dir(state: ProjectHelpState) -> str:
    raw_value = state.index_dir.strip()
    if not raw_value:
        return ""
    base_path = Path(raw_value)
    manifest_in_place = base_path / "manifest.json"
    if manifest_in_place.exists():
        return str(base_path)
    if state.project_id.strip():
        project_dir = base_path / state.project_id.strip()
        if (project_dir / "manifest.json").exists():
            return str(project_dir)
    return raw_value


def resolve_project_manifest_path(state: ProjectHelpState) -> Path | None:
    if not state.index_dir.strip() or not state.project_id.strip():
        return None
    direct_manifest = Path(resolve_effective_index_dir(state)) / "manifest.json"
    if direct_manifest.exists():
        return direct_manifest
    return Path(state.index_dir) / state.project_id / "manifest.json"


def load_project_manifest(state: ProjectHelpState) -> dict[str, Any] | None:
    manifest_path = resolve_project_manifest_path(state)
    if manifest_path is None or not manifest_path.exists():
        return None
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def print_manifest_summary(manifest: dict[str, Any]) -> None:
    lines = [
        f"manifest project_id: {manifest.get('project_id') or '-'}",
        f"manifest project_root: {manifest.get('project_root') or '-'}",
        f"embed_model: {manifest.get('embed_model') or '-'}",
        f"embedding_dimension: {manifest.get('embedding_dimension') or '-'}",
        f"index_file: {manifest.get('index_file') or '-'}",
        f"chunks_file: {manifest.get('chunks_file') or '-'}",
    ]
    for line in lines:
        print_info(line)
    if manifest.get("index_file") is None:
        print_info("warning: FAISS index file is missing, semantic RAG search may not work.")
    if manifest.get("embedding_dimension") is None:
        print_info("warning: embedding_dimension is missing in manifest.")


def resolve_effective_project_root(state: ProjectHelpState) -> str:
    explicit_root = state.project_root.strip()
    if explicit_root:
        return explicit_root
    manifest = load_project_manifest(state)
    if not manifest:
        return ""
    value = str(manifest.get("project_root") or "").strip()
    return value


def build_payload(state: ProjectHelpState, user_message: str) -> dict[str, Any]:
    messages: list[dict[str, str]] = []
    if state.include_history:
        messages.extend(state.history)
    messages.append({"role": "user", "content": build_user_message(state, user_message)})

    payload: dict[str, Any] = {
        "conversation_id": state.conversation_id or str(uuid.uuid4()),
        "branch_id": state.branch_id or "main",
        "task_id": state.task_id or None,
        "model": state.model.strip(),
        "messages": messages,
        "temperature": 0.2,
        "max_tokens": 800,
        "top_p": 1.0,
        "show_task_transition_in_chat": state.show_task_transition,
        "include_sources_in_content": state.show_links,
        "include_citations_in_content": state.allow_citations,
        "project": {
            "id": state.project_id.strip() or None,
            "root": resolve_effective_project_root(state) or None,
            "index_dir": resolve_effective_index_dir(state) or None,
        },
    }
    if state.provider_id.strip():
        payload["provider_id"] = state.provider_id.strip()
    if state.require_json:
        payload["validation"] = {"require_json": True}
    return payload


def save_chat(state: ProjectHelpState, file_path: str | None = None) -> Path:
    history_dir = resolve_history_dir()
    path = Path(file_path) if file_path else history_dir / f"project_help_chat_{now_stamp()}.json"
    data = {
        "saved_at": datetime.now().isoformat(timespec="seconds"),
        "api_url": state.api_url,
        "timeout": state.timeout,
        "provider_id": state.provider_id,
        "model": state.model,
        "conversation_id": state.conversation_id,
        "branch_id": state.branch_id,
        "task_id": state.task_id,
        "project_id": state.project_id,
        "project_root": state.project_root,
        "index_dir": state.index_dir,
        "include_history": state.include_history,
        "require_json": state.require_json,
        "show_task_transition": state.show_task_transition,
        "show_diagnostics": state.show_diagnostics,
        "allow_citations": state.allow_citations,
        "show_links": state.show_links,
        "auto_help_mode": state.auto_help_mode,
        "history": state.history,
        "last_response": state.last_response,
    }
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def handle_command(raw: str, state: ProjectHelpState, client: ProjectHelpAPIClient) -> bool:
    parts = raw.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if cmd == "/help":
        print(HELP)
    elif cmd == "/status":
        print_status(state)
    elif cmd == "/health":
        body = client.health()
        state.last_response = body
        print_info(json.dumps(body, ensure_ascii=False, indent=2) if isinstance(body, dict) else str(body))
    elif cmd == "/backend":
        if not arg:
            print_error("Укажи URL, например: /backend http://127.0.0.1:8000")
        else:
            state.api_url = arg.rstrip("/")
            client.health()
            print_info(f"Новый backend: {state.api_url}")
    elif cmd == "/model":
        state.model = arg or DEFAULT_MODEL
        print_info(f"model: {state.model}")
    elif cmd == "/provider":
        state.provider_id = arg
        print_info(f"provider_id: {state.provider_id or 'cleared'}")
    elif cmd == "/project":
        state.project_id = arg
        print_info(f"project_id: {state.project_id or 'cleared'}")
    elif cmd == "/root":
        state.project_root = arg
        print_info(f"project_root: {state.project_root or 'cleared'}")
    elif cmd == "/index":
        state.index_dir = arg
        print_info(f"index_dir: {state.index_dir or 'cleared'}")
        effective_index_dir = resolve_effective_index_dir(state)
        if effective_index_dir and effective_index_dir != state.index_dir:
            print_info(f"resolved project index_dir: {effective_index_dir}")
        manifest = load_project_manifest(state)
        if manifest is None and state.index_dir and state.project_id:
            print_info(f"manifest not found: {resolve_project_manifest_path(state)}")
        elif manifest is not None:
            print_manifest_summary(manifest)
    elif cmd == "/branch":
        state.branch_id = arg or "main"
        print_info(f"branch_id: {state.branch_id}")
    elif cmd == "/task":
        state.task_id = arg
        print_info(f"task_id: {state.task_id or 'cleared'}")
    elif cmd == "/conversation":
        state.conversation_id = arg or str(uuid.uuid4())
        print_info(f"conversation_id: {state.conversation_id}")
    elif cmd == "/new":
        state.conversation_id = str(uuid.uuid4())
        state.history.clear()
        state.last_response = None
        print_info(f"Новый диалог: {state.conversation_id}")
    elif cmd == "/history":
        state.include_history = normalize_toggle(arg)
        print_info(f"include_history: {state.include_history}")
    elif cmd == "/json":
        state.require_json = normalize_toggle(arg)
        print_info(f"require_json: {state.require_json}")
    elif cmd == "/transitions":
        state.show_task_transition = normalize_toggle(arg)
        print_info(f"show_task_transition: {state.show_task_transition}")
    elif cmd == "/diagnostics":
        state.show_diagnostics = normalize_toggle(arg)
        print_info(f"show_diagnostics: {state.show_diagnostics}")
    elif cmd == "/citations":
        state.allow_citations = normalize_toggle(arg)
        print_info(f"allow_citations: {state.allow_citations}")
    elif cmd == "/links":
        state.show_links = normalize_toggle(arg)
        print_info(f"show_links: {state.show_links}")
    elif cmd == "/autohelp":
        state.auto_help_mode = normalize_toggle(arg)
        print_info(f"auto_help_mode: {state.auto_help_mode}")
    elif cmd == "/payload":
        text = arg or "/help Какая структура проекта?"
        print(json.dumps(build_payload(state, text), ensure_ascii=False, indent=2))
    elif cmd == "/raw":
        if state.last_response is None:
            print_info("Сырой ответ пока пуст.")
        else:
            print(
                json.dumps(state.last_response, ensure_ascii=False, indent=2)
                if isinstance(state.last_response, (dict, list))
                else str(state.last_response)
            )
    elif cmd == "/save":
        path = save_chat(state, arg or None)
        print_info(f"История сохранена: {path}")
    elif cmd == "/clear":
        state.history.clear()
        state.last_response = None
        print_info("История сессии очищена.")
    elif cmd in {"/exit", "/quit"}:
        return False
    else:
        print_error("Неизвестная команда. Введи /help")
    return True


def run_prompt(state: ProjectHelpState, client: ProjectHelpAPIClient, prompt: str) -> int:
    manifest = load_project_manifest(state)
    if state.show_diagnostics and state.index_dir and state.project_id:
        effective_index_dir = resolve_effective_index_dir(state)
        if effective_index_dir and effective_index_dir != state.index_dir:
            print_info(f"resolved project index_dir: {effective_index_dir}")
        if manifest is None:
            print_info(f"manifest not found: {resolve_project_manifest_path(state)}")
        else:
            print_manifest_summary(manifest)

    print_user_prompt(prompt)
    result = client.generate(prompt)
    state.last_response = result

    answer = apply_response_preferences(state, extract_assistant_text(result))
    print_assistant_header()
    print(answer or "[empty response]")

    if state.include_history and answer:
        state.history.append({"role": "user", "content": build_user_message(state, prompt)})
        state.history.append({"role": "assistant", "content": answer})

    if state.show_diagnostics and isinstance(result, dict):
        print_response_meta(result)
    if state.show_links and isinstance(result, dict):
        print_sources_block(result.get("sources", []) if isinstance(result.get("sources"), list) else [])
    return 0


def interactive_loop(state: ProjectHelpState, client: ProjectHelpAPIClient) -> int:
    print(BANNER)
    print_info(f"Backend: {state.api_url}")
    print_info("Введи /help для списка команд.")
    print_info("Для project-help удобно спрашивать так: /help Какая структура проекта?")
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
                keep_running = handle_command(raw, state, client)
                if not keep_running:
                    print("До встречи.")
                    return 0
            except ProjectHelpCLIError as exc:
                print_error(str(exc))
            print()
            continue

        try:
            run_prompt(state, client, raw)
        except ProjectHelpCLIError as exc:
            print_error(str(exc))
        print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="CLI-клиент для Day31 Project Help",
        formatter_class=argparse.RawTextHelpFormatter,
    )
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="Адрес backend LLM Assistant")
    parser.add_argument("--timeout", type=float, default=120.0, help="Таймаут запроса в секундах")
    parser.add_argument("--token", default="", help="Bearer token")
    parser.add_argument("--provider-id", default="", help="provider_id для backend")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Модель для generate")
    parser.add_argument("--conversation-id", default="", help="ID диалога")
    parser.add_argument("--branch-id", default="main", help="branch_id")
    parser.add_argument("--task-id", default="", help="task_id")
    parser.add_argument("--project-id", default=DEFAULT_PROJECT_ID, help="project.id")
    parser.add_argument("--project-root", default="", help="project.root")
    parser.add_argument("--index-dir", default="", help="project.index_dir")
    parser.add_argument("--no-history", action="store_true", help="Не отправлять историю предыдущих сообщений")
    parser.add_argument("--require-json", action="store_true", help="Включить validation.require_json")
    parser.add_argument(
        "--hide-task-transitions",
        action="store_true",
        help="Отключить show_task_transition_in_chat",
    )
    parser.add_argument("--hide-diagnostics", action="store_true", help="Скрыть диагностический вывод")
    parser.add_argument("--no-citations", action="store_true", help="Попросить backend не использовать цитаты")
    parser.add_argument("--hide-links", action="store_true", help="Скрыть ссылки и блок источников")
    parser.add_argument("--prompt", default="", help="Одноразовый запрос без интерактивного режима")
    parser.add_argument("--save", default="", help="Сохранить историю в JSON-файл")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    state = ProjectHelpState(
        api_url=args.api_url.rstrip("/"),
        timeout=args.timeout,
        token=args.token,
        provider_id=args.provider_id,
        model=args.model,
        conversation_id=args.conversation_id or str(uuid.uuid4()),
        branch_id=args.branch_id,
        task_id=args.task_id,
        project_id=args.project_id,
        project_root=args.project_root,
        index_dir=args.index_dir,
        include_history=not args.no_history,
        require_json=args.require_json,
        show_task_transition=not args.hide_task_transitions,
        show_diagnostics=not args.hide_diagnostics,
        allow_citations=not args.no_citations,
        show_links=not args.hide_links,
    )
    client = ProjectHelpAPIClient(state)

    try:
        client.health()
    except ProjectHelpCLIError as exc:
        print_error(str(exc))
        return 1

    if args.prompt:
        try:
            code = run_prompt(state, client, args.prompt)
        except ProjectHelpCLIError as exc:
            print_error(str(exc))
            return 1
        if args.save:
            path = save_chat(state, args.save)
            print_info(f"История сохранена: {path}")
        return code

    code = interactive_loop(state, client)
    if args.save:
        path = save_chat(state, args.save)
        print_info(f"История сохранена: {path}")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
