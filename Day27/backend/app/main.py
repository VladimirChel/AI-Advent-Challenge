from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import chats, models, providers, settings as settings_routes
from app.core.config import get_settings
from app.db.session import init_db


app_settings = get_settings()

app = FastAPI(
    title="LLM Chat API",
    version="0.1.0",
    description="Backend API for cloud and local LLM chat providers.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(chats.router, prefix="/api")
app.include_router(models.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(settings_routes.router, prefix="/api")


@app.on_event("startup")
def on_startup() -> None:
    init_db()


@app.get("/health")
async def healthcheck() -> dict[str, str]:
    return {"status": "ok", "environment": app_settings.app_env}
