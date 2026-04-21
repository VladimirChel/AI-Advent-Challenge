from fastapi import APIRouter, Query

from app.services.model_service import model_service


router = APIRouter(tags=["models"])


@router.get("/models")
async def list_models(
    provider: str | None = Query(default=None),
    source: str | None = Query(default=None),
) -> dict[str, object]:
    items = await model_service.list_models(provider=provider, source=source)
    return {"items": items}

