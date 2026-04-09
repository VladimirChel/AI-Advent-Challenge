from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool

from config import DATABASE_URL, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE


db_pool = ConnectionPool(
    conninfo=DATABASE_URL,
    min_size=DB_POOL_MIN_SIZE,
    max_size=DB_POOL_MAX_SIZE,
    open=False,
)


@contextmanager
def get_db_connection() -> Iterator[psycopg.Connection]:
    with db_pool.connection() as conn:
        yield conn


def init_db() -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id BIGSERIAL PRIMARY KEY,
                    sensor_id TEXT NOT NULL,
                    alias TEXT,
                    value DOUBLE PRECISION,
                    units TEXT,
                    source_updated_at TIMESTAMP NULL,
                    collected_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sensor_readings_sensor_collected
                ON sensor_readings (sensor_id, collected_at DESC)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS sensor_aggregates (
                    id BIGSERIAL PRIMARY KEY,
                    sensor_id TEXT NOT NULL,
                    alias TEXT,
                    units TEXT,
                    window_type TEXT NOT NULL,
                    window_started_at TIMESTAMP NOT NULL,
                    window_finished_at TIMESTAMP NOT NULL,
                    samples_count INTEGER NOT NULL,
                    min_value DOUBLE PRECISION,
                    max_value DOUBLE PRECISION,
                    avg_value DOUBLE PRECISION,
                    last_value DOUBLE PRECISION,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    UNIQUE (sensor_id, window_type, window_started_at, window_finished_at)
                )
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_sensor_aggregates_lookup
                ON sensor_aggregates (window_type, window_finished_at DESC, sensor_id)
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS summaries (
                    id BIGSERIAL PRIMARY KEY,
                    summary_type TEXT NOT NULL,
                    period_started_at TIMESTAMP NOT NULL,
                    period_finished_at TIMESTAMP NOT NULL,
                    title TEXT,
                    content TEXT NOT NULL,
                    model TEXT,
                    metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS scheduled_jobs (
                    job_name TEXT PRIMARY KEY,
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    schedule_kind TEXT NOT NULL,
                    schedule_value TEXT NOT NULL,
                    last_run_at TIMESTAMP NULL,
                    next_run_at TIMESTAMP NULL,
                    last_status TEXT NULL,
                    last_error TEXT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS job_runs (
                    id BIGSERIAL PRIMARY KEY,
                    job_name TEXT NOT NULL,
                    started_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    finished_at TIMESTAMP NULL,
                    status TEXT NOT NULL,
                    details JSONB NOT NULL DEFAULT '{}'::jsonb
                )
                """
            )
        conn.commit()


def healthcheck_db() -> tuple[bool, str | None]:
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, None
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
