import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI

from api_agent import router as agent_router
from api_health import router as health_router
from api_readings import router as readings_router
from api_summaries import router as summaries_router
from config import APP_NAME, APP_VERSION, LOG_LEVEL
from db import db_pool, init_db
from scheduler_service import SchedulerService

logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)

scheduler = SchedulerService()


@asynccontextmanager
async def lifespan(_: FastAPI):
    db_pool.open()
    init_db()
    await scheduler.start()
    try:
        yield
    finally:
        await scheduler.stop()
        db_pool.close()


app = FastAPI(
    title=APP_NAME,
    version=APP_VERSION,
    description="Scheduled monitoring agent with PostgreSQL storage and periodic summaries",
    lifespan=lifespan,
)

app.include_router(health_router)
app.include_router(agent_router)
app.include_router(readings_router)
app.include_router(summaries_router)


@app.get("/")
def root() -> dict[str, Any]:
    return {
        "service": APP_NAME,
        "version": APP_VERSION,
        "message": "Day18 scheduled agent is running",
    }


if __name__ == "__main__":
    import uvicorn
    from config import APP_HOST, APP_PORT

    uvicorn.run("main:app", host=APP_HOST, port=APP_PORT, reload=True)
