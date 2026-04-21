from pydantic import BaseModel, Field


class SettingsRead(BaseModel):
    default_provider: str
    default_model: str
    default_temperature: float = Field(ge=0.0, le=2.0)
    default_max_tokens: int = Field(ge=1, le=8192)
    system_prompt: str


class SettingsUpdate(BaseModel):
    default_provider: str | None = None
    default_model: str | None = None
    default_temperature: float | None = Field(default=None, ge=0.0, le=2.0)
    default_max_tokens: int | None = Field(default=None, ge=1, le=8192)
    system_prompt: str | None = None

