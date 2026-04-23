from __future__ import annotations

from dataclasses import dataclass
from datetime import timezone

from db import get_db_connection
from llm.schemas import ChatMessage
from config import SUMMARY_KEEP_LAST_MESSAGES, SUMMARY_MAX_TOKENS


@dataclass
class ConversationSummaryRecord:
    conversation_id: str
    branch_id: str
    summary: str
    source_upto_seq_no: int
    updated_at: str | None = None


def get_conversation_summary(conversation_id: str, branch_id: str) -> ConversationSummaryRecord | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT conversation_id, branch_id, summary, source_upto_seq_no, updated_at
                FROM conversation_summaries
                WHERE conversation_id = %s AND branch_id = %s
                """,
                (conversation_id, branch_id),
            )
            row = cur.fetchone()

    if not row:
        return None

    return ConversationSummaryRecord(
        conversation_id=row[0],
        branch_id=row[1],
        summary=row[2],
        source_upto_seq_no=int(row[3]),
        updated_at=row[4].replace(tzinfo=timezone.utc).isoformat() if row[4] else None,
    )


def get_user_memory_summary(user_id: str, limit: int = 3) -> str | None:
    if limit <= 0:
        return None

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT summary
                FROM conversation_summaries
                WHERE user_id = %s
                ORDER BY updated_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

    summaries = [row[0].strip() for row in rows if row and row[0] and row[0].strip()]
    if not summaries:
        return None

    if len(summaries) == 1:
        return summaries[0]

    return "Контекст из прошлых диалогов пользователя:\n" + "\n\n".join(
        f"Фрагмент {idx}: {summary}"
        for idx, summary in enumerate(summaries, start=1)
    )


def build_summary_from_messages(
    messages: list[ChatMessage],
    *,
    max_items: int = SUMMARY_KEEP_LAST_MESSAGES,
    max_chars: int = SUMMARY_MAX_TOKENS * 4,
) -> str:
    if not messages:
        return ""

    compact: list[str] = []
    for msg in messages[-max_items:]:
        role = "Пользователь" if msg.role == "user" else "Ассистент" if msg.role == "assistant" else "Система"
        content = " ".join(msg.content.split())
        compact.append(f"{role}: {content[:400]}")

    summary = "Краткая сводка последних важных сообщений:\n" + "\n".join(f"- {line}" for line in compact)
    return summary[:max_chars]


def upsert_conversation_summary(
    conversation_id: str,
    branch_id: str,
    user_id: str,
    summary: str,
    source_upto_seq_no: int,
) -> None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversation_summaries (
                    conversation_id, user_id, branch_id, summary, source_upto_seq_no, updated_at
                )
                VALUES (%s, %s, %s, %s, %s, NOW())
                ON CONFLICT (conversation_id, branch_id)
                DO UPDATE SET
                    user_id = EXCLUDED.user_id,
                    summary = EXCLUDED.summary,
                    source_upto_seq_no = EXCLUDED.source_upto_seq_no,
                    updated_at = NOW()
                """,
                (conversation_id, user_id, branch_id, summary, source_upto_seq_no),
            )
        conn.commit()
