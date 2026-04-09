from __future__ import annotations

from datetime import datetime
from typing import Any

from db import get_db_connection


def insert_sensor_readings(readings: list[dict[str, Any]]) -> int:
    if not readings:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for item in readings:
                cur.execute(
                    """
                    INSERT INTO sensor_readings (
                        sensor_id,
                        alias,
                        value,
                        units,
                        source_updated_at,
                        payload
                    )
                    VALUES (%s, %s, %s, %s, %s, %s::jsonb)
                    """,
                    (
                        item.get("sensor_id"),
                        item.get("alias"),
                        item.get("value"),
                        item.get("units"),
                        _timestamp_or_none(item.get("updated_at")),
                        _to_json(item),
                    ),
                )
        conn.commit()
    return len(readings)


def get_latest_readings(limit: int = 100) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT ON (sensor_id)
                    sensor_id,
                    alias,
                    value,
                    units,
                    source_updated_at,
                    collected_at
                FROM sensor_readings
                ORDER BY sensor_id, collected_at DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
    return [
        {
            "sensor_id": row[0],
            "alias": row[1],
            "value": row[2],
            "units": row[3],
            "source_updated_at": row[4].isoformat() if row[4] else None,
            "collected_at": row[5].isoformat() if row[5] else None,
        }
        for row in rows
    ]


def get_readings_for_period(started_at: datetime, finished_at: datetime) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sensor_id, alias, units, value, collected_at
                FROM sensor_readings
                WHERE collected_at >= %s AND collected_at < %s
                ORDER BY sensor_id, collected_at ASC
                """,
                (started_at, finished_at),
            )
            rows = cur.fetchall()
    return [
        {
            "sensor_id": row[0],
            "alias": row[1],
            "units": row[2],
            "value": row[3],
            "collected_at": row[4],
        }
        for row in rows
    ]


def _timestamp_or_none(raw_value: Any) -> datetime | None:
    if raw_value is None:
        return None
    if isinstance(raw_value, datetime):
        return raw_value
    if isinstance(raw_value, (int, float)):
        return datetime.fromtimestamp(raw_value)
    return None


def _to_json(item: dict[str, Any]) -> str:
    import json

    return json.dumps(item, ensure_ascii=False)
