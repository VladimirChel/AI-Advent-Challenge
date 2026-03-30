from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Literal
import requests

MemoryStrategy = Literal["none", "window", "summary", "retrieval", "hybrid", "facts", "hybrid_facts"]
ChatRole = Literal["system", "user", "assistant"]


@dataclass
class ChatMessage:
    role: ChatRole
    content: str


@dataclass
class ResponseValidationRules:
    min_output_length: int | None = None
    max_output_length: int | None = None
    must_contain: list[str] = field(default_factory=list)
    forbid_phrases: list[str] = field(default_factory=list)
    require_json: bool = False


@dataclass
class LLMRequest:
    messages: list[ChatMessage]
    model: str = "openai/gpt-4o-mini"
    conversation_id: str | None = None
    branch_id: str = "main"
    fork_from_branch_id: str | None = None
    fork_from_message_uuid: str | None = None
    use_memory: bool = True
    memory_strategy: MemoryStrategy = "hybrid"
    history_limit: int = 20
    retrieval_enabled: bool = True
    retrieval_limit: int = 6
    sticky_facts_enabled: bool = True
    temperature: float = 0.2
    max_tokens: int = 500
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0
    user_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    validation: ResponseValidationRules | None = None
    stop: list[str] | None = None

    def to_payload(self) -> dict[str, Any]:
        payload = asdict(self)
        return payload


class LLMGatewayClient:
    def __init__(self, base_url: str, headers: dict[str, str] | None = None, timeout: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})
        if headers:
            self.session.headers.update(headers)

    def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, json_data: Any = None) -> Any:
        response = self.session.request(
            method=method,
            url=f"{self.base_url}{path}",
            params=params,
            json=json_data,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def generate(self, payload: LLMRequest | dict[str, Any]) -> dict[str, Any]:
        body = payload.to_payload() if isinstance(payload, LLMRequest) else payload
        return self._request("POST", "/generate", json_data=body)

    def get_conversation_messages(self, conversation_id: str, branch_id: str = "main", limit: int = 20) -> dict[str, Any]:
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/messages",
            params={"branch_id": branch_id, "limit": limit},
        )

    def get_conversation_summary(self, conversation_id: str, branch_id: str = "main") -> dict[str, Any]:
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/summary",
            params={"branch_id": branch_id},
        )

    def refresh_conversation_summary(
        self,
        conversation_id: str,
        branch_id: str = "main",
        model: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"branch_id": branch_id}
        if model:
            params["model"] = model
        if user_id:
            params["user_id"] = user_id
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/summary/refresh",
            params=params,
        )

    def get_conversation_facts(self, conversation_id: str, branch_id: str = "main") -> dict[str, Any]:
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/facts",
            params={"branch_id": branch_id},
        )

    def refresh_conversation_facts(
        self,
        conversation_id: str,
        branch_id: str = "main",
        model: str | None = None,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        params = {"branch_id": branch_id}
        if model:
            params["model"] = model
        if user_id:
            params["user_id"] = user_id
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/facts/refresh",
            params=params,
        )

    def list_conversation_branches(self, conversation_id: str) -> dict[str, Any]:
        return self._request("GET", f"/conversations/{conversation_id}/branches")

    def create_conversation_branch(
        self,
        conversation_id: str,
        branch_id: str,
        fork_from_message_uuid: str,
        source_branch_id: str = "main",
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/branches",
            params={
                "branch_id": branch_id,
                "fork_from_message_uuid": fork_from_message_uuid,
                "source_branch_id": source_branch_id,
            },
        )

    def list_models(self) -> dict[str, Any]:
        return self._request("GET", "/models")
