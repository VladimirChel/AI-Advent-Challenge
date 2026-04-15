from db import get_db_connection
from llm.schemas import ChatMessage


def get_recent_messages(conversation_id: str, branch_id: str, limit: int) -> list[ChatMessage]:
    if limit <= 0:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT role, content
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

    return [ChatMessage(role=row[0], content=row[1]) for row in rows]