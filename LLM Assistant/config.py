import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()


def _get_env_with_legacy(primary_name: str, legacy_name: str, default: str = "") -> str:
    primary_value = os.getenv(primary_name)
    if primary_value is not None:
        return primary_value.strip()
    legacy_value = os.getenv(legacy_name)
    if legacy_value is not None:
        return legacy_value.strip()
    return default.strip()


def _get_bool_env(name: str, default: str = "false") -> bool:
    return os.getenv(name, default).strip().lower() in {"1", "true", "yes", "on"}

APP_NAME = os.getenv("APP_NAME", "agent-memory-gateway").strip()
APP_VERSION = os.getenv("APP_VERSION", "0.1.0").strip()
APP_HOST = os.getenv("APP_HOST", "0.0.0.0").strip()
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = _get_bool_env("DEBUG")
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").strip().upper()

LLM_API_KEY = _get_env_with_legacy("LLM_API_KEY", "PROXYAPI_API_KEY")
LLM_BASE_URL = _get_env_with_legacy("LLM_BASE_URL", "PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1")
DEFAULT_LLM_PROVIDER = os.getenv("DEFAULT_LLM_PROVIDER", "default").strip() or "default"
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "").strip() or LLM_API_KEY
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))
MCP_ENABLED = _get_bool_env("MCP_ENABLED")
MCP_SERVER_SCRIPT = Path(os.getenv("MCP_SERVER_SCRIPT", "../Day16/server.py")).resolve()
_mcp_server_scripts_raw = os.getenv("MCP_SERVER_SCRIPTS", "").strip()
if _mcp_server_scripts_raw:
    try:
        MCP_SERVER_SCRIPTS = [
            Path(item).resolve()
            for item in json.loads(_mcp_server_scripts_raw)
            if isinstance(item, str) and item.strip()
        ]
    except json.JSONDecodeError:
        MCP_SERVER_SCRIPTS = [
            Path(item.strip()).resolve()
            for item in _mcp_server_scripts_raw.split(";")
            if item.strip()
        ]
else:
    MCP_SERVER_SCRIPTS = []
MCP_WAIT_AFTER_START_SECONDS = float(os.getenv("MCP_WAIT_AFTER_START_SECONDS", "0"))
MCP_MAX_TOOL_ROUNDTRIPS = int(os.getenv("MCP_MAX_TOOL_ROUNDTRIPS", "4"))
MCP_TOOL_CALL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_CALL_TIMEOUT_SECONDS", "20"))

RAG_ENABLED = _get_bool_env("RAG_ENABLED")
RAG_STRATEGY = os.getenv("RAG_STRATEGY", "structure").strip() or "structure"
RAG_INDEX_FILE = Path(os.getenv("RAG_INDEX_FILE", "")).resolve() if os.getenv("RAG_INDEX_FILE", "").strip() else None
RAG_METADATA_FILE = (
    Path(os.getenv("RAG_METADATA_FILE", "")).resolve() if os.getenv("RAG_METADATA_FILE", "").strip() else None
)
RAG_EMBED_MODEL = os.getenv("RAG_EMBED_MODEL", "bge-m3").strip()
RAG_OLLAMA_URL = os.getenv("RAG_OLLAMA_URL", "http://localhost:11434").strip()
RAG_MAX_CHUNKS = int(os.getenv("RAG_MAX_CHUNKS", "5"))
RAG_MIN_RELEVANCE_SCORE = float(os.getenv("RAG_MIN_RELEVANCE_SCORE", "0.75"))
RAG_DENSE_SEARCH_ENABLED = _get_bool_env("RAG_DENSE_SEARCH_ENABLED", "true")
RAG_LEXICAL_RERANK_ENABLED = _get_bool_env("RAG_LEXICAL_RERANK_ENABLED", "true")
RAG_LEXICAL_FALLBACK_ENABLED = _get_bool_env("RAG_LEXICAL_FALLBACK_ENABLED", "true")

MAX_TEMPERATURE = float(os.getenv("MAX_TEMPERATURE", "1.2"))
MAX_MAX_TOKENS = int(os.getenv("MAX_MAX_TOKENS", "4000"))

HISTORY_LIMIT = int(os.getenv("HISTORY_LIMIT", "20"))
MAX_HISTORY_LIMIT = int(os.getenv("MAX_HISTORY_LIMIT", "100"))

SUMMARY_TRIGGER_MESSAGES = int(os.getenv("SUMMARY_TRIGGER_MESSAGES", "24"))
SUMMARY_KEEP_LAST_MESSAGES = int(os.getenv("SUMMARY_KEEP_LAST_MESSAGES", "10"))
SUMMARY_MAX_INPUT_MESSAGES = int(os.getenv("SUMMARY_MAX_INPUT_MESSAGES", "100"))
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "500"))
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "").strip()

RETRIEVAL_ENABLED = _get_bool_env("RETRIEVAL_ENABLED", "true")
RETRIEVAL_LIMIT = int(os.getenv("RETRIEVAL_LIMIT", "6"))
RETRIEVAL_MIN_QUERY_CHARS = int(os.getenv("RETRIEVAL_MIN_QUERY_CHARS", "8"))
RETRIEVAL_CANDIDATE_POOL = int(os.getenv("RETRIEVAL_CANDIDATE_POOL", "80"))
RETRIEVAL_MAX_CONTENT_CHARS = int(os.getenv("RETRIEVAL_MAX_CONTENT_CHARS", "1200"))
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.08"))
RETRIEVAL_USE_TRIGRAM = _get_bool_env("RETRIEVAL_USE_TRIGRAM", "true")

STICKY_FACTS_ENABLED = _get_bool_env("STICKY_FACTS_ENABLED", "true")
STICKY_FACTS_TRIGGER_MESSAGES = int(os.getenv("STICKY_FACTS_TRIGGER_MESSAGES", "6"))
STICKY_FACTS_MAX_INPUT_MESSAGES = int(os.getenv("STICKY_FACTS_MAX_INPUT_MESSAGES", "24"))
STICKY_FACTS_MAX_TOKENS = int(os.getenv("STICKY_FACTS_MAX_TOKENS", "350"))
STICKY_FACTS_MODEL = os.getenv("STICKY_FACTS_MODEL", "").strip()
STICKY_FACTS_MAX_ITEMS = int(os.getenv("STICKY_FACTS_MAX_ITEMS", "20"))

TASK_MEMORY_ENABLED = _get_bool_env("TASK_MEMORY_ENABLED", "true")
TASK_AUTO_ID_FOR_RAG_CHAT = _get_bool_env("TASK_AUTO_ID_FOR_RAG_CHAT", "true")
TASK_SHOW_TRANSITIONS = _get_bool_env("TASK_SHOW_TRANSITIONS", "true")
TASK_REQUIRE_PLAN_APPROVAL = _get_bool_env("TASK_REQUIRE_PLAN_APPROVAL", "true")
TASK_GOAL_MAX_CHARS = int(os.getenv("TASK_GOAL_MAX_CHARS", "1000"))
TASK_LAST_USER_MESSAGE_MAX_CHARS = int(os.getenv("TASK_LAST_USER_MESSAGE_MAX_CHARS", "1000"))
TASK_LAST_RESPONSE_PREVIEW_CHARS = int(os.getenv("TASK_LAST_RESPONSE_PREVIEW_CHARS", "500"))
TASK_CLARIFIED_POINTS_LIMIT = int(os.getenv("TASK_CLARIFIED_POINTS_LIMIT", "12"))
TASK_CONSTRAINTS_LIMIT = int(os.getenv("TASK_CONSTRAINTS_LIMIT", "10"))
TASK_FIXED_TERMS_LIMIT = int(os.getenv("TASK_FIXED_TERMS_LIMIT", "12"))
TASK_OPEN_QUESTIONS_LIMIT = int(os.getenv("TASK_OPEN_QUESTIONS_LIMIT", "5"))

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

INVARIANTS_FILE = Path(os.getenv("INVARIANTS_FILE", "docs/assistant_invariants.json"))

DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))


def _load_llm_providers() -> list[dict[str, str]]:
    raw = os.getenv("LLM_PROVIDERS", "").strip()
    providers: list[dict[str, str]] = []
    if raw:
        parsed = json.loads(raw)
        if not isinstance(parsed, list):
            raise RuntimeError("LLM_PROVIDERS must be a JSON array")
        for item in parsed:
            if not isinstance(item, dict):
                continue
            provider_id = str(item.get("id") or "").strip()
            base_url = str(item.get("base_url") or "").strip()
            if not provider_id or not base_url:
                continue
            api_key = str(item.get("api_key") or "").strip()
            api_key_env = str(item.get("api_key_env") or "").strip()
            if api_key_env:
                api_key = os.getenv(api_key_env, "").strip()
            providers.append(
                {
                    "id": provider_id,
                    "name": str(item.get("name") or provider_id).strip(),
                    "base_url": base_url,
                    "api_key": api_key or "local-no-key-required",
                    "default_model": str(item.get("default_model") or "").strip(),
                }
            )

    if providers:
        return providers

    return [
        {
            "id": DEFAULT_LLM_PROVIDER,
            "name": DEFAULT_LLM_PROVIDER,
            "base_url": LLM_BASE_URL,
            "api_key": LLM_API_KEY or "local-no-key-required",
            "default_model": DEFAULT_MODEL,
        }
    ]


LLM_PROVIDERS = _load_llm_providers()

if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL is required")
