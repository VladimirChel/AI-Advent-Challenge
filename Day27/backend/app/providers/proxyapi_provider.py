import json
import time
from collections.abc import AsyncIterator

import httpx
from fastapi import HTTPException

from app.core.config import get_settings
from app.schemas.model import ModelInfo, ProviderHealth
from app.schemas.provider import ChatRequest, ChatResponse


class ProxyApiProvider:
    provider_name = "proxyapi"
    preferred_chat_models = [
        "gpt-4o-mini",
        "gpt-4o",
        "gpt-5.4-mini",
        "gpt-5.4",
        "o4-mini",
    ]

    def __init__(self) -> None:
        self.settings = get_settings()

    def _headers(self) -> dict[str, str]:
        api_key = self.settings.proxyapi_api_key.strip()
        if not api_key or api_key == "replace_me":
            raise HTTPException(
                status_code=503,
                detail="ProxyAPI API key is not configured. Set PROXYAPI_API_KEY.",
            )
        return {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        }

    def _client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(
            base_url=self.settings.proxyapi_base_url.rstrip("/"),
            timeout=self.settings.request_timeout_seconds,
            headers=self._headers(),
        )

    @staticmethod
    def _normalize_message_payload(request: ChatRequest) -> list[dict[str, str]]:
        messages = list(request.messages)
        if request.system_prompt.strip() and not any(msg["role"] == "system" for msg in messages):
            messages.insert(0, {"role": "system", "content": request.system_prompt.strip()})
        return messages

    @staticmethod
    def _responses_input(request: ChatRequest) -> str:
        lines: list[str] = []
        for message in ProxyApiProvider._normalize_message_payload(request):
            role = message["role"].capitalize()
            lines.append(f"{role}: {message['content']}")
        lines.append("Assistant:")
        return "\n\n".join(lines)

    @staticmethod
    def _extract_responses_text(data: dict[str, object]) -> str:
        output_text = data.get("output_text")
        if isinstance(output_text, str) and output_text:
            return output_text

        output = data.get("output")
        if isinstance(output, list):
            chunks: list[str] = []
            for item in output:
                if not isinstance(item, dict):
                    continue
                contents = item.get("content")
                if not isinstance(contents, list):
                    continue
                for content in contents:
                    if not isinstance(content, dict):
                        continue
                    text = content.get("text")
                    if isinstance(text, str):
                        chunks.append(text)
            return "".join(chunks)
        return ""

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.is_success:
            return
        detail = f"HTTP {response.status_code}"
        try:
            payload = response.json()
            if isinstance(payload.get("error"), dict):
                detail = payload.get("error", {}).get("message", detail)
            elif isinstance(payload.get("message"), str):
                detail = payload["message"]
            else:
                detail = response.text or detail
        except Exception:
            try:
                detail = response.text or detail
            except Exception:
                pass
        raise HTTPException(
            status_code=502 if response.status_code >= 500 else response.status_code,
            detail=f"ProxyAPI request failed: {detail}",
        )

    async def list_models(self) -> list[ModelInfo]:
        try:
            async with self._client() as client:
                response = await client.get("/models")
                self._raise_for_status(response)
                payload = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"ProxyAPI is unavailable: {exc}") from exc

        available = {
            model["id"]: model
            for model in payload.get("data", [])
            if isinstance(model, dict) and isinstance(model.get("id"), str)
        }

        items: list[ModelInfo] = []
        for model_id in self.preferred_chat_models:
            if model_id not in available:
                continue
            items.append(
                ModelInfo(
                    id=model_id,
                    display_name=model_id,
                    provider=self.provider_name,
                    source_type="cloud",
                )
            )

        if items:
            return items

        return [
            ModelInfo(
                id=model_id,
                display_name=model_id,
                provider=self.provider_name,
                source_type="cloud",
            )
            for model_id in self.preferred_chat_models
        ]

    async def generate(self, request: ChatRequest) -> ChatResponse:
        start = time.perf_counter()
        try:
            async with self._client() as client:
                payload = {
                    "model": request.model,
                    "messages": self._normalize_message_payload(request),
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "stream": False,
                }
                response = await client.post("/chat/completions", json=payload)
                if response.status_code == 400:
                    responses_payload = {
                        "model": request.model,
                        "input": self._responses_input(request),
                        "temperature": request.temperature,
                        "max_output_tokens": request.max_tokens,
                    }
                    response = await client.post("/responses", json=responses_payload)
                    self._raise_for_status(response)
                    data = response.json()
                    usage = data.get("usage") or {}
                    return ChatResponse(
                        provider=self.provider_name,
                        model=str(data.get("model", request.model)),
                        content=self._extract_responses_text(data),
                        usage={
                            "input_tokens": int(usage.get("input_tokens", 0) or 0),
                            "output_tokens": int(usage.get("output_tokens", 0) or 0),
                        },
                        latency_ms=int((time.perf_counter() - start) * 1000),
                        finish_reason="stop",
                    )

                self._raise_for_status(response)
                data = response.json()
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"ProxyAPI is unavailable: {exc}") from exc

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        usage = data.get("usage") or {}
        return ChatResponse(
            provider=self.provider_name,
            model=data.get("model", request.model),
            content=message.get("content", ""),
            usage={
                "input_tokens": usage.get("prompt_tokens", 0),
                "output_tokens": usage.get("completion_tokens", 0),
            },
            latency_ms=int((time.perf_counter() - start) * 1000),
            finish_reason=choice.get("finish_reason", "stop"),
        )

    async def stream_generate(self, request: ChatRequest) -> AsyncIterator[str]:
        try:
            async with self._client() as client:
                use_responses_api = False
                payload = {
                    "model": request.model,
                    "messages": self._normalize_message_payload(request),
                    "temperature": request.temperature,
                    "max_tokens": request.max_tokens,
                    "stream": True,
                }
                async with client.stream("POST", "/chat/completions", json=payload) as response:
                    if response.status_code == 400:
                        use_responses_api = True
                    else:
                        self._raise_for_status(response)
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            raw = line[6:].strip()
                            if raw == "[DONE]":
                                return
                            chunk = json.loads(raw)
                            choices = chunk.get("choices") or []
                            if not choices:
                                continue
                            delta = choices[0].get("delta") or {}
                            content = delta.get("content")
                            if content:
                                yield content
                        return

                if use_responses_api:
                    responses_payload = {
                        "model": request.model,
                        "input": self._responses_input(request),
                        "temperature": request.temperature,
                        "max_output_tokens": request.max_tokens,
                        "stream": True,
                    }
                    async with client.stream("POST", "/responses", json=responses_payload) as response:
                        self._raise_for_status(response)
                        async for line in response.aiter_lines():
                            if not line or not line.startswith("data: "):
                                continue
                            raw = line[6:].strip()
                            if raw == "[DONE]":
                                break
                            chunk = json.loads(raw)
                            if chunk.get("type") == "response.output_text.delta":
                                delta = chunk.get("delta")
                                if isinstance(delta, str) and delta:
                                    yield delta
        except httpx.HTTPError as exc:
            raise HTTPException(status_code=503, detail=f"ProxyAPI is unavailable: {exc}") from exc

    async def health_check(self) -> ProviderHealth:
        started = time.perf_counter()
        try:
            async with self._client() as client:
                response = await client.get("/models")
                self._raise_for_status(response)
            return ProviderHealth(
                provider=self.provider_name,
                status="ok",
                latency_ms=int((time.perf_counter() - started) * 1000),
                details="ProxyAPI is reachable.",
            )
        except (HTTPException, httpx.HTTPError) as exc:
            return ProviderHealth(
                provider=self.provider_name,
                status="offline",
                latency_ms=int((time.perf_counter() - started) * 1000),
                details=str(getattr(exc, "detail", exc)),
            )
