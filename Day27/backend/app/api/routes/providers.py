from fastapi import APIRouter

from app.services.model_service import model_service


router = APIRouter(tags=["providers"])


@router.get("/providers/health")
async def provider_health() -> dict[str, object]:
    return {"items": await model_service.provider_health()}

