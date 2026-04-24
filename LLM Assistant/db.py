from contextlib import contextmanager
from typing import Iterator

import psycopg
from psycopg_pool import ConnectionPool

from config import DATABASE_REQUIRED, DATABASE_URL, DB_POOL_MAX_SIZE, DB_POOL_MIN_SIZE

db_pool = (
    ConnectionPool(
        conninfo=DATABASE_URL,
        min_size=DB_POOL_MIN_SIZE,
        max_size=DB_POOL_MAX_SIZE,
        open=False,
    )
    if DATABASE_REQUIRED
    else None
)


@contextmanager
def get_db_connection() -> Iterator[psycopg.Connection]:
    if db_pool is None:
        raise RuntimeError("database_disabled")
    with db_pool.connection() as conn:
        yield conn


def init_db() -> None:
    if db_pool is None:
        return
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    id TEXT PRIMARY KEY,
                    email TEXT NOT NULL UNIQUE,
                    password_hash TEXT NOT NULL,
                    is_active BOOLEAN NOT NULL DEFAULT TRUE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
                )
                """
            )

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
                    stage TEXT NOT NULL DEFAULT 'planning',
                    goal TEXT,
                    current_step TEXT,
                    expected_action TEXT NOT NULL DEFAULT 'assistant_continue',
                    blocked_reason TEXT,
                    plan JSONB NOT NULL DEFAULT '[]',
                    completed_steps JSONB NOT NULL DEFAULT '[]',
                    constraints JSONB NOT NULL DEFAULT '[]',
                    artifacts JSONB NOT NULL DEFAULT '[]',
                    state_version INTEGER NOT NULL DEFAULT 1,
                    last_event TEXT,
                    task_state JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMP NOT NULL DEFAULT NOW(),
                    PRIMARY KEY (conversation_id, branch_id, task_id)
                )
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS task_transitions (
                    id BIGSERIAL PRIMARY KEY,
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    branch_id TEXT NOT NULL DEFAULT 'main',
                    task_id TEXT NOT NULL,
                    from_status TEXT,
                    to_status TEXT NOT NULL,
                    from_stage TEXT,
                    to_stage TEXT,
                    event TEXT NOT NULL,
                    reason TEXT,
                    payload JSONB NOT NULL DEFAULT '{}',
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
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
                CREATE INDEX IF NOT EXISTS idx_task_transitions_lookup
                ON task_transitions (conversation_id, branch_id, task_id, created_at DESC)
                """
            )

            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS conversation_summaries (
                    conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE,
                    user_id TEXT,
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
                    user_id TEXT,
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
                    user_id TEXT,
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

            cur.execute("ALTER TABLE conversation_summaries ADD COLUMN IF NOT EXISTS user_id TEXT")
            cur.execute("ALTER TABLE conversation_facts ADD COLUMN IF NOT EXISTS user_id TEXT")
            cur.execute("ALTER TABLE memory_chunks ADD COLUMN IF NOT EXISTS user_id TEXT")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS phase TEXT")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS next_action TEXT")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS stage TEXT NOT NULL DEFAULT 'planning'")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS expected_action TEXT NOT NULL DEFAULT 'assistant_continue'")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS blocked_reason TEXT")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS state_version INTEGER NOT NULL DEFAULT 1")
            cur.execute("ALTER TABLE task_memory ADD COLUMN IF NOT EXISTS last_event TEXT")
            cur.execute("ALTER TABLE task_transitions ADD COLUMN IF NOT EXISTS from_phase TEXT")
            cur.execute("ALTER TABLE task_transitions ADD COLUMN IF NOT EXISTS to_phase TEXT")
            cur.execute("ALTER TABLE task_transitions ADD COLUMN IF NOT EXISTS from_stage TEXT")
            cur.execute("ALTER TABLE task_transitions ADD COLUMN IF NOT EXISTS to_stage TEXT")

            cur.execute("UPDATE task_memory SET stage = phase WHERE stage = 'planning' AND phase IS NOT NULL")
            cur.execute("UPDATE task_memory SET expected_action = COALESCE(next_action, expected_action) WHERE expected_action = 'assistant_continue'")
            cur.execute("UPDATE task_transitions SET from_stage = from_phase WHERE from_stage IS NULL AND from_phase IS NOT NULL")
            cur.execute("UPDATE task_transitions SET to_stage = to_phase WHERE to_stage IS NULL AND to_phase IS NOT NULL")

            cur.execute(
                """
                UPDATE conversation_summaries AS s
                SET user_id = c.user_id
                FROM conversations AS c
                WHERE s.conversation_id = c.id
                  AND s.user_id IS NULL
                """
            )
            cur.execute(
                """
                UPDATE conversation_facts AS f
                SET user_id = c.user_id
                FROM conversations AS c
                WHERE f.conversation_id = c.id
                  AND f.user_id IS NULL
                """
            )
            cur.execute(
                """
                UPDATE memory_chunks AS m
                SET user_id = c.user_id
                FROM conversations AS c
                WHERE m.conversation_id = c.id
                  AND m.user_id IS NULL
                """
            )

            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_summaries_user_updated
                ON conversation_summaries (user_id, updated_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_conversation_facts_user_updated
                ON conversation_facts (user_id, updated_at DESC)
                """
            )
            cur.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_memory_chunks_user_updated
                ON memory_chunks (user_id, updated_at DESC)
                """
            )
        conn.commit()


def healthcheck_db() -> tuple[bool, str | None]:
    if db_pool is None:
        return False, "disabled"
    try:
        with get_db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                cur.fetchone()
        return True, None
    except Exception as exc:  # pragma: no cover
        return False, str(exc)
