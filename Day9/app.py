import json
import logging
import os
import time
import uuid
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator, Literal

import psycopg
from psycopg_pool import ConnectionPool
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from starlette.exceptions import HTTPException as StarletteHTTPException
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

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
    version="1.2.0",
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
    use_memory: bool = True
    history_limit: int = Field(default=DEFAULT_HISTORY_LIMIT, ge=0, le=MAX_HISTORY_LIMIT)
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


class LLMResponse(BaseModel):
    request_id: str
    conversation_id: str
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


class ConversationSummaryInfo(BaseModel):
    summary: str
    source_upto_seq_no: int
    updated_at: str | None = None


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
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
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
                    conversation_id TEXT PRIMARY KEY REFERENCES conversations(id) ON DELETE CASCADE,
                    summary TEXT NOT NULL,
                    source_upto_seq_no INTEGER NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_seq
                ON messages (conversation_id, seq_no DESC)
                """
            )
            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_seq
                ON messages (conversation_id, seq_no)
                """
            )
        conn.commit()


@asynccontextmanager


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


def get_recent_messages(conversation_id: str, limit: int) -> list[ChatMessage]:
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
                    WHERE conversation_id = %s
                    ORDER BY seq_no DESC
                    LIMIT %s
                ) AS recent
                ORDER BY seq_no ASC
                """,
                (conversation_id, limit),
            )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]


def get_messages_after_seq(
    conversation_id: str,
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
                    WHERE conversation_id = %s AND seq_no > %s
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, seq_no),
                )
            else:
                cur.execute(
                    """
                    SELECT role, content
                    FROM (
                        SELECT role, content, seq_no
                        FROM messages
                        WHERE conversation_id = %s AND seq_no > %s
                        ORDER BY seq_no DESC
                        LIMIT %s
                    ) AS recent
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, seq_no, limit),
                )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]


def get_messages_range(
    conversation_id: str,
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
                      AND seq_no > %s
                      AND seq_no <= %s
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, start_seq_exclusive, end_seq_inclusive),
                )
            else:
                cur.execute(
                    """
                    SELECT role, content
                    FROM (
                        SELECT role, content, seq_no
                        FROM messages
                        WHERE conversation_id = %s
                          AND seq_no > %s
                          AND seq_no <= %s
                        ORDER BY seq_no DESC
                        LIMIT %s
                    ) AS bounded
                    ORDER BY seq_no ASC
                    """,
                    (conversation_id, start_seq_exclusive, end_seq_inclusive, limit),
                )
            rows = cur.fetchall()

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]


def get_conversation_summary(conversation_id: str) -> ConversationSummaryInfo | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary, source_upto_seq_no, updated_at
                FROM conversation_summaries
                WHERE conversation_id = %s
                """,
                (conversation_id,),
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


def upsert_conversation_summary(conversation_id: str, summary: str, source_upto_seq_no: int) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_summaries (conversation_id, summary, source_upto_seq_no, updated_at)
                VALUES (%s, %s, %s, NOW())
                ON CONFLICT (conversation_id)
                DO UPDATE SET
                    summary = EXCLUDED.summary,
                    source_upto_seq_no = EXCLUDED.source_upto_seq_no,
                    updated_at = NOW()
                """,
                (conversation_id, summary, source_upto_seq_no),
            )
        conn.commit()


def get_max_seq_no(conversation_id: str) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT COALESCE(MAX(seq_no), 0) FROM messages WHERE conversation_id = %s",
                (conversation_id,),
            )
            row = cur.fetchone()
    return int(row[0] or 0)


def get_unsummarized_message_count(conversation_id: str, summary_upto_seq_no: int) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*)
                FROM messages
                WHERE conversation_id = %s AND seq_no > %s
                """,
                (conversation_id, summary_upto_seq_no),
            )
            row = cur.fetchone()
    return int(row[0] or 0)


def save_messages_and_touch_conversation(
    conversation_id: str,
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
                "SELECT COALESCE(MAX(seq_no), 0) FROM messages WHERE conversation_id = %s",
                (conversation_id,),
            )
            current_seq = cur.fetchone()[0]

            for index, message in enumerate(messages, start=1):
                cur.execute(
                    """
                    INSERT INTO messages (conversation_id, role, content, seq_no)
                    VALUES (%s, %s, %s, %s)
                    """,
                    (conversation_id, message.role, message.content, current_seq + index),
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


def maybe_refresh_summary(conversation_id: str, model: str, user_id: str | None) -> bool:
    current_summary = get_conversation_summary(conversation_id)
    summary_upto_seq_no = current_summary.source_upto_seq_no if current_summary else 0
    unsummarized_count = get_unsummarized_message_count(conversation_id, summary_upto_seq_no)

    if unsummarized_count < SUMMARY_TRIGGER_MESSAGES:
        return False

    max_seq_no = get_max_seq_no(conversation_id)
    new_summary_upto_seq_no = max_seq_no - SUMMARY_KEEP_LAST_MESSAGES
    if new_summary_upto_seq_no <= summary_upto_seq_no:
        return False

    messages_to_summarize = get_messages_range(
        conversation_id=conversation_id,
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
        summary=summary_text,
        source_upto_seq_no=new_summary_upto_seq_no,
    )
    logger.info(
        "Conversation summary refreshed conversation_id=%s source_upto_seq_no=%s",
        conversation_id,
        new_summary_upto_seq_no,
    )
    return True


def build_context_messages(
    conversation_id: str,
    history_limit: int,
) -> tuple[list[ChatMessage], bool]:
    summary_info = get_conversation_summary(conversation_id)
    context_messages: list[ChatMessage] = []
    summary_used = False

    if summary_info:
        context_messages.append(
            ChatMessage(
                role="system",
                content=(
                    "Ниже краткое резюме предыдущего диалога. Используй его как долговременный контекст.\n\n"
                    f"{summary_info.summary}"
                ),
            )
        )
        summary_used = True
        recent_messages = get_messages_after_seq(
            conversation_id=conversation_id,
            seq_no=summary_info.source_upto_seq_no,
            limit=history_limit,
        )
    else:
        recent_messages = get_recent_messages(conversation_id, history_limit)

    context_messages.extend(recent_messages)
    return context_messages, summary_used


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
        "time": utc_now_iso(),
    }


@app.post("/generate", response_model=LLMResponse)
def generate(payload: LLMRequest) -> LLMResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()
    conversation_id = payload.conversation_id or str(uuid.uuid4())

    request_snapshot = {
        "request_id": request_id,
        "conversation_id": conversation_id,
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
        "history_limit": payload.history_limit,
    }

    logger.info(
        f"LLM request started request_id={request_id} "
        f"conversation_id={conversation_id} model={payload.model} "
        f"messages={len(payload.messages)} use_memory={payload.use_memory}"
    )

    try:
        ensure_conversation_exists(conversation_id, payload.user_id, payload.model)

        stored_messages: list[ChatMessage] = []
        summary_used = False
        if payload.use_memory:
            stored_messages, summary_used = build_context_messages(
                conversation_id=conversation_id,
                history_limit=payload.history_limit,
            )

        full_messages = [*stored_messages, *payload.messages]
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
                    "latency_ms": latency_ms,
                },
            )

        validation_result = validate_output(content, payload.validation)
        usage = get_usage(response)

        messages_to_save = [*payload.messages, ChatMessage(role="assistant", content=content)]
        messages_saved = save_messages_and_touch_conversation(
            conversation_id=conversation_id,
            user_id=payload.user_id,
            model=payload.model,
            messages=messages_to_save,
        )

        summary_updated = False
        if payload.use_memory:
            try:
                summary_updated = maybe_refresh_summary(
                    conversation_id=conversation_id,
                    model=payload.model,
                    user_id=payload.user_id,
                )
            except Exception as summary_exc:
                logger.exception(
                    "Summary refresh failed conversation_id=%s: %s",
                    conversation_id,
                    summary_exc,
                )
                safe_write_audit(
                    {
                        "type": "summary_refresh_error",
                        "conversation_id": conversation_id,
                        "message": str(summary_exc),
                    }
                )

        result = LLMResponse(
            request_id=request_id,
            conversation_id=conversation_id,
            created_at=utc_now_iso(),
            model=payload.model,
            content=content,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            usage=usage,
            validation=validation_result,
            raw_response_id=getattr(response, "id", None),
            context_messages_used=len(stored_messages),
            messages_saved=messages_saved,
            summary_used=summary_used,
            summary_updated=summary_updated,
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
                    "context_messages_used": len(stored_messages),
                    "messages_saved": messages_saved,
                    "summary_used": summary_used,
                    "summary_updated": summary_updated,
                    "content_preview": content[:1000],
                },
            }
        )

        logger.info(
            f"LLM request completed request_id={request_id} "
            f"conversation_id={conversation_id} model={payload.model} "
            f"latency_ms={latency_ms} finish_reason={finish_reason}"
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
            f"conversation_id={conversation_id} model={payload.model} "
            f"latency_ms={latency_ms}: {exc}"
        )

        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_llm_error",
                "message": str(exc),
                "request_id": request_id,
                "conversation_id": conversation_id,
                "latency_ms": latency_ms,
            },
        )


@app.get("/conversations/{conversation_id}/messages")
def get_conversation_messages(conversation_id: str, limit: int = DEFAULT_HISTORY_LIMIT) -> dict[str, Any]:
    limit = max(1, min(limit, MAX_HISTORY_LIMIT))
    messages = get_recent_messages(conversation_id, limit)
    return {
        "conversation_id": conversation_id,
        "messages": [message.model_dump() for message in messages],
        "count": len(messages),
    }


@app.get("/conversations/{conversation_id}/summary")
def get_conversation_summary_route(conversation_id: str) -> dict[str, Any]:
    summary_info = get_conversation_summary(conversation_id)
    return {
        "conversation_id": conversation_id,
        "summary": summary_info.summary if summary_info else None,
        "source_upto_seq_no": summary_info.source_upto_seq_no if summary_info else 0,
        "updated_at": summary_info.updated_at if summary_info else None,
        "exists": summary_info is not None,
    }


@app.post("/conversations/{conversation_id}/summary/refresh")
def refresh_conversation_summary_route(
    conversation_id: str,
    model: str = DEFAULT_MODEL,
    user_id: str | None = None,
) -> dict[str, Any]:
    ensure_conversation_exists(conversation_id, user_id, model)
    updated = maybe_refresh_summary(conversation_id=conversation_id, model=model, user_id=user_id)
    summary_info = get_conversation_summary(conversation_id)
    return {
        "conversation_id": conversation_id,
        "updated": updated,
        "summary": summary_info.summary if summary_info else None,
        "source_upto_seq_no": summary_info.source_upto_seq_no if summary_info else 0,
        "updated_at": summary_info.updated_at if summary_info else None,
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
