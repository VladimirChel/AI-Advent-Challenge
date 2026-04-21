from typing import AsyncIterator, Protocol

from app.schemas.model import ModelInfo, ProviderHealth
from app.schemas.provider import ChatRequest, ChatResponse


class BaseLlmProvider(Protocol):
    async def list_models(self) -> list[ModelInfo]:
        ...

    async def generate(self, request: ChatRequest) -> ChatResponse:
        ...

    async def stream_generate(self, request: ChatRequest) -> AsyncIterator[str]:
        ...

    async def health_check(self) -> ProviderHealth:
        ...

