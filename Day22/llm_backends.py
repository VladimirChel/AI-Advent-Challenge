#!/usr/bin/env python3
from __future__ import annotations

import json
import urllib.error
import urllib.request

from rag_compare import call_llm, register_temporary_user


DEFAULT_ASSISTANT_MODEL = "openai/gpt-4o-mini"
DEFAULT_OLLAMA_MODEL = "llama3"


def call_ollama(
    *,
    ollama_url: str,
    model: str,
    prompt: str,
    temperature: float,
) -> str:
    payload = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": temperature,
        },
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{ollama_url.rstrip('/')}/api/generate",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Ollama вернула HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Не удалось подключиться к Ollama по адресу {ollama_url}") from exc

    answer = str(result.get("response", "")).strip()
    if not answer:
        raise RuntimeError("Ollama вернула пустой ответ.")
    return answer


def resolve_auth_token(*, llm_backend: str, assistant_url: str, auth_token: str) -> str:
    if llm_backend != "assistant":
        return ""
    return auth_token.strip() or register_temporary_user(assistant_url)


def generate_text(
    *,
    llm_backend: str,
    prompt: str,
    temperature: float,
    assistant_url: str,
    assistant_model: str,
    auth_token: str,
    max_tokens: int,
    user_id: str,
    ollama_url: str,
    ollama_model: str,
) -> str:
    if llm_backend == "assistant":
        return call_llm(
            assistant_url=assistant_url,
            auth_token=auth_token,
            model=assistant_model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
            user_id=user_id,
        )
    if llm_backend == "ollama":
        return call_ollama(
            ollama_url=ollama_url,
            model=ollama_model,
            prompt=prompt,
            temperature=temperature,
        )
    raise ValueError(f"Неизвестный llm_backend: {llm_backend}")
