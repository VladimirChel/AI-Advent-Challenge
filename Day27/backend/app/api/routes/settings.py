from fastapi import APIRouter

from app.core.config import get_settings
from app.schemas.settings import SettingsRead, SettingsUpdate


router = APIRouter(tags=["settings"])

_state = SettingsRead(
    default_provider=get_settings().default_provider,
    default_model=get_settings().default_model,
    default_temperature=0.7,
    default_max_tokens=1024,
    system_prompt="",
)


@router.get("/settings", response_model=SettingsRead)
async def get_app_settings() -> SettingsRead:
    return _state


@router.patch("/settings", response_model=SettingsRead)
async def update_app_settings(payload: SettingsUpdate) -> SettingsRead:
    global _state
    _state = _state.model_copy(update=payload.model_dump(exclude_none=True))
    return _state

