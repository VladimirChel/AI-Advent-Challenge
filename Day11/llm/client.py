from typing import Any
from openai import OpenAI
from llm.schemas import ChatMessage
from config import PROXYAPI_API_KEY, PROXYAPI_BASE_URL, REQUEST_TIMEOUT_SECONDS

client = OpenAI(
    api_key=PROXYAPI_API_KEY,
    base_url=PROXYAPI_BASE_URL,
    timeout=REQUEST_TIMEOUT_SECONDS,
)


def call_chat_completion(
    *,
    model: str,
    messages: list[ChatMessage],
    temperature: float,
    max_tokens: int,
    top_p: float,
    presence_penalty: float,
    frequency_penalty: float,
    user_id: str | None,
) -> Any:
    params: dict[str, Any] = {
        "model": model,
        "messages": [m.model_dump() for m in messages],
        "temperature": temperature,
        "top_p": top_p,
        "presence_penalty": presence_penalty,
        "frequency_penalty": frequency_penalty,
        "user": user_id,
    }

    if "gpt-5" in model:
        params["max_completion_tokens"] = max_tokens
    else:
        params["max_tokens"] = max_tokens

    return client.chat.completions.create(**params)


def extract_text_from_chat_completion(resp: Any) -> tuple[str, str | None]:
    content_parts: list[str] = []
    finish_reason = None

    if not hasattr(resp, "choices") or not resp.choices:
        return "", None

    for choice in resp.choices:
        message = getattr(choice, "message", None)
        message_content = getattr(message, "content", None)

        if isinstance(message_content, str) and message_content:
            content_parts.append(message_content)

        if finish_reason is None:
            finish_reason = getattr(choice, "finish_reason", None)

    return "\n".join(content_parts), finish_reason


def get_usage(resp: Any) -> dict[str, Any]:
    usage = getattr(resp, "usage", None)
    if not usage:
        return {}

    return {
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }