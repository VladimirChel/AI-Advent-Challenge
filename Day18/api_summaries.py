from fastapi import APIRouter, Query

from repository_summaries import get_latest_summary

router = APIRouter(prefix="/summaries", tags=["summaries"])


@router.get("/latest")
def latest_summary(summary_type: str | None = Query(default=None)) -> dict:
    return {"item": get_latest_summary(summary_type)}
