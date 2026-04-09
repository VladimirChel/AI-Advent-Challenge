from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from db import get_db_connection


def record_job_start(job_name: str) -> int:
    started_at = datetime.now(timezone.utc)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO job_runs (job_name, started_at, status)
                VALUES (%s, %s, %s)
                RETURNING id
                """,
                (job_name, started_at, "running"),
            )
            run_id = cur.fetchone()[0]
            cur.execute(
                """
                INSERT INTO scheduled_jobs (job_name, enabled, schedule_kind, schedule_value, last_run_at, last_status, updated_at)
                VALUES (%s, TRUE, %s, %s, %s, %s, NOW())
                ON CONFLICT (job_name)
                DO UPDATE SET last_run_at = EXCLUDED.last_run_at, last_status = EXCLUDED.last_status, updated_at = NOW()
                """,
                (job_name, "interval", "runtime-managed", started_at, "running"),
            )
        conn.commit()
    return int(run_id)


def record_job_finish(
    run_id: int,
    *,
    job_name: str,
    status: str,
    details: dict[str, Any] | None = None,
    error: str | None = None,
    next_run_at: datetime | None = None,
) -> None:
    finished_at = datetime.now(timezone.utc)
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE job_runs
                SET finished_at = %s, status = %s, details = %s::jsonb
                WHERE id = %s
                """,
                (finished_at, status, json.dumps(details or {}, ensure_ascii=False), run_id),
            )
            cur.execute(
                """
                INSERT INTO scheduled_jobs (
                    job_name,
                    enabled,
                    schedule_kind,
                    schedule_value,
                    last_run_at,
                    next_run_at,
                    last_status,
                    last_error,
                    updated_at
                )
                VALUES (%s, TRUE, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (job_name)
                DO UPDATE SET
                    last_run_at = EXCLUDED.last_run_at,
                    next_run_at = EXCLUDED.next_run_at,
                    last_status = EXCLUDED.last_status,
                    last_error = EXCLUDED.last_error,
                    updated_at = NOW()
                """,
                (job_name, "interval", "runtime-managed", finished_at, next_run_at, status, error),
            )
        conn.commit()


def list_jobs() -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT job_name, enabled, schedule_kind, schedule_value, last_run_at, next_run_at, last_status, last_error, updated_at
                FROM scheduled_jobs
                ORDER BY job_name ASC
                """
            )
            rows = cur.fetchall()
    return [
        {
            "job_name": row[0],
            "enabled": row[1],
            "schedule_kind": row[2],
            "schedule_value": row[3],
            "last_run_at": row[4].isoformat() if row[4] else None,
            "next_run_at": row[5].isoformat() if row[5] else None,
            "last_status": row[6],
            "last_error": row[7],
            "updated_at": row[8].isoformat() if row[8] else None,
        }
        for row in rows
    ]
