from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from db import get_db_connection


def insert_summary(
    *,
    summary_type: str,
    period_started_at: datetime,
    period_finished_at: datetime,
    title: str | None,
    content: str,
    model: str | None,
    metadata: dict[str, Any] | None = None,
) -> int:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO summaries (
                    summary_type,
                    period_started_at,
                    period_finished_at,
                    title,
                    content,
                    model,
                    metadata
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb)
                RETURNING id
                """,
                (
                    summary_type,
                    period_started_at,
                    period_finished_at,
                    title,
                    content,
                    model,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            summary_id = cur.fetchone()[0]
        conn.commit()
    return int(summary_id)


def get_latest_summary(summary_type: str | None = None) -> dict[str, Any] | None:
    query = """
        SELECT id, summary_type, period_started_at, period_finished_at, title, content, model, metadata, created_at
        FROM summaries
    """
    params: tuple[Any, ...] = ()
    if summary_type:
        query += " WHERE summary_type = %s"
        params = (summary_type,)
    query += " ORDER BY created_at DESC LIMIT 1"

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "summary_type": row[1],
        "period_started_at": row[2].isoformat(),
        "period_finished_at": row[3].isoformat(),
        "title": row[4],
        "content": row[5],
        "model": row[6],
        "metadata": row[7],
        "created_at": row[8].isoformat(),
    }
