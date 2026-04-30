from __future__ import annotations

import argparse
import json
import urllib.error
import urllib.request
from typing import Any

from config import (
    ASSISTANT_AUTH_TOKEN,
    ASSISTANT_BASE_URL,
    ASSISTANT_MODEL,
    ASSISTANT_PROVIDER_ID,
    ASSISTANT_TIMEOUT_SECONDS,
)


class AssistantClientError(RuntimeError):
    pass


class AssistantClient:
    def __init__(
        self,
        *,
        base_url: str = ASSISTANT_BASE_URL,
        model: str = ASSISTANT_MODEL,
        auth_token: str = ASSISTANT_AUTH_TOKEN,
        provider_id: str | None = ASSISTANT_PROVIDER_ID,
        timeout_seconds: float = ASSISTANT_TIMEOUT_SECONDS,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.auth_token = auth_token
        self.provider_id = provider_id
        self.timeout_seconds = timeout_seconds

    def generate(self, *, system_prompt: str, user_prompt: str, conversation_id: str | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "conversation_id": conversation_id,
            "chat_mode": "default",
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "temperature": 0.2,
            "max_tokens": 900,
            "mcp": {"enabled": False},
            "rag": {"enabled": False},
        }
        if self.provider_id:
            payload["provider_id"] = self.provider_id

        body = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if self.auth_token:
            headers["Authorization"] = f"Bearer {self.auth_token}"

        request = urllib.request.Request(
            f"{self.base_url}/generate",
            data=body,
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            details = exc.read().decode("utf-8", errors="replace")
            raise AssistantClientError(
                f"LLM Assistant returned HTTP {exc.code}: {details}"
            ) from exc
        except urllib.error.URLError as exc:
            raise AssistantClientError(
                "Could not reach LLM Assistant. Start the backend and verify ASSISTANT_BASE_URL."
            ) from exc


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Send a test prompt to LLM Assistant.")
    parser.add_argument(
        "--message",
        default="Reply with one short sentence confirming that the backend is reachable.",
        help="User message sent to the LLM Assistant backend.",
    )
    parser.add_argument(
        "--system",
        default="You are a concise backend connectivity test assistant.",
        help="System prompt for the test request.",
    )
    parser.add_argument(
        "--conversation-id",
        default=None,
        help="Optional conversation id.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    client = AssistantClient()
    result = client.generate(
        system_prompt=args.system,
        user_prompt=args.message,
        conversation_id=args.conversation_id,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
