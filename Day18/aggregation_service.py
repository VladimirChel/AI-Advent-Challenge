from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta, timezone
from typing import Any

from repository_aggregates import upsert_aggregate
from repository_readings import get_readings_for_period


def aggregate_recent_readings(window_type: str = "15m", interval_minutes: int = 15) -> dict[str, Any]:
    finished_at = datetime.now(timezone.utc)
    started_at = finished_at - timedelta(minutes=interval_minutes)
    rows = get_readings_for_period(started_at, finished_at)

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[row["sensor_id"]].append(row)

    aggregates_created = 0
    for sensor_id, items in grouped.items():
        values = [float(item["value"]) for item in items if item["value"] is not None]
        if not values:
            continue
        latest_item = items[-1]
        upsert_aggregate(
            sensor_id=sensor_id,
            alias=latest_item.get("alias"),
            units=latest_item.get("units"),
            window_type=window_type,
            window_started_at=started_at,
            window_finished_at=finished_at,
            samples_count=len(values),
            min_value=min(values),
            max_value=max(values),
            avg_value=sum(values) / len(values),
            last_value=values[-1],
        )
        aggregates_created += 1

    return {
        "window_type": window_type,
        "window_started_at": started_at.isoformat(),
        "window_finished_at": finished_at.isoformat(),
        "sensors_aggregated": aggregates_created,
    }
