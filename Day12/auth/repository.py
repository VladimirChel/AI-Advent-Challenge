from __future__ import annotations

import uuid

from db import get_db_connection


def create_user(*, email: str, password_hash: str) -> dict[str, str | bool] | None:
    user_id = str(uuid.uuid4())
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (id, email, password_hash)
                VALUES (%s, %s, %s)
                ON CONFLICT (email) DO NOTHING
                RETURNING id, email, is_active
                """,
                (user_id, email, password_hash),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        return None

    return {"id": row[0], "email": row[1], "is_active": bool(row[2])}


def get_user_by_email(email: str) -> dict[str, str | bool] | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, password_hash, is_active
                FROM users
                WHERE email = %s
                """,
                (email,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "email": row[1],
        "password_hash": row[2],
        "is_active": bool(row[3]),
    }


def get_user_by_id(user_id: str) -> dict[str, str | bool] | None:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, email, is_active
                FROM users
                WHERE id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {"id": row[0], "email": row[1], "is_active": bool(row[2])}
