from __future__ import annotations

import os
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
REPO_ROOT = ROOT_DIR.parent
DAY21_DIR = REPO_ROOT / "Day21"
LLM_ASSISTANT_DIR = REPO_ROOT / "LLM Assistant"
MCP_DIR = REPO_ROOT / "MCP"

APP_NAME = os.getenv("SUPPORT_APP_NAME", "support-assistant-mvp")
APP_HOST = os.getenv("SUPPORT_APP_HOST", "127.0.0.1")
APP_PORT = int(os.getenv("SUPPORT_APP_PORT", "8010"))

ASSISTANT_BASE_URL = os.getenv("ASSISTANT_BASE_URL", "http://127.0.0.1:8000").rstrip("/")
ASSISTANT_MODEL = os.getenv("ASSISTANT_MODEL", "gpt-4o-mini")
ASSISTANT_AUTH_TOKEN = os.getenv("ASSISTANT_AUTH_TOKEN", "").strip()
ASSISTANT_PROVIDER_ID = os.getenv("ASSISTANT_PROVIDER_ID", "").strip() or None
ASSISTANT_TIMEOUT_SECONDS = float(os.getenv("ASSISTANT_TIMEOUT_SECONDS", "120"))

SUPPORT_MCP_SERVER_SCRIPT = Path(
    os.getenv(
        "SUPPORT_MCP_SERVER_SCRIPT",
        str(MCP_DIR / "support_context" / "server.py"),
    )
).resolve()
SUPPORT_MCP_WAIT_AFTER_START_SECONDS = float(os.getenv("SUPPORT_MCP_WAIT_AFTER_START_SECONDS", "0.0"))
SUPPORT_MCP_TIMEOUT_SECONDS = float(os.getenv("SUPPORT_MCP_TIMEOUT_SECONDS", "20"))

DATA_DIR = ROOT_DIR / "data"
DOCS_DIR = DATA_DIR / "docs"
OUTPUT_DIR = ROOT_DIR / "output"
TESTS_DIR = ROOT_DIR / "tests"

USERS_FILE = Path(os.getenv("SUPPORT_USERS_FILE", str(DATA_DIR / "users.json"))).resolve()
TICKETS_FILE = Path(os.getenv("SUPPORT_TICKETS_FILE", str(DATA_DIR / "tickets.json"))).resolve()

RAG_STRATEGY = os.getenv("SUPPORT_RAG_STRATEGY", "structure")
RAG_INDEX_FILE = Path(
    os.getenv("SUPPORT_RAG_INDEX_FILE", str(OUTPUT_DIR / f"{RAG_STRATEGY}.faiss"))
).resolve()
RAG_METADATA_FILE = Path(
    os.getenv("SUPPORT_RAG_METADATA_FILE", str(OUTPUT_DIR / f"{RAG_STRATEGY}_index.json"))
).resolve()
RAG_EMBED_MODEL = os.getenv("SUPPORT_RAG_EMBED_MODEL", "nomic-embed-text")
RAG_OLLAMA_URL = os.getenv("SUPPORT_RAG_OLLAMA_URL", "http://127.0.0.1:11434")
RAG_TOP_K = int(os.getenv("SUPPORT_RAG_TOP_K", "4"))
RAG_MIN_SCORE = float(os.getenv("SUPPORT_RAG_MIN_SCORE", "0.55"))

DEFAULT_DEMO_USER_COUNT = int(os.getenv("SUPPORT_DEMO_USER_COUNT", "24"))
DEFAULT_DEMO_TICKET_COUNT = int(os.getenv("SUPPORT_DEMO_TICKET_COUNT", "72"))
