import os
import json
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "agent-memory-gateway").strip()
APP_VERSION = os.getenv("APP_VERSION", "0.1.0").strip()
APP_HOST = os.getenv("APP_HOST", "0.0.0.0").strip()
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").strip().upper()

PROXYAPI_API_KEY = os.getenv("PROXYAPI_API_KEY", "").strip()
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "").strip() or PROXYAPI_API_KEY
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))
MCP_ENABLED_BY_DEFAULT = os.getenv("MCP_ENABLED_BY_DEFAULT", "false").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
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

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

INVARIANTS_FILE = Path(os.getenv("INVARIANTS_FILE", "docs/assistant_invariants.json"))

DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

if not PROXYAPI_API_KEY:
    raise RuntimeError("Environment variable PROXYAPI_API_KEY is required")

if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL is required")
