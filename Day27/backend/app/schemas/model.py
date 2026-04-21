from pydantic import BaseModel


class ModelInfo(BaseModel):
    id: str
    display_name: str
    provider: str
    source_type: str
    context_window: int | None = None
    supports_streaming: bool = True
    supports_tools: bool = False
    is_active: bool = True


class ProviderHealth(BaseModel):
    provider: str
    status: str
    latency_ms: int
    details: str

