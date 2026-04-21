from fastapi import HTTPException

from app.providers.registry import provider_registry
from app.schemas.model import ModelInfo, ProviderHealth
from app.schemas.provider import ChatRequest, ChatResponse


class ModelService:
    async def list_models(self, provider: str | None = None, source: str | None = None) -> list[ModelInfo]:
        providers = (
            {provider: provider_registry.get(provider)}
            if provider is not None
            else provider_registry.all()
        )
        models: list[ModelInfo] = []
        errors: list[str] = []
        for provider_name, adapter in providers.items():
            try:
                models.extend(await adapter.list_models())
            except HTTPException as exc:
                if provider is not None:
                    raise
                errors.append(f"{provider_name}: {exc.detail}")
        if source is not None:
            models = [model for model in models if model.source_type == source]
        if not models and errors:
            raise HTTPException(status_code=503, detail="; ".join(errors))
        return models

    async def provider_health(self) -> list[ProviderHealth]:
        statuses: list[ProviderHealth] = []
        for adapter in provider_registry.all().values():
            statuses.append(await adapter.health_check())
        return statuses

    async def generate(self, request: ChatRequest) -> ChatResponse:
        provider = provider_registry.get(request.provider)
        return await provider.generate(request)

    async def stream_generate(self, request: ChatRequest):
        provider = provider_registry.get(request.provider)
        async for chunk in provider.stream_generate(request):
            yield chunk


model_service = ModelService()
