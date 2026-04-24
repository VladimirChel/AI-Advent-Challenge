from __future__ import annotations

import json
from typing import Any

import requests

from app.config import AppConfig


SYSTEM_PROMPT = """Ты финансовый помощник по дебиторской задолженности.
Отвечай только на основе переданных данных.
Не выдумывай суммы, даты, контрагентов и менеджеров.
Если данных меньше 3 дней, прямо скажи, что тренд построен по доступному числу дней.
Если в данных нет ответа, так и напиши.
Сначала дай короткий вывод, затем 2-5 фактов по цифрам."""


class LLMAssistantError(RuntimeError):
    pass


def build_user_prompt(context: dict[str, Any]) -> str:
    return (
        "Вопрос пользователя:\n"
        f"{context['question']}\n\n"
        "Структурированные данные:\n"
        f"{json.dumps(context, ensure_ascii=False, indent=2)}"
    )


def ask_llm_assistant(
    config: AppConfig,
    conversation_id: str,
    user_prompt: str,
    system_prompt: str = SYSTEM_PROMPT,
) -> str:
    headers = {"Content-Type": "application/json"}
    if config.llm_assistant_token:
        headers["Authorization"] = f"Bearer {config.llm_assistant_token}"
    payload = {
        "conversation_id": conversation_id,
        "branch_id": "main",
        "task_id": "debt-report",
        "chat_mode": "rag_task_chat",
        "provider_id": config.llm_provider_id or None,
        "model": config.llm_model,
        "temperature": 0.1,
        "max_tokens": 900,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "rag": {"enabled": False},
        "mcp": {"enabled": False},
    }
    response = requests.post(
        config.llm_assistant_url,
        headers=headers,
        json=payload,
        timeout=120,
    )
    if response.status_code >= 400:
        raise LLMAssistantError(f"LLM Assistant error {response.status_code}: {response.text}")
    data = response.json()
    content = data.get("content", "").strip()
    if not content:
        raise LLMAssistantError("LLM Assistant returned empty content")
    return content
