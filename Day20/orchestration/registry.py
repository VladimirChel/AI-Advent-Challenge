from __future__ import annotations

from copy import deepcopy
from contextlib import ExitStack
from dataclasses import dataclass
from typing import Any

from .types import ToolDefinition, ToolServerSession


def normalize_server_id(raw_id: str) -> str:
    normalized = "".join(ch if ch.isalnum() else "_" for ch in raw_id.strip().lower())
    normalized = normalized.strip("_")
    return normalized or "server"


@dataclass(slots=True)
class RegisteredServer:
    server_id: str
    session_factory: Any
    metadata: dict[str, Any]


class ServerRegistry:
    def __init__(self) -> None:
        self._servers: dict[str, RegisteredServer] = {}

    def register(self, server_id: str, session_factory: Any, **metadata: Any) -> None:
        normalized = normalize_server_id(server_id)
        if normalized in self._servers:
            raise ValueError(f"Server '{normalized}' is already registered")
        self._servers[normalized] = RegisteredServer(
            server_id=normalized,
            session_factory=session_factory,
            metadata=dict(metadata),
        )

    def is_empty(self) -> bool:
        return not self._servers

    def items(self) -> list[RegisteredServer]:
        return list(self._servers.values())

    def open_pool(self) -> "ServerPool":
        return ServerPool(self.items())


class ServerPool:
    def __init__(self, servers: list[RegisteredServer]) -> None:
        self._servers = servers
        self._stack: ExitStack | None = None
        self.sessions: dict[str, ToolServerSession] = {}

    def __enter__(self) -> "ServerPool":
        self._stack = ExitStack()
        for server in self._servers:
            session = self._stack.enter_context(server.session_factory())
            self.sessions[server.server_id] = session
        return self

    def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        if self._stack is not None:
            self._stack.__exit__(exc_type, exc, tb)


class ToolRegistry:
    def __init__(self) -> None:
        self._tools_by_alias: dict[str, ToolDefinition] = {}

    def register_from_session(self, server_id: str, session: ToolServerSession) -> list[ToolDefinition]:
        registered: list[ToolDefinition] = []
        for tool in session.list_tools():
            definition = ToolDefinition(
                server_id=server_id,
                name=tool["name"],
                description=tool.get("description", "").strip(),
                input_schema=_sanitize_json_schema(
                    tool.get(
                        "inputSchema",
                        {"type": "object", "properties": {}, "additionalProperties": False},
                    )
                ),
            )
            if definition.alias in self._tools_by_alias:
                raise ValueError(f"Tool alias collision: {definition.alias}")
            self._tools_by_alias[definition.alias] = definition
            registered.append(definition)
        return registered

    def get(self, alias: str) -> ToolDefinition:
        try:
            return self._tools_by_alias[alias]
        except KeyError as exc:
            raise KeyError(f"Unknown tool alias '{alias}'") from exc

    def all(self) -> list[ToolDefinition]:
        return list(self._tools_by_alias.values())


def _sanitize_json_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}, "additionalProperties": False}

    sanitized = deepcopy(schema)
    _walk_schema(sanitized)
    return sanitized


def _walk_schema(node: Any) -> None:
    if isinstance(node, dict):
        node_type = node.get("type")
        if node_type == "array" and "items" not in node:
            node["items"] = {}

        properties = node.get("properties")
        if isinstance(properties, dict):
            for value in properties.values():
                _walk_schema(value)

        items = node.get("items")
        if isinstance(items, (dict, list)):
            _walk_schema(items)

        for key in ("anyOf", "oneOf", "allOf", "prefixItems"):
            branch = node.get(key)
            if isinstance(branch, list):
                for item in branch:
                    _walk_schema(item)

        additional_properties = node.get("additionalProperties")
        if isinstance(additional_properties, dict):
            _walk_schema(additional_properties)

    elif isinstance(node, list):
        for item in node:
            _walk_schema(item)
