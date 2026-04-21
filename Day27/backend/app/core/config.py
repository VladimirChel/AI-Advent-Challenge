from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = "development"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    database_url: str = "postgresql+psycopg://llmchat:llmchat@localhost:5432/llmchat"
    proxyapi_base_url: str = "https://api.proxyapi.ru/openai/v1"
    proxyapi_api_key: str = "replace_me"
    ollama_base_url: str = "http://localhost:11434"
    default_provider: str = "proxyapi"
    default_model: str = "gpt-4o-mini"
    request_timeout_seconds: int = 120

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
