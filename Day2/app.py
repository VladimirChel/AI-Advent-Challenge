import json
import logging
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from openai import OpenAI
from pydantic import BaseModel, Field, field_validator

load_dotenv()


# =========================
# Config
# =========================
PROXYAPI_API_KEY = os.getenv("PROXYAPI_API_KEY", "").strip()
PROXYAPI_BASE_URL = os.getenv("PROXYAPI_BASE_URL", "https://openai.api.proxyapi.ru/v1").strip()

APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8000"))
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini").strip()
REQUEST_TIMEOUT_SECONDS = int(os.getenv("REQUEST_TIMEOUT_SECONDS", "60"))
MAX_TEMPERATURE = float(os.getenv("MAX_TEMPERATURE", "1.2"))
MAX_MAX_TOKENS = int(os.getenv("MAX_MAX_TOKENS", "4000"))
LOG_DIR = Path(os.getenv("LOG_DIR", "logs"))

if not PROXYAPI_API_KEY:
    raise RuntimeError("Environment variable PROXYAPI_API_KEY is required")

LOG_DIR.mkdir(parents=True, exist_ok=True)

# =========================
# Logging
# =========================
logger = logging.getLogger("llm_gateway")
logger.setLevel(logging.INFO)

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
# FastAPI
# =========================
app = FastAPI(
    title="LLM Gateway via ProxyAPI",
    version="1.0.0",
    description="Прокси-приложение для контролируемых запросов к LLM через ProxyAPI",
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
    temperature: float = Field(default=0.2, ge=0.0)
    max_tokens: int = Field(default=500, ge=1)
    top_p: float = Field(default=1.0, ge=0.0, le=1.0)
    presence_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    frequency_penalty: float = Field(default=0.0, ge=-2.0, le=2.0)
    user_id: str | None = Field(default=None, max_length=200)
    metadata: dict[str, Any] = Field(default_factory=dict)
    validation: ResponseValidationRules | None = None
    stop: list[str] | None = Field(default=None, max_length=16)    

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
        # ProxyAPI OpenAI-compatible format: provider/model
        if "/" not in value:
            raise ValueError("model must be in format 'provider/model'")
        return value


class LLMResponse(BaseModel):
    request_id: str
    created_at: str
    model: str
    content: str
    finish_reason: str | None
    latency_ms: int
    usage: dict[str, Any]
    validation: dict[str, Any]
    raw_response_id: str | None = None


# =========================
# Helpers
# =========================
def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_write_audit(payload: dict[str, Any]) -> None:
    audit_logger.info(json.dumps(payload, ensure_ascii=False))


def extract_text_from_chat_completion(resp: Any) -> tuple[str, str | None]:
    content_parts = []
    finish_reason = None

    if not hasattr(resp, "choices") or not resp.choices:
        return "", None

    for choice in resp.choices:
        if getattr(choice, "message", None) and getattr(choice.message, "content", None):
            content_parts.append(choice.message.content)
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

    # OpenAI SDK objects are not always plain dicts
    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }


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
                "message": str(exc),
                "request_id": request_id,
                "latency_ms": latency_ms,
            },
        )


# =========================
# Routes
# =========================
@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": "llm-gateway",
        "base_url": PROXYAPI_BASE_URL,
        "default_model": DEFAULT_MODEL,
        "time": utc_now_iso(),
    }


@app.post("/generate", response_model=LLMResponse)
def generate(payload: LLMRequest) -> LLMResponse:
    request_id = str(uuid.uuid4())
    started = time.perf_counter()

    request_snapshot = {
        "request_id": request_id,
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
    }

    logger.info(
        f"LLM request started request_id={request_id} "
        f"model={payload.model} messages={len(payload.messages)}"
    )

    try:
        params = {
            "model": payload.model,
            "messages": [msg.model_dump() for msg in payload.messages],
            "temperature": payload.temperature,
            "top_p": payload.top_p,
            "presence_penalty": payload.presence_penalty,
            "frequency_penalty": payload.frequency_penalty,
            "stop": payload.stop,
            "user": payload.user_id,
}
        if "gpt-5" in payload.model:
            params["max_completion_tokens"] = payload.max_tokens
        else:
            params["max_tokens"] = payload.max_tokens

        response = client.chat.completions.create(**params)
        
        latency_ms = int((time.perf_counter() - started) * 1000)
        content, finish_reason = extract_text_from_chat_completion(response)
        validation_result = validate_output(content, payload.validation)
        usage = get_usage(response)

        result = LLMResponse(
            request_id=request_id,
            created_at=utc_now_iso(),
            model=payload.model,
            content=content,
            finish_reason=finish_reason,
            latency_ms=latency_ms,
            usage=usage,
            validation=validation_result,
            raw_response_id=getattr(response, "id", None),
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
                    "content_preview": content[:1000],
                },
            }
        )

        logger.info(
            f"LLM request completed request_id={request_id} "
            f"model={payload.model} latency_ms={latency_ms} "
            f"finish_reason={finish_reason}"
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
            f"model={payload.model} latency_ms={latency_ms}: {exc}"
        )

        raise HTTPException(
            status_code=502,
            detail={
                "error": "upstream_llm_error",
                "message": str(exc),
                "request_id": request_id,
                "latency_ms": latency_ms,
            },
        )


@app.get("/models")
def list_models() -> dict[str, Any]:
    """
    Пробует получить список моделей через OpenAI-compatible endpoint.
    """
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