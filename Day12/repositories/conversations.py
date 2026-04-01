from __future__ import annotations

from fastapi import HTTPException

from db import get_db_connection


def get_conversation_owner(conversation_id: str) -> str | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT user_id
                FROM conversations
                WHERE id = %s
                """,
                (conversation_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return row[0]


def assert_conversation_access(*, conversation_id: str, user_id: str) -> None:
    owner_id = get_conversation_owner(conversation_id)
    if owner_id and owner_id != user_id:
        raise HTTPException(status_code=403, detail="conversation_access_denied")
