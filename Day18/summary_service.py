from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from config import DEFAULT_MODEL, SUMMARY_LOOKBACK_HOURS
from llm_schemas import SummaryRequest
from llm_service import generate_summary
from repository_aggregates import get_aggregates_for_period
from repository_summaries import insert_summary
from summary_prompts import build_summary_prompt


def generate_periodic_summary(summary_type: str = "hourly") -> dict[str, Any]:
    finished_at = datetime.now(timezone.utc)
    started_at = finished_at - timedelta(hours=SUMMARY_LOOKBACK_HOURS)
    aggregates = get_aggregates_for_period("15m", started_at, finished_at)
    prompt = build_summary_prompt(started_at=started_at, finished_at=finished_at, aggregates=aggregates)
    content = generate_summary(
        SummaryRequest(
            title="Monitoring summary",
            prompt=prompt,
            model=DEFAULT_MODEL,
        )
    )
    summary_id = insert_summary(
        summary_type=summary_type,
        period_started_at=started_at,
        period_finished_at=finished_at,
        title="Hourly monitoring summary",
        content=content,
        model=DEFAULT_MODEL,
        metadata={
            "aggregate_count": len(aggregates),
            "window_type": "15m",
        },
    )
    return {
        "summary_id": summary_id,
        "summary_type": summary_type,
        "aggregate_count": len(aggregates),
    }
