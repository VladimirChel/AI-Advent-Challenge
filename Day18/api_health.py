from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter

from config import APP_NAME, APP_VERSION, DEFAULT_MODEL
from db import healthcheck_db

router = APIRouter(tags=["health"])


@router.get("/health")
def health() -> dict[str, Any]:
    db_ok, db_error = healthcheck_db()
    return {
        "status": "ok" if db_ok else "degraded",
        "service": APP_NAME,
        "version": APP_VERSION,
        "database": "ok" if db_ok else "error",
        "database_error": db_error,
        "default_model": DEFAULT_MODEL,
        "time": datetime.now(timezone.utc).isoformat(),
    }
