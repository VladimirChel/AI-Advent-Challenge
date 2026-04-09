from config import PROXYAPI_API_KEY
from llm_client import client
from llm_schemas import SummaryRequest


def generate_summary(request: SummaryRequest) -> str:
    if not request.prompt.strip():
        return "No data available for summary."
    if not PROXYAPI_API_KEY:
        return "Summary generation skipped: PROXYAPI_API_KEY is not configured."

    try:
        response = client.chat.completions.create(
            model=request.model,
            messages=[
                {
                    "role": "system",
                    "content": "You are a concise monitoring assistant. Summarize metrics clearly and mention notable changes.",
                },
                {
                    "role": "user",
                    "content": request.prompt,
                },
            ],
            temperature=request.temperature,
            max_tokens=request.max_tokens,
        )
    except Exception as exc:  # pragma: no cover
        return f"Summary generation failed: {exc}"

    content = response.choices[0].message.content if response.choices else ""
    return content or "Summary generation returned an empty response."
