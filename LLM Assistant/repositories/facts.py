from __future__ import annotations

import re
from datetime import timezone

from db import get_db_connection
from llm.schemas import ChatMessage
from memory.models import StickyFact


FACT_PATTERNS: list[tuple[re.Pattern[str], str, str]] = [
    (re.compile(r"(?:меня зовут|мо[её] имя)\s+([A-ZА-ЯЁ][a-zа-яё\-]+)", re.IGNORECASE), "user_name", "profile"),
    (re.compile(r"мой проект(?: называется)?\s+([A-Za-zА-Яа-яЁё0-9_\- ]{2,80})", re.IGNORECASE), "project_name", "project"),
    (re.compile(r"мой любимый язык\s*[—\-:]?\s*([A-Za-zА-Яа-яЁё0-9_+#. ]{2,60})", re.IGNORECASE), "favorite_language", "preference"),
    (re.compile(r"дедлайн\s+(.{3,120})", re.IGNORECASE), "deadline", "task"),
    (re.compile(r"я работаю над\s+(.{3,120})", re.IGNORECASE), "current_project", "project"),
]


def get_user_facts(user_id: str) -> list[StickyFact]:
    with get_db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT key, value, memory_kind, confidence, source, updated_at
                FROM (
                    SELECT DISTINCT ON (key)
                        key, value, memory_kind, confidence, source, updated_at
                    FROM conversation_facts
                    WHERE user_id = %s
                    ORDER BY key ASC, updated_at DESC
                ) AS latest_facts
                ORDER BY updated_at DESC, key ASC
                """,
                (user_id,),
            )
            rows = cur.fetchall()

    return [
        StickyFact(
            key=row[0],
            value=row[1],
            memory_kind=row[2],
            confidence=float(row[3]),
            source=row[4],
            updated_at=row[5].replace(tzinfo=timezone.utc).isoformat() if row[5] else None,
        )
        for row in rows
    ]


def extract_candidate_facts(messages: list[ChatMessage]) -> list[StickyFact]:
    facts: dict[str, StickyFact] = {}
    for msg in messages:
        if msg.role != "user":
            continue
        text = " ".join(msg.content.split())
        for pattern, key, kind in FACT_PATTERNS:
            match = pattern.search(text)
            if match:
                value = match.group(1).strip(" .,:;!?")
                if value:
                    facts[key] = StickyFact(key=key, value=value, memory_kind=kind, confidence=0.85, source="heuristic")
    return list(facts.values())


def upsert_facts(conversation_id: str, branch_id: str, user_id: str, facts: list[StickyFact]) -> int:
    if not facts:
        return 0

    with get_db_connection() as conn:
        with conn.cursor() as cur:
            for fact in facts:
                cur.execute(
                    """
                    INSERT INTO conversation_facts (
                        conversation_id, user_id, branch_id, key, value, memory_kind, confidence, source, updated_at
                    )
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (conversation_id, branch_id, key)
                    DO UPDATE SET
                        user_id = EXCLUDED.user_id,
                        value = EXCLUDED.value,
                        memory_kind = EXCLUDED.memory_kind,
                        confidence = EXCLUDED.confidence,
                        source = EXCLUDED.source,
                        updated_at = NOW()
                    """,
                    (
                        conversation_id,
                        user_id,
                        branch_id,
                        fact.key,
                        fact.value,
                        fact.memory_kind,
                        fact.confidence,
                        fact.source,
                    ),
                )
        conn.commit()

    return len(facts)
