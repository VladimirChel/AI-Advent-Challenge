import uuid
from llm.schemas import ChatMessage
from db import get_db_connection


def save_messages(
    conversation_id: str,
    branch_id: str,
    user_id: str | None,
    model: str,
    messages: list[ChatMessage],
) -> int:
    if not messages:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO conversations (id, user_id, model)
                VALUES (%s, %s, %s)
                ON CONFLICT (id) DO NOTHING
                """,
                (conversation_id, user_id, model),
            )

            cur.execute(
                """
                SELECT COALESCE(MAX(seq_no), 0)
                FROM messages
                WHERE conversation_id = %s AND branch_id = %s
                """,
                (conversation_id, branch_id),
            )
            current_seq = int(cur.fetchone()[0] or 0)

            rows = []
            for i, msg in enumerate(messages, start=1):
                rows.append(
                    (
                        str(uuid.uuid4()),
                        conversation_id,
                        branch_id,
                        msg.role,
                        msg.content,
                        current_seq + i,
                    )
                )

            cur.executemany(
                """
                INSERT INTO messages (
                    message_uuid, conversation_id, branch_id, role, content, seq_no
                )
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                rows,
            )

            cur.execute(
                """
                UPDATE conversations
                SET updated_at = NOW(),
                    user_id = COALESCE(%s, user_id),
                    model = %s
                WHERE id = %s
                """,
                (user_id, model, conversation_id),
            )
        conn.commit()

    return len(messages)


def get_recent_messages_for_summary(conversation_id: str, branch_id: str, limit: int = 16) -> tuple[list[ChatMessage], int]:
    if limit <= 0:
        return [], 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content, seq_no
                FROM (
                    SELECT role, content, seq_no
                    FROM messages
                    WHERE conversation_id = %s AND branch_id = %s
                    ORDER BY seq_no DESC
                    LIMIT %s
                ) AS recent
                ORDER BY seq_no ASC
                """,
                (conversation_id, branch_id, limit),
            )
            rows = cur.fetchall()

    messages = [ChatMessage(role=row[0], content=row[1]) for row in rows]
    latest_seq_no = max((int(row[2]) for row in rows), default=0)
    return messages, latest_seq_no
