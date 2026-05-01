from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from llm.schemas import ChatMessage, MCPServerConfig, MCPSettings, ProjectSettings, RAGSettings


HELP_MODE = "project_help"
DEFAULT_MODE = "default"
PROJECT_REPO_TOOLS_SERVER = Path(__file__).resolve().parents[1] / "MCP" / "project_repo_tools" / "server.py"
MCP_ROUTE = "mcp"
RAG_ROUTE = "rag"
HYBRID_ROUTE = "hybrid"


@dataclass(slots=True)
class HelpModeState:
    active_mode: str
    command_name: str | None
    rewritten_live_messages: list[ChatMessage]
    immediate_response: str | None = None
    project_id: str | None = None
    route: str = RAG_ROUTE


def resolve_help_mode(
    *,
    short_term_messages: list[ChatMessage],
    live_messages: list[ChatMessage],
    project: ProjectSettings | None,
) -> HelpModeState:
    history_mode = _detect_mode_from_messages([*short_term_messages, *live_messages[:-1]])
    latest_user_index = max((index for index, message in enumerate(live_messages) if message.role == "user"), default=-1)
    if latest_user_index < 0:
        return HelpModeState(active_mode=history_mode, command_name=None, rewritten_live_messages=list(live_messages))

    latest_user = live_messages[latest_user_index].content.strip()
    lower = latest_user.lower()
    project_id = _resolve_project_id(project)

    if lower == "/mode":
        return HelpModeState(
            active_mode=history_mode,
            command_name="/mode",
            rewritten_live_messages=list(live_messages),
            immediate_response=_build_mode_message(history_mode, project_id),
            project_id=project_id,
            route=RAG_ROUTE,
        )

    if lower in {"/exit", "/default"}:
        return HelpModeState(
            active_mode=DEFAULT_MODE,
            command_name="/exit",
            rewritten_live_messages=list(live_messages),
            immediate_response="Project help mode disabled. Back to the default assistant mode.",
            project_id=project_id,
            route=RAG_ROUTE,
        )

    if lower == "/help":
        return HelpModeState(
            active_mode=HELP_MODE,
            command_name="/help",
            rewritten_live_messages=list(live_messages),
            immediate_response=(
                "Project help mode enabled. Ask about structure, docs, API, schemas, or git branches. "
                "Use /exit to leave this mode."
            ),
            project_id=project_id,
            route=RAG_ROUTE,
        )

    if lower.startswith("/help "):
        rewritten = list(live_messages)
        rewritten[latest_user_index] = ChatMessage(role="user", content=latest_user[6:].strip())
        return HelpModeState(
            active_mode=HELP_MODE,
            command_name="/help",
            rewritten_live_messages=rewritten,
            project_id=project_id,
            route=classify_project_help_route(rewritten[latest_user_index].content),
        )

    latest_query = latest_user
    return HelpModeState(
        active_mode=history_mode,
        command_name=None,
        rewritten_live_messages=list(live_messages),
        project_id=project_id,
        route=classify_project_help_route(latest_query) if history_mode == HELP_MODE else RAG_ROUTE,
    )


def classify_project_help_route(question: str) -> str:
    text = " ".join((question or "").lower().split())
    if not text:
        return RAG_ROUTE

    mcp_strong_terms = {
        "сколько файлов",
        "сколько readme",
        "find all",
        "count files",
        "tree",
        "дерево",
        "tree_dir",
        "find_files",
        "search_text",
        "usage",
        "usages",
        "используется",
        "используются",
        "где используется",
        "все места",
        "найти все",
        "найди все",
        "список файлов",
        "все файлы",
        "какие файлы",
        "покажи дерево",
        "обойди проект",
        "инвариант",
        "инварианты",
        "правила для файлов",
        "проверь файлы",
        "проверить файлы",
        "check invariants",
    }
    mcp_terms = {
        "git",
        "branch",
        "branches",
        "ветк",
        "repo",
        "repository",
        "репозитор",
        "dir",
        "directory",
        "folder",
        "file",
        "файл",
        "папк",
        "каталог",
        "list dir",
        "read file",
        "прочитай файл",
        "покажи файл",
        "что лежит",
        "содержимое корня",
        "корень проекта",
    }
    rag_terms = {
        "readme",
        "docs",
        "documentation",
        "документац",
        "структур",
        "архитектур",
        "api",
        "openapi",
        "swagger",
        "schema",
        "схем",
        "описан",
        "как устроен",
        "как устроена",
        "модул",
        "компонент",
    }

    if any(term in text for term in mcp_strong_terms):
        return MCP_ROUTE

    has_mcp = any(term in text for term in mcp_terms)
    has_rag = any(term in text for term in rag_terms)

    count_or_search_intent = any(
        term in text
        for term in {
            "сколько",
            "count",
            "найти",
            "найди",
            "поиск",
            "search",
            "список",
            "list",
            "где",
            "where",
            "использ",
        }
    )
    filesystem_targets = any(
        term in text
        for term in {
            "file",
            "files",
            "readme",
            "md",
            "каталог",
            "папк",
            "директор",
            "folder",
            "directory",
            "repo",
            "repository",
            "компонент",
            "api",
        }
    )
    if count_or_search_intent and filesystem_targets:
        return MCP_ROUTE

    if has_mcp and has_rag:
        return HYBRID_ROUTE
    if has_mcp:
        return MCP_ROUTE
    return RAG_ROUTE


def _detect_mode_from_messages(messages: list[ChatMessage]) -> str:
    active_mode = DEFAULT_MODE
    for message in messages:
        if message.role != "user":
            continue
        text = message.content.strip().lower()
        if text == "/help" or text.startswith("/help "):
            active_mode = HELP_MODE
        elif text in {"/exit", "/default"}:
            active_mode = DEFAULT_MODE
    return active_mode


def _build_mode_message(active_mode: str, project_id: str | None) -> str:
    if active_mode == HELP_MODE:
        if project_id:
            return f"Current mode: {HELP_MODE}. Active project: {project_id}. Use /exit to leave this mode."
        return f"Current mode: {HELP_MODE}. Use /exit to leave this mode."
    return "Current mode: default."


def build_project_help_system_message(project: ProjectSettings | None) -> ChatMessage | None:
    if project is None:
        return None
    effective_root = _resolve_project_root(project)
    details: list[str] = [
        "You are in project help mode.",
        "Answer questions about the target project using the provided RAG context and MCP tool results.",
        "Do not invent files, APIs, modules, or architecture details that are not grounded in sources or tool output.",
        "When possible, mention concrete project paths in the answer.",
        "If the answer is not in the docs or tools, say that clearly.",
        "If the user asks for exact file counts, exact file lists, recursive tree output, concrete file locations, usages, or invariant checks, prefer MCP tools over RAG summaries.",
        "For questions like 'how many files', 'find all', 'where is this used', or 'show the tree', do not guess from documentation. Use MCP tools first and base the answer on their structured output.",
        "If an MCP tool returns a count or file list, use that exact result in the answer.",
        "For exact counts of files, prefer a dedicated counting tool over guessing or manually counting partial lists.",
        "For README-like filenames or similar name matching, prefer case-insensitive regex-based file matching instead of a narrow case-sensitive glob.",
        "For repository-wide README counts, a good MCP call pattern is count_files with glob='**/*', name_regex='readme', case_sensitive=false.",
        "Do not use a root-only glob like 'README*' when the user asks about the whole project or repository.",
    ]
    if effective_root:
        details.append(f"Always use this project_root when calling repo tools: {effective_root}")
    if project.id:
        details.append(f"Project id: {project.id}")
    return ChatMessage(role="system", content="\n".join(details))


def resolve_project_rag_settings(
    project: ProjectSettings | None,
    payload_rag: RAGSettings | None,
    *,
    help_mode_active: bool,
) -> RAGSettings | None:
    if project is None:
        return payload_rag

    manifest = _load_manifest(project.index_dir) if project.index_dir else {}
    index_file = project.index_file or manifest.get("index_file")
    metadata_file = project.metadata_file or manifest.get("chunks_file") or manifest.get("index_payload_file")
    embed_model = str(manifest.get("embed_model") or "").strip() or None
    ollama_url = str(manifest.get("ollama_url") or "").strip() or None
    if (not embed_model or not ollama_url) and project.index_dir:
        payload_meta = _load_index_payload_meta(project.index_dir, manifest)
        embed_model = embed_model or payload_meta.get("model")
        ollama_url = ollama_url or payload_meta.get("ollama_url")

    if payload_rag is not None:
        if payload_rag.enabled:
            explicit_fields = payload_rag.model_fields_set
            requested_index_file = payload_rag.index_file if "index_file" in explicit_fields else None
            requested_metadata_file = payload_rag.metadata_file if "metadata_file" in explicit_fields else None
            requested_embed_model = payload_rag.embed_model if "embed_model" in explicit_fields else None
            requested_ollama_url = payload_rag.ollama_url if "ollama_url" in explicit_fields else None
            return payload_rag.model_copy(
                update={
                    "index_file": requested_index_file or index_file or payload_rag.index_file,
                    "metadata_file": requested_metadata_file or metadata_file or payload_rag.metadata_file,
                    "embed_model": requested_embed_model or embed_model or payload_rag.embed_model,
                    "ollama_url": requested_ollama_url or ollama_url or payload_rag.ollama_url,
                }
            )
        return payload_rag

    if not help_mode_active or not (index_file and metadata_file):
        return None

    return RAGSettings(
        enabled=True,
        strategy=str(manifest.get("strategy") or "structure"),
        index_file=str(index_file),
        metadata_file=str(metadata_file),
        embed_model=embed_model or "bge-m3",
        ollama_url=ollama_url or "http://localhost:11434",
    )


def resolve_project_mcp_settings(
    project: ProjectSettings | None,
    payload_mcp: MCPSettings | None,
    *,
    help_mode_active: bool,
) -> MCPSettings | None:
    if payload_mcp is not None:
        return payload_mcp
    effective_root = _resolve_project_root(project)
    if not help_mode_active or project is None or not effective_root:
        return None
    return MCPSettings(
        enabled=True,
        servers=[
            MCPServerConfig(
                id="project_repo",
                server_script=str(PROJECT_REPO_TOOLS_SERVER),
            )
        ],
    )


def _resolve_project_id(project: ProjectSettings | None) -> str | None:
    if project is None:
        return None
    if project.id:
        return project.id
    if project.index_dir:
        return Path(project.index_dir).resolve().name
    if project.root:
        return Path(project.root).resolve().name
    return None


def _resolve_project_root(project: ProjectSettings | None) -> str | None:
    if project is None:
        return None
    if project.root:
        return project.root
    if not project.index_dir:
        return None
    manifest = _load_manifest(project.index_dir)
    value = str(manifest.get("project_root") or "").strip()
    return value or None


def _load_manifest(index_dir: str) -> dict[str, str]:
    manifest_path = Path(index_dir).resolve() / "manifest.json"
    if not manifest_path.exists():
        return {}
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _load_index_payload_meta(index_dir: str, manifest: dict[str, str]) -> dict[str, str]:
    index_payload_file = str(manifest.get("index_payload_file") or "").strip()
    candidate_paths: list[Path] = []
    if index_payload_file:
        candidate_paths.append(Path(index_payload_file).resolve())
    base_dir = Path(index_dir).resolve()
    candidate_paths.extend(
        [
            base_dir / "structure_index.json",
            base_dir / "fixed_index.json",
        ]
    )

    for candidate in candidate_paths:
        if not candidate.exists():
            continue
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        model = str(payload.get("model") or "").strip()
        return {
            "model": model or "",
            "ollama_url": "",
        }
    return {}
