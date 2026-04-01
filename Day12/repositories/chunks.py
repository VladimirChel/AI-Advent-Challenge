from __future__ import annotations

import re
from typing import Iterable

from db import get_db_connection
from llm.schemas import ChatMessage
from memory.models import RetrievedMemoryItem


TOKEN_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9_]{2,}")
STOPWORDS = {
    "и", "в", "на", "с", "по", "к", "у", "о", "что", "как", "я", "мы", "ты", "это", "the", "and", "for", "from",
}


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in TOKEN_RE.findall(text) if t.lower() not in STOPWORDS]


def add_memory_chunks(
    user_id: str,
    conversation_id: str,
    branch_id: str,
    messages: Iterable[ChatMessage],
    *,
    source_type: str = "message",
    memory_tier: str = "episodic",
) -> int:
    rows = []
    for idx, msg in enumerate(messages, start=1):
        text = " ".join(msg.content.split()).strip()
        if not text:
            continue
        rows.append((conversation_id, user_id, branch_id, source_type, f"{msg.role}:{idx}", memory_tier, text[:4000], 0.5))

    if not rows:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO memory_chunks (
                    conversation_id, user_id, branch_id, source_type, source_ref, memory_tier, chunk_text, importance
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                rows,
            )
        conn.commit()

    return len(rows)


def retrieve_memory_chunks(
    user_id: str,
    query: str,
    limit: int,
) -> list[RetrievedMemoryItem]:
    tokens = _tokenize(query)
    if not tokens or limit <= 0:
        return []

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT source_type, source_ref, memory_tier, chunk_text, importance
                FROM memory_chunks
                WHERE user_id = %s
                ORDER BY updated_at DESC, id DESC
                LIMIT 200
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    ranked: list[RetrievedMemoryItem] = []
    for source_type, source_ref, memory_tier, chunk_text, importance in rows:
        haystack_tokens = set(_tokenize(chunk_text))
        overlap = sum(1 for token in tokens if token in haystack_tokens)
        if overlap <= 0:
            continue
        score = overlap + float(importance or 0)
        ranked.append(
            RetrievedMemoryItem(
                source_type=f"{source_type}/{memory_tier}",
                source_ref=source_ref,
                score=round(score, 3),
                content=chunk_text,
            )
        )

    ranked.sort(key=lambda item: item.score, reverse=True)
    return ranked[:limit]
