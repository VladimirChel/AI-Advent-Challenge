import json
import logging
import os
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

MemoryStrategy = Literal["none", "window", "summary", "retrieval", "hybrid", "facts", "hybrid_facts"]

import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator
from starlette.exceptions import HTTPException as StarletteHTTPException

load_dotenv()


# =========================
# Config
# =========================
PROXYAPI_API_KEY = os.getenv("PROXYAPI_API_KEY", "").strip()
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1").strip()
DATABASE_URL = os.getenv("DATABASE_URL", "").strip()

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
MAX_TEMPERATURE = float(os.getenv("MAX_TEMPERATURE", "1.2"))
MAX_MAX_TOKENS = int(os.getenv("MAX_MAX_TOKENS", "4000"))
DEFAULT_HISTORY_LIMIT = int(os.getenv("DEFAULT_HISTORY_LIMIT", "20"))
MAX_HISTORY_LIMIT = int(os.getenv("MAX_HISTORY_LIMIT", "100"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))

SUMMARY_TRIGGER_MESSAGES = int(os.getenv("SUMMARY_TRIGGER_MESSAGES", "24"))
SUMMARY_KEEP_LAST_MESSAGES = int(os.getenv("SUMMARY_KEEP_LAST_MESSAGES", "10"))
SUMMARY_MAX_INPUT_MESSAGES = int(os.getenv("SUMMARY_MAX_INPUT_MESSAGES", "100"))
SUMMARY_MAX_TOKENS = int(os.getenv("SUMMARY_MAX_TOKENS", "500"))
SUMMARY_MODEL = os.getenv("SUMMARY_MODEL", "").strip()

RETRIEVAL_ENABLED_BY_DEFAULT = os.getenv("RETRIEVAL_ENABLED_BY_DEFAULT", "true").strip().lower() in {"1", "true", "yes", "on"}
RETRIEVAL_LIMIT = int(os.getenv("RETRIEVAL_LIMIT", "6"))
RETRIEVAL_MIN_QUERY_CHARS = int(os.getenv("RETRIEVAL_MIN_QUERY_CHARS", "8"))
RETRIEVAL_CANDIDATE_POOL = int(os.getenv("RETRIEVAL_CANDIDATE_POOL", "80"))
RETRIEVAL_MAX_CONTENT_CHARS = int(os.getenv("RETRIEVAL_MAX_CONTENT_CHARS", "1200"))
RETRIEVAL_MIN_SCORE = float(os.getenv("RETRIEVAL_MIN_SCORE", "0.08"))
RETRIEVAL_USE_TRIGRAM = os.getenv("RETRIEVAL_USE_TRIGRAM", "true").strip().lower() in {"1", "true", "yes", "on"}

STICKY_FACTS_ENABLED_BY_DEFAULT = os.getenv("STICKY_FACTS_ENABLED_BY_DEFAULT", "true").strip().lower() in {"1", "true", "yes", "on"}
STICKY_FACTS_TRIGGER_MESSAGES = int(os.getenv("STICKY_FACTS_TRIGGER_MESSAGES", "6"))
STICKY_FACTS_MAX_INPUT_MESSAGES = int(os.getenv("STICKY_FACTS_MAX_INPUT_MESSAGES", "24"))
STICKY_FACTS_MAX_TOKENS = int(os.getenv("STICKY_FACTS_MAX_TOKENS", "350"))
STICKY_FACTS_MODEL = os.getenv("STICKY_FACTS_MODEL", "").strip()
STICKY_FACTS_MAX_ITEMS = int(os.getenv("STICKY_FACTS_MAX_ITEMS", "20"))

if not PROXYAPI_API_KEY:
    raise RuntimeError("Environment variable PROXYAPI_API_KEY is required")

if not DATABASE_URL:
    raise RuntimeError("Environment variable DATABASE_URL is required")

if SUMMARY_KEEP_LAST_MESSAGES < 1:
    raise RuntimeError("SUMMARY_KEEP_LAST_MESSAGES must be >= 1")

if SUMMARY_TRIGGER_MESSAGES <= SUMMARY_KEEP_LAST_MESSAGES:
    raise RuntimeError("SUMMARY_TRIGGER_MESSAGES must be greater than SUMMARY_KEEP_LAST_MESSAGES")

LOG_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# DB Pool
# =========================
db_pool = ConnectionPool(conninfo=DATABASE_URL, min_size=1, max_size=10, open=False)

# =========================
# Logging
# =========================
logger = logging.getLogger("llm_gateway")
logger.setLevel(logging.INFO)
logger.handlers.clear()

formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

stream_handler = logging.StreamHandler()
stream_handler.setFormatter(formatter)
logger.addHandler(stream_handler)

file_handler = logging.FileHandler(LOG_DIR / "app.log", encoding="utf-8")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

audit_logger = logging.getLogger("audit")
audit_logger.setLevel(logging.INFO)
audit_logger.handlers.clear()

audit_handler = logging.FileHandler(LOG_DIR / "audit.jsonl", encoding="utf-8")
audit_handler.setFormatter(logging.Formatter("%(message)s"))
audit_logger.addHandler(audit_handler)

# =========================
# OpenAI client via ProxyAPI
# =========================
client = OpenAI(
    api_key=PROXYAPI_API_KEY,
    base_url=PROXYAPI_BASE_URL,
    timeout=REQUEST_TIMEOUT_SECONDS,
)


# =========================
# FastAPI lifespan
# =========================
async def lifespan(app: FastAPI):
    db_pool.open()
    init_db()
    logger.info("Database initialized")
    try:
        yield
    finally:
        db_pool.close()
        logger.info("Database pool closed")


# =========================
# FastAPI
# =========================
app = FastAPI(
    title="LLM Gateway via ProxyAPI",
    version="1.3.0",
    description="Прокси-приложение для контролируемых запросов к LLM через ProxyAPI",
    lifespan=lifespan,
)


# =========================
# Models
# =========================
class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1, max_length=50000)


class ResponseValidationRules(BaseModel):
    min_output_length: int | None = Field(default=None, ge=1, le=20000)
    max_output_length: int | None = Field(default=None, ge=1, le=200000)
    must_contain: list[str] = Field(default_factory=list)
    forbid_phrases: list[str] = Field(default_factory=list)
    require_json: bool = False


class LLMRequest(BaseModel):
    model: str = Field(default=DEFAULT_MODEL, min_length=3, max_length=200)
    messages: list[ChatMessage] = Field(..., min_length=1)
    conversation_id: str | None = Field(default=None, max_length=200)
    branch_id: str = Field(default="main", min_length=1, max_length=200)
    fork_from_branch_id: str | None = Field(default=None, max_length=200)
    fork_from_message_uuid: str | None = Field(default=None, max_length=200)
    use_memory: bool = True
    memory_strategy: MemoryStrategy = "hybrid"
    history_limit: int = Field(default=DEFAULT_HISTORY_LIMIT, ge=0, le=MAX_HISTORY_LIMIT)
    retrieval_enabled: bool = Field(default=RETRIEVAL_ENABLED_BY_DEFAULT)
    retrieval_limit: int = Field(default=RETRIEVAL_LIMIT, ge=0, le=20)
    sticky_facts_enabled: bool = Field(default=STICKY_FACTS_ENABLED_BY_DEFAULT)
    temperature: float = Field(default=0.2, ge=0.0)
    max_tokens: int = Field(default=500, ge=1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    user_id: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation: ResponseValidationRules | None = None
    stop: list[str] | None = Field(default=None, max_length=16)

    @field_validator("metadata")
    @classmethod
    def validate_metadata(cls, value: dict[str, Any]) -> dict[str, Any]:
        encoded = json.dumps(value, ensure_ascii=False)
        if len(encoded) > 10000:
            raise ValueError("metadata is too large")
        return value

    @field_validator("stop")
    @classmethod
    def validate_stop(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value

        cleaned = [item.strip() for item in value if item and item.strip()]
        if len(cleaned) != len(value):
            raise ValueError("stop must not contain empty strings")

        for item in cleaned:
            if len(item) > 200:
                raise ValueError("each stop sequence must be <= 200 characters")

        return cleaned

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value > MAX_TEMPERATURE:
            raise ValueError(f"temperature must be <= {MAX_TEMPERATURE}")
        return value

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, value: int) -> int:
        if value > MAX_MAX_TOKENS:
            raise ValueError(f"max_tokens must be <= {MAX_MAX_TOKENS}")
        return value

    @field_validator("model")
    @classmethod
    def validate_model(cls, value: str) -> str:
        if "/" not in value:
            raise ValueError("model must be in format 'provider/model'")
        return value


class RetrievedMemoryItem(BaseModel):
    seq_no: int
    role: Literal["system", "user", "assistant"]
    score: float
    content: str


class LLMResponse(BaseModel):
    request_id: str
    conversation_id: str
    branch_id: str
    created_at: str
    model: str
    content: str
    finish_reason: str | None
    latency_ms: int
    usage: dict[str, Any]
    validation: dict[str, Any]
    raw_response_id: str | None = None
    context_messages_used: int
    messages_saved: int
    summary_used: bool = False
    summary_updated: bool = False
    retrieval_used: bool = False
    retrieval_messages_used: int = 0
    retrieval_query: str | None = None
    sticky_facts_used: bool = False
    sticky_facts_updated: bool = False
    sticky_facts_count: int = 0



class ConversationSummaryInfo(BaseModel):
    summary: str
    source_upto_seq_no: int
    updated_at: str | None = None


class StickyFact(BaseModel):
    key: str
    value: str
    source: str = "llm"
    last_observed_seq_no: int | None = None
    updated_at: str | None = None


class MemoryContext(BaseModel):
    messages: list[ChatMessage]
    summary_used: bool = False
    retrieval_used: bool = False
    retrieval_messages_used: int = 0
    retrieval_query: str | None = None
    retrieved_items: list[RetrievedMemoryItem] = Field(default_factory=list)
    sticky_facts_used: bool = False
    sticky_facts_count: int = 0


# =========================
# Helpers
# =========================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_write_audit(payload: dict[str, Any]) -> None:
    audit_logger.info(json.dumps(payload, ensure_ascii=False))


@contextmanager
def get_db_connection() -> Iterator[psycopg.Connection]:
    with db_pool.connection() as conn:
        yield conn


def init_db() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
            except Exception as exc:
                logger.warning("Could not enable pgcrypto extension: %s", exc)
            if RETRIEVAL_USE_TRIGRAM:
                try:
                    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
                except Exception as exc:
                    logger.warning("Could not enable pg_trgm extension: %s", exc)
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    model TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    message_uuid TEXT UNIQUE,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    parent_message_uuid TEXT,
                    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
                    content TEXT NOT NULL,
                    seq_no INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    summary TEXT NOT NULL,
                    source_upto_seq_no INTEGER NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_facts (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    source TEXT NOT NULL DEFAULT 'llm',
                    last_observed_seq_no INTEGER,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id, key)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_branch_seq
                ON messages (conversation_id, branch_id, seq_no DESC)
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_branch_seq
                ON messages (conversation_id, branch_id, seq_no)
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_facts_updated
                ON conversation_facts (conversation_id, branch_id, updated_at DESC)
                                """
            )

            cur.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS message_uuid TEXT")
            cur.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS branch_id TEXT NOT NULL DEFAULT 'main'")
            cur.execute("ALTER TABLE messages ADD COLUMN IF NOT EXISTS parent_message_uuid TEXT")
            cur.execute("UPDATE messages SET message_uuid = gen_random_uuid()::text WHERE message_uuid IS NULL")
            cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_message_uuid ON messages (message_uuid)")
            cur.execute("ALTER TABLE conversation_summaries ADD COLUMN IF NOT EXISTS branch_id TEXT NOT NULL DEFAULT 'main'")
            cur.execute("ALTER TABLE conversation_facts ADD COLUMN IF NOT EXISTS branch_id TEXT NOT NULL DEFAULT 'main'")

            if RETRIEVAL_USE_TRIGRAM:
                try:
                    cur.execute(
                        """
                        CREATE INDEX IF NOT EXISTS idx_messages_content_trgm
                        ON messages USING gin (content gin_trgm_ops)
                        """
                    )
                except Exception as exc:
                    logger.warning("Could not create trigram index: %s", exc)
        conn.commit()




def ensure_branch_exists(conversation_id: str, branch_id: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT 1
                FROM messages
                WHERE conversation_id = %s AND branch_id = %s
                LIMIT 1
                """,
                (conversation_id, branch_id),
            )
            exists = cur.fetchone()
    if not exists and branch_id != "main":
        raise HTTPException(status_code=404, detail=f"branch '{branch_id}' not found")


def create_branch_mvp(
    conversation_id: str,
    new_branch_id: str,
    source_branch_id: str,
    fork_from_message_uuid: str,
) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT seq_no
                FROM messages
                WHERE conversation_id = %s
                  AND branch_id = %s
                  AND message_uuid = %s
                LIMIT 1
                """,
                (conversation_id, source_branch_id, fork_from_message_uuid),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(status_code=404, detail="fork_from_message_uuid not found in source branch")
            fork_seq_no = int(row[0])

            cur.execute(
                """
                SELECT 1
                FROM messages
                WHERE conversation_id = %s AND branch_id = %s
                LIMIT 1
                """,
                (conversation_id, new_branch_id),
            )
            if cur.fetchone():
                return 0

            cur.execute(
                """
                SELECT role, content, seq_no
                FROM messages
                WHERE conversation_id = %s
                  AND branch_id = %s
                  AND seq_no <= %s
                ORDER BY seq_no ASC
                """,
                (conversation_id, source_branch_id, fork_seq_no),
            )
            rows = cur.fetchall()
            for role, content, seq_no in rows:
                cur.execute(
                    """
                    INSERT INTO messages (message_uuid, conversation_id, branch_id, parent_message_uuid, role, content, seq_no)
                    VALUES (%s, %s, %s, NULL, %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), conversation_id, new_branch_id, role, content, seq_no),
                )
        conn.commit()
    return len(rows)


def list_conversation_branches(conversation_id: str) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT branch_id, COUNT(*), MIN(created_at), MAX(created_at)
                FROM messages
                WHERE conversation_id = %s
                GROUP BY branch_id
                ORDER BY branch_id ASC
                """,
                (conversation_id,),
            )
            rows = cur.fetchall()
    return [
        {
            "branch_id": row[0],
            "messages_count": int(row[1]),
            "created_at": row[2].replace(tzinfo=timezone.utc).isoformat() if row[2] else None,
            "updated_at": row[3].replace(tzinfo=timezone.utc).isoformat() if row[3] else None,
        }
        for row in rows
    ]

def ensure_conversation_exists(conversation_id: str, user_id: str | None, model: str) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, user_id, model)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (conversation_id, user_id, model),
            )
        conn.commit()


def get_recent_messages(conversation_id: str, branch_id: str, limit: int) -> list[ChatMessage]:
    if limit <= 0:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
                FROM (
                    SELECT role, content, seq_no
                    FROM messages
                    WHERE conversation_id = %s AND branch_id = %s
                    ORDER BY seq_no DESC
                    LIMIT %s
                ) AS recent
                ORDER BY seq_no ASC
                """,
                (conversation_id, branch_id, limit),
            )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]




def get_recent_messages_with_meta(conversation_id: str, branch_id: str, limit: int) -> list[dict[str, Any]]:
    if limit <= 0:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT message_uuid, role, content, seq_no, created_at
                FROM (
                    SELECT message_uuid, role, content, seq_no, created_at
                    FROM messages
                    WHERE conversation_id = %s AND branch_id = %s
                    ORDER BY seq_no DESC
                    LIMIT %s
                ) AS recent
                ORDER BY seq_no ASC
                """,
                (conversation_id, branch_id, limit),
            )
            rows = cur.fetchall()

    return [
        {
            "message_uuid": row[0],
            "role": row[1],
            "content": row[2],
            "seq_no": int(row[3]),
            "created_at": row[4].replace(tzinfo=timezone.utc).isoformat() if row[4] else None,
        }
        for row in rows
    ]

def get_messages_after_seq(
    conversation_id: str,
    branch_id: str,
    seq_no: int,
    limit: int | None = None,
) -> list[ChatMessage]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if limit is None:
                cur.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE conversation_id = %s AND branch_id = %s AND seq_no > %s
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, seq_no),
                )
            else:
                cur.execute(
                    """
                    SELECT role, content
                    FROM (
                        SELECT role, content, seq_no
                        FROM messages
                        WHERE conversation_id = %s AND branch_id = %s AND seq_no > %s
                        ORDER BY seq_no DESC
                        LIMIT %s
                    ) AS recent
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, seq_no, limit),
                )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]


def get_message_seq_nos_after_seq(
    conversation_id: str,
    branch_id: str,
    seq_no: int,
    limit: int | None = None,
) -> list[int]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if limit is None:
                cur.execute(
                    """
                    SELECT seq_no
                    FROM messages
                    WHERE conversation_id = %s AND branch_id = %s AND seq_no > %s
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, seq_no),
                )
            else:
                cur.execute(
                    """
                    SELECT seq_no
                    FROM (
                        SELECT seq_no
                        FROM messages
                        WHERE conversation_id = %s AND branch_id = %s AND seq_no > %s
                        ORDER BY seq_no DESC
                        LIMIT %s
                    ) AS recent
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, seq_no, limit),
                )
            rows = cur.fetchall()
    return [int(row[0]) for row in rows]


def get_messages_range(
    conversation_id: str,
    branch_id: str,
    start_seq_exclusive: int,
    end_seq_inclusive: int,
    limit: int | None = None,
) -> list[ChatMessage]:
    if end_seq_inclusive <= start_seq_exclusive:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            if limit is None:
                cur.execute(
                    """
                    SELECT role, content
                    FROM messages
                    WHERE conversation_id = %s
                      AND branch_id = %s
                      AND seq_no > %s
                      AND seq_no <= %s
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, start_seq_exclusive, end_seq_inclusive),
                )
            else:
                cur.execute(
                    """
                    SELECT role, content
                    FROM (
                        SELECT role, content, seq_no
                        FROM messages
                        WHERE conversation_id = %s
                          AND branch_id = %s
                          AND seq_no > %s
                          AND seq_no <= %s
                        ORDER BY seq_no DESC
                        LIMIT %s
                    ) AS bounded
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, branch_id, start_seq_exclusive, end_seq_inclusive, limit),
                )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]


def get_conversation_summary(conversation_id: str, branch_id: str) -> ConversationSummaryInfo | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary, source_upto_seq_no, updated_at
                FROM conversation_summaries
                WHERE conversation_id = %s AND branch_id = %s
                """,
                (conversation_id, branch_id),
            )
            row = cur.fetchone()

    if not row:
        return None

    updated_at = row[2].replace(tzinfo=timezone.utc).isoformat() if row[2] else None
    return ConversationSummaryInfo(
        summary=row[0],
        source_upto_seq_no=row[1],
        updated_at=updated_at,
    )


def upsert_conversation_summary(conversation_id: str, branch_id: str, summary: str, source_upto_seq_no: int) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_summaries (conversation_id, branch_id, summary, source_upto_seq_no, updated_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (conversation_id, branch_id)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    source_upto_seq_no = EXCLUDED.source_upto_seq_no,
                    updated_at = NOW()
                """,
                (conversation_id, branch_id, summary, source_upto_seq_no),
            )
        conn.commit()


def get_max_seq_no(conversation_id: str, branch_id: str) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(seq_no), 0) FROM messages WHERE conversation_id = %s AND branch_id = %s",
                (conversation_id, branch_id),
            )
            row = cur.fetchone()
    return int(row[0] or 0)


def get_unsummarized_message_count(conversation_id: str, branch_id: str, summary_upto_seq_no: int) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE conversation_id = %s AND branch_id = %s AND seq_no > %s
                """,
                (conversation_id, branch_id, summary_upto_seq_no),
            )
            row = cur.fetchone()
    return int(row[0] or 0)



def get_conversation_facts(conversation_id: str, branch_id: str, limit: int = STICKY_FACTS_MAX_ITEMS) -> list[StickyFact]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, value, source, last_observed_seq_no, updated_at
                FROM conversation_facts
                WHERE conversation_id = %s AND branch_id = %s
                ORDER BY updated_at DESC, key ASC
                LIMIT %s
                """,
                (conversation_id, branch_id, limit),
            )
            rows = cur.fetchall()

    facts: list[StickyFact] = []
    for row in rows:
        updated_at = row[4].replace(tzinfo=timezone.utc).isoformat() if row[4] else None
        facts.append(
            StickyFact(
                key=row[0],
                value=row[1],
                source=row[2] or "llm",
                last_observed_seq_no=row[3],
                updated_at=updated_at,
            )
        )
    return facts


def upsert_conversation_facts(
    conversation_id: str,
    branch_id: str,
    facts: list[StickyFact],
) -> int:
    if not facts:
        return 0

    upserted = 0
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for fact in facts:
                cur.execute(
                    """
                    INSERT INTO conversation_facts (
                        conversation_id,
                        branch_id,
                        key,
                        value,
                        source,
                        last_observed_seq_no,
                        updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (conversation_id, branch_id, key)
                    DO UPDATE SET
                        value = EXCLUDED.value,
                        source = EXCLUDED.source,
                        last_observed_seq_no = EXCLUDED.last_observed_seq_no,
                        updated_at = NOW()
                    """,
                    (
                        conversation_id,
                        branch_id,
                        fact.key,
                        fact.value,
                        fact.source,
                        fact.last_observed_seq_no,
                    ),
                )
                upserted += 1
        conn.commit()

    return upserted


def get_messages_for_fact_refresh(conversation_id: str, branch_id: str, limit: int) -> list[ChatMessage]:
    return get_recent_messages(conversation_id, branch_id, limit)


def extract_sticky_facts(
    *,
    messages: list[ChatMessage],
    model: str,
    user_id: str | None,
) -> list[StickyFact]:
    if not messages:
        return []

    conversation_dump = "\n\n".join(f"{message.role}: {message.content}" for message in messages)

    system_prompt = (
        "Извлеки только устойчивые факты для долговременной памяти ассистента. "
        "Факты должны быть полезны в следующих категориях: user_profile, preferences, goals, "
        "constraints, project, tech_stack, decisions. Не включай временные детали, шум, "
        "одноразовые вопросы и предположения. Возвращай только JSON вида "
        '{"facts":[{"key":"...", "value":"..."}]}. '
        "Ключи должны быть в snake_case, короткими и стабильными. Не более 12 фактов."
    )

    messages_for_extraction = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(
            role="user",
            content=(
                "Извлеки sticky facts из этих сообщений. Если устойчивых фактов нет, "
                'верни {"facts":[]}.\n\n'
                f"{conversation_dump}"
            ),
        ),
    ]

    facts_model = STICKY_FACTS_MODEL or model
    response = call_chat_completion(
        model=facts_model,
        messages=messages_for_extraction,
        temperature=0.1,
        max_tokens=STICKY_FACTS_MAX_TOKENS,
        top_p=1.0,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        stop=None,
        user_id=user_id,
    )
    content, _ = extract_text_from_chat_completion(response)
    if not content.strip():
        return []

    try:
        payload = json.loads(content)
    except Exception:
        logger.warning("Sticky facts extractor returned non-JSON payload")
        return []

    raw_facts = payload.get("facts", [])
    if not isinstance(raw_facts, list):
        return []

    allowed_prefixes = {
        "user_",
        "preference_",
        "goal_",
        "constraint_",
        "project_",
        "tech_",
        "decision_",
    }
    normalized: list[StickyFact] = []
    seen_keys: set[str] = set()
    for item in raw_facts[:12]:
        if not isinstance(item, dict):
            continue
        key = str(item.get("key", "")).strip().lower()
        value = " ".join(str(item.get("value", "")).split()).strip()
        if not key or not value:
            continue
        if len(key) > 64 or len(value) > 500:
            continue
        if not any(key.startswith(prefix) for prefix in allowed_prefixes):
            continue
        if key in seen_keys:
            continue
        seen_keys.add(key)
        normalized.append(StickyFact(key=key, value=value, source="llm"))

    return normalized


def maybe_refresh_sticky_facts(conversation_id: str, branch_id: str, model: str, user_id: str | None) -> int:
    if not STICKY_FACTS_ENABLED_BY_DEFAULT:
        return 0

    candidate_messages = get_messages_for_fact_refresh(
        conversation_id=conversation_id,
        branch_id=branch_id,
        limit=STICKY_FACTS_MAX_INPUT_MESSAGES,
    )
    if len(candidate_messages) < STICKY_FACTS_TRIGGER_MESSAGES:
        return 0

    facts = extract_sticky_facts(
        messages=candidate_messages,
        model=model,
        user_id=user_id,
    )
    if not facts:
        return 0

    last_seq_no = get_max_seq_no(conversation_id, branch_id)
    for fact in facts:
        fact.last_observed_seq_no = last_seq_no

    return upsert_conversation_facts(conversation_id=conversation_id, branch_id=branch_id, facts=facts)


def build_sticky_facts_system_message(facts: list[StickyFact]) -> ChatMessage | None:
    if not facts:
        return None

    lines = ["Ниже sticky facts из долговременной памяти. Считай их приоритетным стабильным контекстом:"]
    for fact in facts:
        lines.append(f"- {fact.key}: {fact.value}")
    return ChatMessage(role="system", content="\n".join(lines))


def save_messages_and_touch_conversation(
    conversation_id: str,
    branch_id: str,
    user_id: str | None,
    model: str,
    messages: list[ChatMessage],
) -> int:
    if not messages:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, user_id, model)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (conversation_id, user_id, model),
            )
            cur.execute(
                "SELECT id FROM conversations WHERE id = %s FOR UPDATE",
                (conversation_id,),
            )
            cur.execute(
                "SELECT COALESCE(MAX(seq_no), 0) FROM messages WHERE conversation_id = %s AND branch_id = %s",
                (conversation_id, branch_id),
            )
            current_seq = cur.fetchone()[0]

            for index, message in enumerate(messages, start=1):
                cur.execute(
                    """
                    INSERT INTO messages (message_uuid, conversation_id, branch_id, parent_message_uuid, role, content, seq_no)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                    """,
                    (str(uuid.uuid4()), conversation_id, branch_id, None, message.role, message.content, current_seq + index),
                )

            cur.execute(
                """
                UPDATE conversations
                SET updated_at = NOW(),
                    user_id = COALESCE(%s, user_id),
                    model = %s
                WHERE id = %s
                """,
                (user_id, model, conversation_id),
            )
        conn.commit()

    return len(messages)


def extract_text_from_chat_completion(resp: Any) -> tuple[str, str | None]:
    content_parts: list[str] = []
    finish_reason = None

    if not hasattr(resp, "choices") or not resp.choices:
        return "", None

    for choice in resp.choices:
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)

        if isinstance(message_content, str) and message_content:
            content_parts.append(message_content)
        elif isinstance(message_content, list):
            for part in message_content:
                if isinstance(part, dict) and part.get("type") == "text" and part.get("text"):
                    content_parts.append(str(part["text"]))
                else:
                    text_attr = getattr(part, "text", None)
                    if text_attr:
                        content_parts.append(str(text_attr))

        if finish_reason is None:
            finish_reason = getattr(choice, "finish_reason", None)

    return "\n".join(part for part in content_parts if part), finish_reason


def validate_output(text: str, rules: ResponseValidationRules | None) -> dict[str, Any]:
    result = {
        "ok": True,
        "errors": [],
    }

    if rules is None:
        return result

    length = len(text)

    if rules.min_output_length is not None and length < rules.min_output_length:
        result["ok"] = False
        result["errors"].append(
            f"Output too short: {length} < {rules.min_output_length}"
        )

    if rules.max_output_length is not None and length > rules.max_output_length:
        result["ok"] = False
        result["errors"].append(
            f"Output too long: {length} > {rules.max_output_length}"
        )

    lowered = text.lower()

    for phrase in rules.must_contain:
        if phrase.lower() not in lowered:
            result["ok"] = False
            result["errors"].append(f"Missing required phrase: {phrase}")

    for phrase in rules.forbid_phrases:
        if phrase.lower() in lowered:
            result["ok"] = False
            result["errors"].append(f"Forbidden phrase found: {phrase}")

    if rules.require_json:
        try:
            json.loads(text)
        except Exception:
            result["ok"] = False
            result["errors"].append("Output is not valid JSON")

    return result


def get_usage(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if not usage:
        return {}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


def call_chat_completion(
    *,
    model: str,
    messages: list[ChatMessage],
    temperature: float,
    max_tokens: int,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    stop: list[str] | None,
    user_id: str | None,
) -> Any:
    params: dict[str, Any] = {
        "model": model,
        "messages": [msg.model_dump() for msg in messages],
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "stop": stop,
        "user": user_id,
    }

    if "gpt-5" in model:
        params["max_completion_tokens"] = max_tokens
    else:
        params["max_tokens"] = max_tokens

    return client.chat.completions.create(**params)


def summarize_messages(
    *,
    messages: list[ChatMessage],
    model: str,
    user_id: str | None,
    existing_summary: str | None,
) -> str:
    conversation_dump = "\n\n".join(f"{message.role}: {message.content}" for message in messages)

    system_prompt = (
        "Сделай краткое и точное резюме диалога для последующего использования как памяти LLM. "
        "Сохраняй только факты, решения, цели пользователя, ограничения, предпочтения, важные сущности "
        "и открытые вопросы. Не выдумывай ничего от себя. Пиши компактно, но не теряй важные детали."
    )

    user_parts = []
    if existing_summary:
        user_parts.append("Текущее резюме памяти:\n" + existing_summary)
    user_parts.append("Новые сообщения для включения в память:\n" + conversation_dump)
    user_parts.append(
        "Верни обновлённое резюме в обычном тексте со структурой:\n"
        "- Цель\n- Важные факты\n- Решения\n- Ограничения и предпочтения\n- Открытые вопросы"
    )

    summary_messages = [
        ChatMessage(role="system", content=system_prompt),
        ChatMessage(role="user", content="\n\n".join(user_parts)),
    ]

    summary_model = SUMMARY_MODEL or model
    response = call_chat_completion(
        model=summary_model,
        messages=summary_messages,
        temperature=0.1,
        max_tokens=SUMMARY_MAX_TOKENS,
        top_p=1.0,
        presence_penalty=0.0,
        frequency_penalty=0.0,
        stop=None,
        user_id=user_id,
    )
    content, _ = extract_text_from_chat_completion(response)
    return content.strip()


def maybe_refresh_summary(conversation_id: str, branch_id: str, model: str, user_id: str | None) -> bool:
    current_summary = get_conversation_summary(conversation_id, branch_id)
    summary_upto_seq_no = current_summary.source_upto_seq_no if current_summary else 0
    unsummarized_count = get_unsummarized_message_count(conversation_id, branch_id, summary_upto_seq_no)

    if unsummarized_count < SUMMARY_TRIGGER_MESSAGES:
        return False

    max_seq_no = get_max_seq_no(conversation_id, branch_id)
    new_summary_upto_seq_no = max_seq_no - SUMMARY_KEEP_LAST_MESSAGES
    if new_summary_upto_seq_no <= summary_upto_seq_no:
        return False

    messages_to_summarize = get_messages_range(
        conversation_id=conversation_id,
        branch_id=branch_id,
        start_seq_exclusive=summary_upto_seq_no,
        end_seq_inclusive=new_summary_upto_seq_no,
        limit=SUMMARY_MAX_INPUT_MESSAGES,
    )
    if not messages_to_summarize:
        return False

    summary_text = summarize_messages(
        messages=messages_to_summarize,
        model=model,
        user_id=user_id,
        existing_summary=current_summary.summary if current_summary else None,
    )
    if not summary_text:
        logger.warning(
            "Summary refresh skipped because summarizer returned empty text conversation_id=%s",
            conversation_id,
        )
        return False

    upsert_conversation_summary(
        conversation_id=conversation_id,
        branch_id=branch_id,
        summary=summary_text,
        source_upto_seq_no=new_summary_upto_seq_no,
    )
    logger.info(
        "Conversation summary refreshed conversation_id=%s source_upto_seq_no=%s",
        conversation_id,
        new_summary_upto_seq_no,
    )
    return True


def extract_retrieval_query(messages: list[ChatMessage]) -> str:
    parts: list[str] = []
    for message in messages:
        if message.role == "user":
            text = " ".join(message.content.split())
            if text:
                parts.append(text)
    return "\n".join(parts).strip()


def truncate_for_memory(text: str, max_chars: int = RETRIEVAL_MAX_CONTENT_CHARS) -> str:
    text = " ".join(text.split())
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 1].rstrip() + "…"


def retrieve_relevant_messages(
    *,
    conversation_id: str,
    branch_id: str,
    query: str,
    summary_upto_seq_no: int,
    excluded_seq_nos: set[int],
    limit: int,
) -> list[RetrievedMemoryItem]:
    normalized_query = " ".join(query.split()).strip()
    if limit <= 0 or len(normalized_query) < RETRIEVAL_MIN_QUERY_CHARS:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            try:
                if RETRIEVAL_USE_TRIGRAM:
                    cur.execute(
                        """
                        SELECT seq_no,
                               role,
                               content,
                               similarity(content, %s) AS score
                        FROM messages
                        WHERE conversation_id = %s
                          AND branch_id = %s
                          AND seq_no <= %s
                          AND char_length(content) >= 20
                        ORDER BY score DESC, seq_no DESC
                        LIMIT %s
                        """,
                        (normalized_query, conversation_id, branch_id, summary_upto_seq_no, RETRIEVAL_CANDIDATE_POOL),
                    )
                else:
                    raise RuntimeError("Trigram retrieval disabled")
            except Exception:
                fallback_pattern = f"%{normalized_query[:100]}%"
                cur.execute(
                    """
                    SELECT seq_no,
                           role,
                           content,
                           CASE WHEN content ILIKE %s THEN 1.0 ELSE 0.0 END AS score
                    FROM messages
                    WHERE conversation_id = %s
                      AND branch_id = %s
                      AND seq_no <= %s
                      AND char_length(content) >= 20
                    ORDER BY score DESC, seq_no DESC
                    LIMIT %s
                    """,
                    (fallback_pattern, conversation_id, branch_id, summary_upto_seq_no, RETRIEVAL_CANDIDATE_POOL),
                )

            rows = cur.fetchall()

    items: list[RetrievedMemoryItem] = []
    seen_signatures: set[tuple[str, str]] = set()
    for seq_no, role, content, score in rows:
        seq_no = int(seq_no)
        numeric_score = float(score or 0.0)
        if seq_no in excluded_seq_nos:
            continue
        if numeric_score < RETRIEVAL_MIN_SCORE:
            continue
        compact = truncate_for_memory(content)
        signature = (role, compact)
        if signature in seen_signatures:
            continue
        seen_signatures.add(signature)
        items.append(
            RetrievedMemoryItem(
                seq_no=seq_no,
                role=role,
                score=round(numeric_score, 4),
                content=compact,
            )
        )
        if len(items) >= limit:
            break

    items.sort(key=lambda item: item.seq_no)
    return items


def build_retrieval_memory_system_message(items: list[RetrievedMemoryItem]) -> ChatMessage | None:
    if not items:
        return None

    lines = [
        "Ниже извлечены релевантные фрагменты из более старой истории диалога. ",
        "Используй их только если они действительно помогают ответить на текущий запрос. ",
        "Если они конфликтуют с более свежими сообщениями, доверяй более свежему контексту.",
        "",
    ]
    for item in items:
        lines.append(f"- seq={item.seq_no} role={item.role} score={item.score}: {item.content}")
    return ChatMessage(role="system", content="\n".join(lines))


def build_context_messages(
    conversation_id: str,
    branch_id: str,
    history_limit: int,
    retrieval_enabled: bool,
    retrieval_limit: int,
    sticky_facts_enabled: bool,
    live_messages: list[ChatMessage],
    memory_strategy: MemoryStrategy,
) -> MemoryContext:
    if memory_strategy == "none":
        return MemoryContext(messages=[])

    summary_info = get_conversation_summary(conversation_id, branch_id)
    context_messages: list[ChatMessage] = []
    summary_used = False
    retrieval_used = False
    retrieval_query: str | None = None
    retrieved_items: list[RetrievedMemoryItem] = []
    sticky_facts: list[StickyFact] = []
    sticky_facts_used = False

    use_window = memory_strategy in {"window", "hybrid", "facts", "hybrid_facts"}
    use_summary = memory_strategy in {"summary", "hybrid", "hybrid_facts"}
    use_retrieval = memory_strategy in {"retrieval", "hybrid", "hybrid_facts"} and retrieval_enabled
    use_sticky_facts = memory_strategy in {"facts", "hybrid_facts"} and sticky_facts_enabled

    summary_upto_seq_no = summary_info.source_upto_seq_no if summary_info else 0

    if use_sticky_facts:
        sticky_facts = get_conversation_facts(conversation_id, branch_id)
        sticky_facts_message = build_sticky_facts_system_message(sticky_facts)
        if sticky_facts_message:
            context_messages.append(sticky_facts_message)
            sticky_facts_used = True

    if use_summary and summary_info:
        context_messages.append(
            ChatMessage(
                role="system",
                content=(
                    "Ниже краткое резюме предыдущего диалога. Используй его как долговременный контекст."


                    f"{summary_info.summary}"
                ),
            )
        )
        summary_used = True

    if use_retrieval:
        retrieval_query = extract_retrieval_query(live_messages)
        excluded_seq_nos: set[int] = set()

        if use_window and history_limit > 0:
            if summary_info:
                excluded_seq_nos = set(
                    get_message_seq_nos_after_seq(
                        conversation_id=conversation_id,
                        branch_id=branch_id,
                        seq_no=summary_info.source_upto_seq_no,
                        limit=history_limit,
                    )
                )
            else:
                max_seq_no = get_max_seq_no(conversation_id, branch_id)
                window_start_seq_no = max(0, max_seq_no - history_limit)
                excluded_seq_nos = set(
                    range(window_start_seq_no + 1, max_seq_no + 1)
                )

        retrieval_end_seq_no = summary_upto_seq_no if summary_info else get_max_seq_no(conversation_id, branch_id)

        if retrieval_query:
            retrieved_items = retrieve_relevant_messages(
                conversation_id=conversation_id,
                branch_id=branch_id,
                query=retrieval_query,
                summary_upto_seq_no=retrieval_end_seq_no,
                excluded_seq_nos=excluded_seq_nos,
                limit=retrieval_limit,
            )
            retrieval_message = build_retrieval_memory_system_message(retrieved_items)
            if retrieval_message:
                retrieval_used = True
                context_messages.append(retrieval_message)

    if use_window and history_limit > 0:
        if summary_info:
            recent_messages = get_messages_after_seq(
                conversation_id=conversation_id,
                branch_id=branch_id,
                seq_no=summary_info.source_upto_seq_no,
                limit=history_limit,
            )
        else:
            recent_messages = get_recent_messages(conversation_id, branch_id, history_limit)
        context_messages.extend(recent_messages)

    return MemoryContext(
        messages=context_messages,
        summary_used=summary_used,
        retrieval_used=retrieval_used,
        retrieval_messages_used=len(retrieved_items),
        retrieval_query=retrieval_query if retrieval_used else None,
        retrieved_items=retrieved_items,
        sticky_facts_used=sticky_facts_used,
        sticky_facts_count=len(sticky_facts),
    )


# =========================
# Middleware
# =========================
@app.middleware("http")
async def request_log_middleware(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get("X-Request-ID", str(uuid.uuid4()))

    try:
        response = await call_next(request)
        latency_ms = int((time.perf_counter() - started) * 1000)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Latency-Ms"] = str(latency_ms)

        logger.info(
            f"{request.method} {request.url.path} status={response.status_code} "
            f"request_id={request_id} latency_ms={latency_ms}"
        )
        return response

    except (HTTPException, StarletteHTTPException):
        raise

    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)
        logger.exception(
            f"Unhandled error {request.method} {request.url.path} "
            f"request_id={request_id} latency_ms={latency_ms}: {exc}"
        )
        return JSONResponse(
            status_code=500,
            content={
                "error": "internal_server_error",
                "message": "Internal server error",
                "request_id": request_id,
                "latency_ms": latency_ms,
            },
        )


# =========================
# Routes
# =========================
@app.get("/health")
def health() -> dict[str, Any]:
    db_ok = True
    db_error = None
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
    except Exception as exc:
        db_ok = False
        db_error = str(exc)

    return {
        "status": "ok" if db_ok else "degraded",
        "service": "llm-gateway",
        "base_url": PROXYAPI_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
        "retrieval_enabled_by_default": RETRIEVAL_ENABLED_BY_DEFAULT,
        "time": utc_now_iso(),
    }


@app.post("/generate", response_model=LLMResponse)
def generate(payload: LLMRequest) -> LLMResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    conversation_id = payload.conversation_id or str(uuid.uuid4())
    branch_id = payload.branch_id.strip() or "main"
    source_branch_id = (payload.fork_from_branch_id or branch_id).strip() or "main"

    request_snapshot = {
        "request_id": request_id,
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "fork_from_branch_id": payload.fork_from_branch_id,
        "fork_from_message_uuid": payload.fork_from_message_uuid,
        "created_at": utc_now_iso(),
        "model": payload.model,
        "temperature": payload.temperature,
        "max_tokens": payload.max_tokens,
        "top_p": payload.top_p,
        "presence_penalty": payload.presence_penalty,
        "frequency_penalty": payload.frequency_penalty,
        "stop": payload.stop,
        "user_id": payload.user_id,
        "metadata": payload.metadata,
        "messages_count": len(payload.messages),
        "use_memory": payload.use_memory,
        "memory_strategy": payload.memory_strategy,
        "history_limit": payload.history_limit,
        "retrieval_enabled": payload.retrieval_enabled,
        "retrieval_limit": payload.retrieval_limit,
        "sticky_facts_enabled": payload.sticky_facts_enabled,
    }

    logger.info(
        f"LLM request started request_id={request_id} "
        f"conversation_id={conversation_id} branch_id={branch_id} model={payload.model} "
        f"messages={len(payload.messages)} use_memory={payload.use_memory} "
        f"memory_strategy={payload.memory_strategy} "
        f"retrieval_enabled={payload.retrieval_enabled} "
        f"sticky_facts_enabled={payload.sticky_facts_enabled}"
    )

    try:
        ensure_conversation_exists(conversation_id, payload.user_id, payload.model)

        if payload.fork_from_message_uuid:
            copied = create_branch_mvp(
                conversation_id=conversation_id,
                new_branch_id=branch_id,
                source_branch_id=source_branch_id,
                fork_from_message_uuid=payload.fork_from_message_uuid,
            )
            logger.info(
                "Branch created conversation_id=%s branch_id=%s source_branch_id=%s copied_messages=%s",
                conversation_id,
                branch_id,
                source_branch_id,
                copied,
            )
        elif branch_id != "main":
            ensure_branch_exists(conversation_id, branch_id)

        memory_context = MemoryContext(messages=[])
        if payload.use_memory and payload.memory_strategy != "none":
            memory_context = build_context_messages(
                conversation_id=conversation_id,
                branch_id=branch_id,
                history_limit=payload.history_limit,
                retrieval_enabled=payload.retrieval_enabled,
                retrieval_limit=payload.retrieval_limit,
                sticky_facts_enabled=payload.sticky_facts_enabled,
                live_messages=payload.messages,
                memory_strategy=payload.memory_strategy,
            )

        full_messages = [*memory_context.messages, *payload.messages]
        response = call_chat_completion(
            model=payload.model,
            messages=full_messages,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            top_p=payload.top_p,
            presence_penalty=payload.presence_penalty,
            frequency_penalty=payload.frequency_penalty,
            stop=payload.stop,
            user_id=payload.user_id,
        )

        latency_ms = int((time.perf_counter() - started) * 1000)
        content, finish_reason = extract_text_from_chat_completion(response)

        if not content.strip():
            raise HTTPException(
                status_code=502,
                detail={
                    "error": "empty_model_response",
                    "message": "Upstream model returned empty content",
                    "request_id": request_id,
                    "conversation_id": conversation_id,
                    "branch_id": branch_id,
                    "latency_ms": latency_ms,
                },
            )

        validation_result = validate_output(content, payload.validation)
        usage = get_usage(response)

        messages_to_save = [*payload.messages, ChatMessage(role="assistant", content=content)]
        messages_saved = save_messages_and_touch_conversation(
            conversation_id=conversation_id,
            branch_id=branch_id,
            user_id=payload.user_id,
            model=payload.model,
            messages=messages_to_save,
        )

        summary_updated = False
        sticky_facts_updated = False
        sticky_facts_count = memory_context.sticky_facts_count
        if payload.use_memory and payload.memory_strategy in {"summary", "hybrid", "hybrid_facts"}:
            try:
                summary_updated = maybe_refresh_summary(
                    conversation_id=conversation_id,
                    branch_id=branch_id,
                    model=payload.model,
                    user_id=payload.user_id,
                )
            except Exception as summary_exc:
                logger.exception(
                    "Summary refresh failed conversation_id=%s branch_id=%s: %s",
                    conversation_id,
                    branch_id,
                    summary_exc,
                )
                safe_write_audit(
                    {
                        "type": "summary_refresh_error",
                        "conversation_id": conversation_id,
                        "branch_id": branch_id,
                        "message": str(summary_exc),
                    }
                )

        if payload.use_memory and payload.sticky_facts_enabled and payload.memory_strategy in {"facts", "hybrid_facts"}:
            try:
                sticky_upserted = maybe_refresh_sticky_facts(
                    conversation_id=conversation_id,
                    branch_id=branch_id,
                    model=payload.model,
                    user_id=payload.user_id,
                )
                sticky_facts_updated = sticky_upserted > 0
                sticky_facts_count = len(get_conversation_facts(conversation_id, branch_id))
            except Exception as facts_exc:
                logger.exception(
                    "Sticky facts refresh failed conversation_id=%s branch_id=%s: %s",
                    conversation_id,
                    branch_id,
                    facts_exc,
                )
                safe_write_audit(
                    {
                        "type": "sticky_facts_refresh_error",
                        "conversation_id": conversation_id,
                        "branch_id": branch_id,
                        "message": str(facts_exc),
                    }
                )

        result = LLMResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            branch_id=branch_id,
            created_at=utc_now_iso(),
            model=payload.model,
            content=content,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            usage=usage,
            validation=validation_result,
            raw_response_id=getattr(response, "id", None),
            context_messages_used=len(memory_context.messages),
            messages_saved=messages_saved,
            summary_used=memory_context.summary_used,
            summary_updated=summary_updated,
            retrieval_used=memory_context.retrieval_used,
            retrieval_messages_used=memory_context.retrieval_messages_used,
            retrieval_query=memory_context.retrieval_query,
            sticky_facts_used=memory_context.sticky_facts_used,
            sticky_facts_updated=sticky_facts_updated,
            sticky_facts_count=sticky_facts_count,
        )

        safe_write_audit(
            {
                "type": "llm_call",
                "request": request_snapshot,
                "response": {
                    "raw_response_id": getattr(response, "id", None),
                    "finish_reason": finish_reason,
                    "latency_ms": latency_ms,
                    "usage": usage,
                    "validation": validation_result,
                    "context_messages_used": len(memory_context.messages),
                    "messages_saved": messages_saved,
                    "summary_used": memory_context.summary_used,
                    "summary_updated": summary_updated,
                    "retrieval_used": memory_context.retrieval_used,
                    "retrieval_messages_used": memory_context.retrieval_messages_used,
                    "retrieval_query": memory_context.retrieval_query,
                    "retrieved_items": [item.model_dump() for item in memory_context.retrieved_items],
                    "content_preview": content[:1000],
                },
            }
        )

        logger.info(
            f"LLM request completed request_id={request_id} "
            f"conversation_id={conversation_id} branch_id={branch_id} model={payload.model} "
            f"latency_ms={latency_ms} finish_reason={finish_reason} "
            f"retrieval_used={memory_context.retrieval_used}"
        )

        return result

    except Exception as exc:
        latency_ms = int((time.perf_counter() - started) * 1000)

        safe_write_audit(
            {
                "type": "llm_call_error",
                "request": request_snapshot,
                "error": {
                    "message": str(exc),
                    "latency_ms": latency_ms,
                },
            }
        )

        logger.exception(
            f"LLM request failed request_id={request_id} "
            f"conversation_id={conversation_id} branch_id={branch_id} model={payload.model} "
            f"latency_ms={latency_ms}: {exc}"
        )

        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_llm_error",
                "message": str(exc),
                "request_id": request_id,
                "conversation_id": conversation_id,
                "branch_id": branch_id,
                "latency_ms": latency_ms,
            },
        )


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, branch_id: str = "main", limit: int = DEFAULT_HISTORY_LIMIT) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    messages = get_recent_messages_with_meta(conversation_id, branch_id, limit)
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "messages": messages,
        "count": len(messages),
    }


@app.get("/conversations/{conversation_id}/summary")
def get_conversation_summary_route(conversation_id: str, branch_id: str = "main") -> dict[str, Any]:
    summary_info = get_conversation_summary(conversation_id, branch_id)
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "summary": summary_info.summary if summary_info else None,
        "source_upto_seq_no": summary_info.source_upto_seq_no if summary_info else 0,
        "updated_at": summary_info.updated_at if summary_info else None,
        "exists": summary_info is not None,
    }



@app.get("/conversations/{conversation_id}/facts")
def get_conversation_facts_route(conversation_id: str, branch_id: str = "main") -> dict[str, Any]:
    facts = get_conversation_facts(conversation_id, branch_id)
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "facts": [fact.model_dump() for fact in facts],
        "count": len(facts),
    }


@app.post("/conversations/{conversation_id}/facts/refresh")
def refresh_conversation_facts_route(
    conversation_id: str,
    branch_id: str = "main",
    model: str = DEFAULT_MODEL,
    user_id: str | None = None,
) -> dict[str, Any]:
    ensure_conversation_exists(conversation_id, user_id, model)
    upserted = maybe_refresh_sticky_facts(conversation_id=conversation_id, branch_id=branch_id, model=model, user_id=user_id)
    facts = get_conversation_facts(conversation_id, branch_id)
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "updated": upserted > 0,
        "upserted": upserted,
        "facts": [fact.model_dump() for fact in facts],
        "count": len(facts),
    }


@app.post("/conversations/{conversation_id}/summary/refresh")
def refresh_conversation_summary_route(
    conversation_id: str,
    branch_id: str = "main",
    model: str = DEFAULT_MODEL,
    user_id: str | None = None,
) -> dict[str, Any]:
    ensure_conversation_exists(conversation_id, user_id, model)
    updated = maybe_refresh_summary(conversation_id=conversation_id, branch_id=branch_id, model=model, user_id=user_id)
    summary_info = get_conversation_summary(conversation_id, branch_id)
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "updated": updated,
        "summary": summary_info.summary if summary_info else None,
        "source_upto_seq_no": summary_info.source_upto_seq_no if summary_info else 0,
        "updated_at": summary_info.updated_at if summary_info else None,
    }


@app.get("/conversations/{conversation_id}/branches")
def get_conversation_branches_route(conversation_id: str) -> dict[str, Any]:
    branches = list_conversation_branches(conversation_id)
    return {
        "conversation_id": conversation_id,
        "branches": branches,
        "count": len(branches),
    }


@app.post("/conversations/{conversation_id}/branches")
def create_conversation_branch_route(
    conversation_id: str,
    branch_id: str,
    fork_from_message_uuid: str,
    source_branch_id: str = "main",
) -> dict[str, Any]:
    copied = create_branch_mvp(
        conversation_id=conversation_id,
        new_branch_id=branch_id,
        source_branch_id=source_branch_id,
        fork_from_message_uuid=fork_from_message_uuid,
    )
    return {
        "conversation_id": conversation_id,
        "branch_id": branch_id,
        "source_branch_id": source_branch_id,
        "fork_from_message_uuid": fork_from_message_uuid,
        "created": copied > 0,
        "copied_messages": copied,
    }


@app.get("/models")
def list_models() -> dict[str, Any]:
    try:
        result = client.models.list()
        data = []
        for item in result.data:
            data.append(
                {
                    "id": getattr(item, "id", None),
                    "created": getattr(item, "created", None),
                    "object": getattr(item, "object", None),
                    "owned_by": getattr(item, "owned_by", None),
                }
            )
        return {"data": data}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc))


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app:app", host=APP_HOST, port=APP_PORT, reload=True)
