import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Any

from fastapi import Depends, FastAPI
from openai import OpenAI

from config import (
    APP_NAME,
    APP_VERSION,
    DEFAULT_MODEL,
    PROXYAPI_API_KEY,
    PROXYAPI_BASE_URL,
    REQUEST_TIMEOUT_SECONDS,
)
from db import db_pool, healthcheck_db, init_db
from auth.dependencies import get_current_user
from auth.schemas import PublicUser


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("agent_app")

client = OpenAI(
    api_key=PROXYAPI_API_KEY,
    base_url=PROXYAPI_BASE_URL,
    timeout=REQUEST_TIMEOUT_SECONDS,
)


@asynccontextmanager
async def lifespan(_: FastAPI):
    db_pool.open()
    init_db()
    logger.info("Database pool opened and schema initialized")
    try:
        yield
    finally:
        db_pool.close()
        logger.info("Database pool closed")


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Agent gateway with explicit memory layers",
    lifespan=lifespan,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@app.get("/health")
def health() -> dict[str, Any]:
    db_ok, db_error = healthcheck_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
        "default_model": DEFAULT_MODEL,
        "time": utc_now_iso(),
    }


@app.get("/models")
def list_models(_: PublicUser = Depends(get_current_user)) -> dict[str, Any]:
    result = client.models.list()
    return {
        "data": [
            {
                "id": getattr(item, "id", None),
                "created": getattr(item, "created", None),
                "object": getattr(item, "object", None),
                "owned_by": getattr(item, "owned_by", None),
            }
            for item in result.data
        ]
    }


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "message": "Service is running. Add API routers for generate/tasks/memory next.",
    }

from api.generate import router as generate_router
from api.auth import router as auth_router
from api.invariants import router as invariants_router

app.include_router(auth_router)
app.include_router(generate_router)
app.include_router(invariants_router)

if __name__ == "__main__":
    import uvicorn
    from config import APP_HOST, APP_PORT

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
