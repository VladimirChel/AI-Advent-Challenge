from __future__ import annotations

import json
from typing import Any

from schemas import RetrievedChunk


def build_system_prompt() -> str:
    return (
        "Ты AI-ассистент поддержки пользователей. "
        "Отвечай пользователю напрямую, как сотрудник поддержки, а не как внутренний аналитик. "
        "Опирайся только на вопрос, данные пользователя, данные тикета и найденную документацию. "
        "Не пиши, что ты анализируешь вопрос или контекст. Не описывай внутренний процесс рассуждения. "
        "Сразу дай полезный ответ по существу: что, вероятно, произошло и что пользователю сделать дальше. "
        "Если документации недостаточно, честно скажи об этом и попроси уточнение. "
        "Не выдумывай факты и не ссылайся на несуществующие правила."
    )


def build_support_prompt(
    *,
    question: str,
    user: dict[str, Any] | None,
    ticket: dict[str, Any] | None,
    related_tickets: list[dict[str, Any]],
    rag_chunks: list[RetrievedChunk],
) -> str:
    payload = {
        "question": question,
        "user": user,
        "ticket": ticket,
        "related_tickets": related_tickets[:3],
        "documentation_matches": [
            {
                "rank": chunk.rank,
                "score": round(chunk.score, 4),
                "chunk_id": chunk.chunk_id,
                "source": chunk.source,
                "section": chunk.section,
                "text": chunk.text,
            }
            for chunk in rag_chunks
        ],
    }
    return (
        "Подготовь ответ пользователю службы поддержки.\n"
        "Говори прямо с пользователем на русском языке.\n"
        "Используй JSON-контекст ниже как источник истины.\n"
        "Главный приоритет: практический ответ и следующие шаги.\n"
        "Если есть полезные действия из документации, перечисли их коротко и понятно.\n"
        "Не пиши фразы вроде 'по тикету видно', 'я проанализировал', 'документация рекомендует'. "
        "Вместо этого сразу формулируй совет пользователю.\n\n"
        f"{json.dumps(payload, ensure_ascii=False, indent=2)}"
    )
