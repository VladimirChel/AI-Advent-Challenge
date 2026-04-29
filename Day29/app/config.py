from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
DEFAULT_DOCUMENTS_DIR = BASE_DIR / "documents"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_SNAPSHOTS_DIR = DEFAULT_OUTPUT_DIR / "snapshots"


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(slots=True)
class AppConfig:
    documents_dir: Path = field(default_factory=lambda: Path(os.getenv("DEBT_DOCUMENTS_DIR", str(DEFAULT_DOCUMENTS_DIR))))
    output_dir: Path = field(default_factory=lambda: Path(os.getenv("DEBT_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))))
    snapshots_dir: Path = field(default_factory=lambda: Path(os.getenv("DEBT_SNAPSHOTS_DIR", str(DEFAULT_SNAPSHOTS_DIR))))
    llm_assistant_url: str = field(default_factory=lambda: os.getenv("LLM_ASSISTANT_URL", "http://127.0.0.1:8000/generate"))
    llm_assistant_token: str = field(default_factory=lambda: os.getenv("LLM_ASSISTANT_TOKEN", ""))
    llm_model: str = field(default_factory=lambda: os.getenv("LLM_MODEL", "gpt-4o-mini"))
    llm_provider_id: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER_ID", ""))
    llm_cloud_mode: bool = field(default_factory=lambda: _env_bool("LLM_CLOUD_MODE", False))
    telegram_bot_token: str = field(default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN", ""))
    telegram_allowed_chat_ids: str = field(default_factory=lambda: os.getenv("TELEGRAM_ALLOWED_CHAT_IDS", ""))
    telegram_poll_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("TELEGRAM_POLL_TIMEOUT_SECONDS", "30")))
    telegram_parse_mode: str = field(default_factory=lambda: os.getenv("TELEGRAM_PARSE_MODE", "HTML"))
    telegram_proxy_url: str = field(default_factory=lambda: os.getenv("TELEGRAM_PROXY_URL", ""))

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    _load_dotenv(ENV_FILE)
    config = AppConfig()
    config.ensure_directories()
    return config
