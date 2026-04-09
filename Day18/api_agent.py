from fastapi import APIRouter

from repository_jobs import list_jobs
from repository_summaries import get_latest_summary

router = APIRouter(prefix="/agent", tags=["agent"])


@router.get("/status")
def agent_status() -> dict:
    return {
        "jobs": list_jobs(),
        "latest_summary": get_latest_summary(),
    }


@router.get("/summary/latest")
def latest_agent_summary() -> dict:
    return {
        "summary": get_latest_summary(),
    }
