from __future__ import annotations

import json
from datetime import datetime


def build_summary_prompt(*, started_at: datetime, finished_at: datetime, aggregates: list[dict]) -> str:
    if not aggregates:
        return (
            f"No aggregates were produced for the period from {started_at.isoformat()} to {finished_at.isoformat()}. "
            "Return a brief note that there was not enough fresh data."
        )

    serialized = json.dumps(aggregates, ensure_ascii=False, indent=2)
    return (
        "Prepare a short operational summary for the monitoring agent.\n"
        f"Period start: {started_at.isoformat()}\n"
        f"Period end: {finished_at.isoformat()}\n"
        "Use the aggregate metrics below and mention notable min/max/average values.\n"
        "Keep the answer compact and useful for an operator.\n\n"
        f"{serialized}"
    )
