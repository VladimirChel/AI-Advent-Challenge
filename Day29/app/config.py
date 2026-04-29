from __future__ import annotations

import os
import json
from dataclasses import dataclass, field
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = BASE_DIR / ".env"
DEFAULT_DOCUMENTS_DIR = BASE_DIR / "documents"
DEFAULT_OUTPUT_DIR = BASE_DIR / "output"
DEFAULT_SNAPSHOTS_DIR = DEFAULT_OUTPUT_DIR / "snapshots"
DEFAULT_ONEC_PRINT_FORMS_DIR = DEFAULT_OUTPUT_DIR / "print_forms"


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


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    return int(raw.strip())


def _env_list(name: str) -> tuple[str, ...]:
    raw = os.getenv(name, "")
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def _env_json_dict(name: str) -> dict[str, object]:
    raw = os.getenv(name, "").strip()
    if not raw:
        return {}
    payload = json.loads(raw)
    if not isinstance(payload, dict):
        raise ValueError(f"{name} must contain a JSON object")
    return payload


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
    onec_print_service_url: str = field(default_factory=lambda: os.getenv("ONEC_PRINT_SERVICE_URL", ""))
    onec_print_service_auth_type: str = field(default_factory=lambda: os.getenv("ONEC_PRINT_SERVICE_AUTH_TYPE", "basic"))
    onec_print_service_username: str = field(default_factory=lambda: os.getenv("ONEC_PRINT_SERVICE_USERNAME", ""))
    onec_print_service_password: str = field(default_factory=lambda: os.getenv("ONEC_PRINT_SERVICE_PASSWORD", ""))
    onec_print_service_token: str = field(default_factory=lambda: os.getenv("ONEC_PRINT_SERVICE_TOKEN", ""))
    onec_print_service_timeout_seconds: int = field(default_factory=lambda: _env_int("ONEC_PRINT_SERVICE_TIMEOUT_SECONDS", 30))
    onec_print_forms_dir: Path = field(default_factory=lambda: Path(os.getenv("ONEC_PRINT_FORMS_DIR", str(DEFAULT_ONEC_PRINT_FORMS_DIR))))
    onec_print_allowed_document_types: tuple[str, ...] = field(default_factory=lambda: _env_list("ONEC_PRINT_ALLOWED_DOCUMENT_TYPES"))
    onec_document_type_map: dict[str, object] = field(default_factory=lambda: _env_json_dict("ONEC_DOCUMENT_TYPE_MAP"))
    onec_print_form_map: dict[str, object] = field(default_factory=lambda: _env_json_dict("ONEC_PRINT_FORM_MAP"))

    def ensure_directories(self) -> None:
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.snapshots_dir.mkdir(parents=True, exist_ok=True)
        self.onec_print_forms_dir.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    _load_dotenv(ENV_FILE)
    config = AppConfig()
    config.ensure_directories()
    return config
