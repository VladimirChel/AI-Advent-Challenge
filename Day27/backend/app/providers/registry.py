from fastapi import HTTPException

from app.providers.ollama_provider import OllamaProvider
from app.providers.proxyapi_provider import ProxyApiProvider


class ProviderRegistry:
    def __init__(self) -> None:
        self._providers = {
            "proxyapi": ProxyApiProvider(),
            "ollama": OllamaProvider(),
        }

    def get(self, provider_name: str):
        provider = self._providers.get(provider_name)
        if provider is None:
            raise HTTPException(status_code=404, detail=f"Unknown provider: {provider_name}")
        return provider

    def all(self) -> dict[str, object]:
        return self._providers


provider_registry = ProviderRegistry()

