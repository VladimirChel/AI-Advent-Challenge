import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "day18-scheduled-agent").strip()
APP_VERSION = os.getenv("APP_VERSION", "0.1.0").strip()
APP_HOST = os.getenv("APP_HOST", "0.0.0.0").strip()
APP_PORT = int(os.getenv("APP_PORT", "8018"))
DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}
LOG_LEVEL = os.getenv("LOG_LEVEL", "DEBUG" if DEBUG else "INFO").strip().upper()

PROXYAPI_API_KEY = os.getenv("PROXYAPI_API_KEY", "").strip()
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1").strip()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))

DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

MCP_SERVER_SCRIPT = Path(os.getenv("MCP_SERVER_SCRIPT", "../Day16/server.py")).resolve()
MCP_WAIT_AFTER_START_SECONDS = float(os.getenv("MCP_WAIT_AFTER_START_SECONDS", "3"))
MCP_TOOL_CALL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_CALL_TIMEOUT_SECONDS", "20"))

COLLECT_INTERVAL_SECONDS = int(os.getenv("COLLECT_INTERVAL_SECONDS", "300"))
AGGREGATE_INTERVAL_SECONDS = int(os.getenv("AGGREGATE_INTERVAL_SECONDS", "900"))
SUMMARY_INTERVAL_SECONDS = int(os.getenv("SUMMARY_INTERVAL_SECONDS", "3600"))
SUMMARY_LOOKBACK_HOURS = int(os.getenv("SUMMARY_LOOKBACK_HOURS", "1"))

if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL is required")
