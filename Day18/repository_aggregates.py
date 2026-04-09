from __future__ import annotations

from datetime import datetime

from db import get_db_connection


def upsert_aggregate(
    *,
    sensor_id: str,
    alias: str | None,
    units: str | None,
    window_type: str,
    window_started_at: datetime,
    window_finished_at: datetime,
    samples_count: int,
    min_value: float | None,
    max_value: float | None,
    avg_value: float | None,
    last_value: float | None,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sensor_aggregates (
                    sensor_id,
                    alias,
                    units,
                    window_type,
                    window_started_at,
                    window_finished_at,
                    samples_count,
                    min_value,
                    max_value,
                    avg_value,
                    last_value
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (sensor_id, window_type, window_started_at, window_finished_at)
                DO UPDATE SET
                    alias = EXCLUDED.alias,
                    units = EXCLUDED.units,
                    samples_count = EXCLUDED.samples_count,
                    min_value = EXCLUDED.min_value,
                    max_value = EXCLUDED.max_value,
                    avg_value = EXCLUDED.avg_value,
                    last_value = EXCLUDED.last_value,
                    created_at = NOW()
                """,
                (
                    sensor_id,
                    alias,
                    units,
                    window_type,
                    window_started_at,
                    window_finished_at,
                    samples_count,
                    min_value,
                    max_value,
                    avg_value,
                    last_value,
                ),
            )
        conn.commit()


def get_aggregates(window_type: str, limit: int = 100) -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sensor_id, alias, units, window_type, window_started_at, window_finished_at,
                       samples_count, min_value, max_value, avg_value, last_value, created_at
                FROM sensor_aggregates
                WHERE window_type = %s
                ORDER BY window_finished_at DESC, sensor_id ASC
                LIMIT %s
                """,
                (window_type, limit),
            )
            rows = cur.fetchall()
    return [
        {
            "sensor_id": row[0],
            "alias": row[1],
            "units": row[2],
            "window_type": row[3],
            "window_started_at": row[4].isoformat(),
            "window_finished_at": row[5].isoformat(),
            "samples_count": row[6],
            "min_value": row[7],
            "max_value": row[8],
            "avg_value": row[9],
            "last_value": row[10],
            "created_at": row[11].isoformat(),
        }
        for row in rows
    ]


def get_aggregates_for_period(window_type: str, started_at: datetime, finished_at: datetime) -> list[dict]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT sensor_id, alias, units, samples_count, min_value, max_value, avg_value, last_value
                FROM sensor_aggregates
                WHERE window_type = %s
                  AND window_started_at >= %s
                  AND window_finished_at <= %s
                ORDER BY sensor_id ASC, window_started_at ASC
                """,
                (window_type, started_at, finished_at),
            )
            rows = cur.fetchall()
    return [
        {
            "sensor_id": row[0],
            "alias": row[1],
            "units": row[2],
            "samples_count": row[3],
            "min_value": row[4],
            "max_value": row[5],
            "avg_value": row[6],
            "last_value": row[7],
        }
        for row in rows
    ]
