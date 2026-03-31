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
                CREATE TABLE IF NOT EXISTS conversations (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    model TEXT NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS messages (
                    id BIGSERIAL PRIMARY KEY,
                    message_uuid TEXT UNIQUE,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    role TEXT NOT NULL CHECK (role IN ('system', 'user', 'assistant')),
                    content TEXT NOT NULL,
                    seq_no INTEGER NOT NULL,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_messages_conversation_branch_seq
                ON messages (conversation_id, branch_id, seq_no DESC)
                """
            )

            cur.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS uniq_messages_branch_seq
                ON messages (conversation_id, branch_id, seq_no)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS task_memory (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    task_id TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    goal TEXT,
                    current_step TEXT,
                    plan JSONB NOT NULL DEFAULT '[]',
                    completed_steps JSONB NOT NULL DEFAULT '[]',
                    constraints JSONB NOT NULL DEFAULT '[]',
                    artifacts JSONB NOT NULL DEFAULT '[]',
                    task_state JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id, task_id)
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_memory_updated
                ON task_memory (conversation_id, branch_id, updated_at DESC)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    summary TEXT NOT NULL,
                    source_upto_seq_no INTEGER NOT NULL,
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_facts (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    memory_kind TEXT NOT NULL DEFAULT 'knowledge',
                    confidence REAL NOT NULL DEFAULT 0.8,
                    source TEXT NOT NULL DEFAULT 'llm',
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id, key)
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_facts_kind
                ON conversation_facts (conversation_id, branch_id, memory_kind, updated_at DESC)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS memory_chunks (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    source_type TEXT NOT NULL,
                    source_ref TEXT NOT NULL,
                    memory_tier TEXT NOT NULL,
                    chunk_text TEXT NOT NULL,
                    importance REAL NOT NULL DEFAULT 0.5,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_lookup
                ON memory_chunks (conversation_id, branch_id, memory_tier, updated_at DESC)
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
