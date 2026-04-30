from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import FastAPI

from config import APP_HOST, APP_NAME, APP_PORT
from schemas import SupportAnswerRequest, SupportAnswerResponse
from support_service import SupportService


app = FastAPI(title=APP_NAME, version="0.1.0")
service = SupportService()


@app.get("/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "service": APP_NAME,
        "time": datetime.now(timezone.utc).isoformat(),
    }


@app.post("/support/answer", response_model=SupportAnswerResponse)
def support_answer(payload: SupportAnswerRequest) -> SupportAnswerResponse:
    return service.answer(payload)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
