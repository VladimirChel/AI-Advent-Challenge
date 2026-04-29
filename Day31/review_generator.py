from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass

from pr_context import PullRequestContext
from pr_retriever import RetrievedChunk

MAX_PROMPT_CHARS = 45_000
MAX_DIFF_CHARS = 12_000
MAX_PATCH_CHARS_PER_FILE = 3_000
MAX_TOTAL_PATCH_CHARS = 12_000
MAX_CHUNK_TEXT_CHARS = 700
MAX_TOTAL_DOC_CONTEXT_CHARS = 4_000
MAX_TOTAL_CODE_CONTEXT_CHARS = 6_000


@dataclass(slots=True)
class ReviewResult:
    markdown: str
    raw_response: str


def _truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[:limit] + "\n...[truncated]"


def _format_chunks(title: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return f"{title}\n- none"

    lines = [title]
    total_chars = 0
    total_limit = MAX_TOTAL_DOC_CONTEXT_CHARS if "documentation" in title.lower() else MAX_TOTAL_CODE_CONTEXT_CHARS
    for chunk in chunks:
        snippet = _truncate(chunk.text.strip(), MAX_CHUNK_TEXT_CHARS)
        entry = (
            f"- {chunk.source} | {chunk.section} | score={chunk.score}\n```text\n{snippet}\n```"
        )
        if total_chars + len(entry) > total_limit:
            break
        lines.append(
            entry
        )
        total_chars += len(entry)
    return "\n".join(lines)


def build_review_prompt(
    *,
    context: PullRequestContext,
    docs_chunks: list[RetrievedChunk],
    code_chunks: list[RetrievedChunk],
) -> str:
    changed_files_summary = "\n".join(
        f"- {item.status} {item.path}" for item in context.changed_files
    ) or "- none"
    per_file_patches = []
    total_patch_chars = 0
    for item in context.changed_files:
        if total_patch_chars >= MAX_TOTAL_PATCH_CHARS:
            break
        patch_body = _truncate(item.patch, MAX_PATCH_CHARS_PER_FILE)
        entry = f"FILE: {item.path} ({item.status})\n```diff\n{patch_body}\n```"
        per_file_patches.append(entry)
        total_patch_chars += len(entry)

    prompt = f"""You are reviewing a pull request for bugs, architecture risks, and actionable improvements.

Return valid JSON with this exact schema:
{{
  "summary": "short overview",
  "potential_bugs": ["..."],
  "architecture_concerns": ["..."],
  "recommendations": ["..."]
}}

Rules:
- Write all user-facing text in Russian.
- Focus on correctness, regressions, missing edge cases, architecture mismatches, and maintainability risks.
- Do not spend space on style-only comments.
- If something is uncertain, say so explicitly.
- If a section has no issues, return an empty array.

PR metadata:
- base_ref: {context.base_ref}
- head_ref: {context.head_ref}
- merge_base: {context.merge_base}

Changed files:
{changed_files_summary}

Global diff:
```diff
{_truncate(context.diff_text, MAX_DIFF_CHARS)}
```

Per-file patches:
{chr(10).join(per_file_patches)}

{_format_chunks("Relevant documentation chunks:", docs_chunks)}

{_format_chunks("Relevant code chunks:", code_chunks)}
"""
    return _truncate(prompt, MAX_PROMPT_CHARS)


def _post_llm_assistant_generate(
    *,
    base_url: str,
    token: str,
    provider_id: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
) -> str:
    endpoint = base_url.rstrip("/") + "/generate"
    payload = {
        "conversation_id": str(uuid.uuid4()),
        "branch_id": "pr-review",
        "task_id": None,
        "provider_id": provider_id or None,
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "top_p": 1.0,
        "show_task_transition_in_chat": False,
        "validation": {"require_json": False},
        "project": None,
        "rag": {"enabled": False},
        "mcp": {"enabled": False},
    }
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {error_body}") from exc
    parsed = json.loads(body)
    return str(parsed.get("content") or "").strip()


def _extract_json_object(text: str) -> dict[str, object]:
    stripped = text.strip()
    try:
        payload = json.loads(stripped)
        if isinstance(payload, dict):
            return payload
    except json.JSONDecodeError:
        pass

    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise json.JSONDecodeError("No JSON object found", stripped, 0)

    candidate = stripped[start:end + 1]
    payload = json.loads(candidate)
    if not isinstance(payload, dict):
        raise json.JSONDecodeError("Top-level JSON value is not an object", candidate, 0)
    return payload


def _render_markdown(review_payload: dict[str, object]) -> str:
    summary = str(review_payload.get("summary") or "Автоматическое ревью PR завершено.")

    def render_section(title: str, key: str) -> str:
        values = review_payload.get(key)
        items = values if isinstance(values, list) else []
        if not items:
            return f"## {title}\n- Существенных проблем не обнаружено."
        lines = [f"## {title}"]
        for item in items:
            lines.append(f"- {item}")
        return "\n".join(lines)

    parts = [
        "# AI-ревью PR",
        summary,
        render_section("Потенциальные баги", "potential_bugs"),
        render_section("Архитектурные замечания", "architecture_concerns"),
        render_section("Рекомендации", "recommendations"),
    ]
    return "\n\n".join(parts).strip() + "\n"


def generate_review(
    *,
    context: PullRequestContext,
    docs_chunks: list[RetrievedChunk],
    code_chunks: list[RetrievedChunk],
    dry_run: bool = False,
) -> ReviewResult:
    prompt = build_review_prompt(context=context, docs_chunks=docs_chunks, code_chunks=code_chunks)

    if dry_run:
        sample = {
            "summary": "Режим dry-run вернул заглушку вместо реального ревью.",
            "potential_bugs": ["Генерация ревью пропущена, потому что включён режим dry-run."],
            "architecture_concerns": [],
            "recommendations": ["Отключите dry-run и настройте локальный endpoint LLM Assistant для получения реального ревью."],
        }
        return ReviewResult(markdown=_render_markdown(sample), raw_response=json.dumps(sample, ensure_ascii=False))

    assistant_url = os.getenv("LLM_ASSISTANT_URL", "").strip()
    assistant_token = os.getenv("LLM_ASSISTANT_TOKEN", "").strip()
    assistant_provider_id = os.getenv("LLM_ASSISTANT_PROVIDER_ID", "").strip()
    assistant_model = os.getenv("LLM_ASSISTANT_MODEL", "").strip()
    temperature = float(os.getenv("PR_REVIEW_TEMPERATURE", "0.1"))
    max_tokens = int(os.getenv("PR_REVIEW_MAX_TOKENS", "1800"))

    if not assistant_url:
        fallback = {
            "summary": "Не удалось сгенерировать ревью.",
            "potential_bugs": ["Не задан LLM_ASSISTANT_URL."],
            "architecture_concerns": [],
            "recommendations": [
                "Задайте LLM_ASSISTANT_URL перед запуском PR-review.",
                "Например, в PowerShell: $env:LLM_ASSISTANT_URL='http://127.0.0.1:8000'",
            ],
        }
        return ReviewResult(markdown=_render_markdown(fallback), raw_response="missing LLM_ASSISTANT_URL")

    try:
        raw_response = _post_llm_assistant_generate(
            base_url=assistant_url,
            token=assistant_token,
            provider_id=assistant_provider_id,
            model=assistant_model,
            prompt=prompt,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        payload = _extract_json_object(raw_response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, RuntimeError) as exc:
        fallback = {
            "summary": "Не удалось сгенерировать ревью.",
            "potential_bugs": [f"Ошибка вызова LLM: {exc}"],
            "architecture_concerns": [],
            "recommendations": [
                "Проверьте, что LLM Assistant доступен с self-hosted runner и что настроенный provider/model возвращает корректный JSON.",
            ],
        }
        return ReviewResult(markdown=_render_markdown(fallback), raw_response=str(exc))

    return ReviewResult(markdown=_render_markdown(payload), raw_response=raw_response)
