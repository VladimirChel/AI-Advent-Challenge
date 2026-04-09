from fastapi import APIRouter, Query

from repository_aggregates import get_aggregates
from repository_readings import get_latest_readings

router = APIRouter(tags=["readings"])


@router.get("/readings/latest")
def latest_readings(limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": get_latest_readings(limit)}


@router.get("/aggregates")
def aggregates(window_type: str = Query(default="15m"), limit: int = Query(default=100, ge=1, le=500)) -> dict:
    return {"items": get_aggregates(window_type, limit)}
