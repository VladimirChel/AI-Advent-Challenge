import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

APP_NAME = os.getenv("APP_NAME", "agent-memory-gateway").strip()
APP_VERSION = os.getenv("APP_VERSION", "0.1.0").strip()
APP_HOST = os.getenv("APP_HOST", "0.0.0.0").strip()
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEBUG = os.getenv("DEBUG", "false").strip().lower() in {"1", "true", "yes", "on"}

PROXYAPI_API_KEY = os.getenv("PROXYAPI_API_KEY", "").strip()
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
AUTH_SECRET_KEY = os.getenv("AUTH_SECRET_KEY", "").strip() or PROXYAPI_API_KEY
AUTH_TOKEN_TTL_SECONDS = int(os.getenv("AUTH_TOKEN_TTL_SECONDS", "86400"))

LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))
LOG_DIR.mkdir(parents=True, exist_ok=True)

DB_POOL_MIN_SIZE = int(os.getenv("DB_POOL_MIN_SIZE", "1"))
DB_POOL_MAX_SIZE = int(os.getenv("DB_POOL_MAX_SIZE", "10"))

if not PROXYAPI_API_KEY:
    raise RuntimeError("Environment variable PROXYAPI_API_KEY is required")

if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL is required")
