import json
import time
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException

from app.core.config import get_settings
from app.schemas.model import ModelInfo, ProviderHealth
from app.schemas.provider import ChatRequest, ChatResponse


class OllamaProvider:
    provider_name = "ollama"

    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.ollama_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
        )

    @staticmethod
    def _normalize_message_payload(request: ChatRequest) -> list[dict[str, str]]:
        messages = list(request.messages)
        if request.system_prompt.strip() and not any(msg["role"] == "system" for msg in messages):
            messages.insert(0, {"role": "system", "content": request.system_prompt.strip()})
        return messages

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = f"HTTP {response.status_code}"
        try:
            payload = response.json()
            detail = payload.get("error", detail)
        except Exception:
            pass
        raise HTTPException(
            status_code=502 if response.status_code >= 500 else response.status_code,
            detail=f"Ollama request failed: {detail}",
        )

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                self._raise_for_status(response)
                payload = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Ollama is unavailable: {exc}") from exc

        items: list[ModelInfo] = []
        for model in payload.get("models", []):
            items.append(
                ModelInfo(
                    id=model.get("model", model.get("name", "")),
                    display_name=model.get("name", model.get("model", "")),
                    provider=self.provider_name,
                    source_type="local",
                    context_window=(model.get("details") or {}).get("context_length"),
                )
            )
        return items

    async def generate(self, request: ChatRequest) -> ChatResponse:
        payload = {
            "model": request.model,
            "messages": self._normalize_message_payload(request),
            "stream": False,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        start = time.perf_counter()
        try:
            async with self._client() as client:
                response = await client.post("/api/chat", json=payload)
                self._raise_for_status(response)
                data = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Ollama is unavailable: {exc}") from exc

        return ChatResponse(
            provider=self.provider_name,
            model=data.get("model", request.model),
            content=(data.get("message") or {}).get("content", ""),
            usage={
                "input_tokens": data.get("prompt_eval_count", 0),
                "output_tokens": data.get("eval_count", 0),
            },
            latency_ms=int((time.perf_counter() - start) * 1000),
            finish_reason=data.get("done_reason", "stop"),
        )

    async def stream_generate(self, request: ChatRequest) -> AsyncIterator[str]:
        payload = {
            "model": request.model,
            "messages": self._normalize_message_payload(request),
            "stream": True,
            "options": {
                "temperature": request.temperature,
                "num_predict": request.max_tokens,
            },
        }

        try:
            async with self._client() as client:
                async with client.stream("POST", "/api/chat", json=payload) as response:
                    self._raise_for_status(response)
                    async for line in response.aiter_lines():
                        if not line:
                            continue
                        chunk = json.loads(line)
                        message = chunk.get("message") or {}
                        content = message.get("content")
                        if content:
                            yield content
                        if chunk.get("done"):
                            break
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"Ollama is unavailable: {exc}") from exc

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            async with self._client() as client:
                response = await client.get("/api/tags")
                self._raise_for_status(response)
            return ProviderHealth(
                provider=self.provider_name,
                status="ok",
                latency_ms=int((time.perf_counter() - started) * 1000),
                details="Ollama is reachable.",
            )
        except (HTTPException, httpx.HTTPError) as exc:
            return ProviderHealth(
                provider=self.provider_name,
                status="offline",
                latency_ms=int((time.perf_counter() - started) * 1000),
                details=str(getattr(exc, "detail", exc)),
            )
