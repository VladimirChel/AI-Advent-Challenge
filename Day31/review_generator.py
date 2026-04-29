from __future__ import annotations

import json
import os
import uuid
import urllib.error
import urllib.request
from dataclasses import dataclass

from pr_context import PullRequestContext
from pr_retriever import RetrievedChunk


@dataclass(slots=True)
class ReviewResult:
    markdown: str
    raw_response: str


def _format_chunks(title: str, chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return f"{title}\n- none"

    lines = [title]
    for chunk in chunks:
        snippet = chunk.text.strip()
        if len(snippet) > 1_200:
            snippet = snippet[:1_200] + "\n..."
        lines.append(
            f"- {chunk.source} | {chunk.section} | score={chunk.score}\n```text\n{snippet}\n```"
        )
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
    for item in context.changed_files:
        per_file_patches.append(f"FILE: {item.path} ({item.status})\n```diff\n{item.patch}\n```")

    return f"""You are reviewing a pull request for bugs, architecture risks, and actionable improvements.

Return valid JSON with this exact schema:
{{
  "summary": "short overview",
  "potential_bugs": ["..."],
  "architecture_concerns": ["..."],
  "recommendations": ["..."]
}}

Rules:
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
{context.diff_text}
```

Per-file patches:
{chr(10).join(per_file_patches)}

{_format_chunks("Relevant documentation chunks:", docs_chunks)}

{_format_chunks("Relevant code chunks:", code_chunks)}
"""


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
        "validation": {"require_json": True},
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
    with urllib.request.urlopen(request, timeout=180) as response:
        body = response.read().decode("utf-8")
    parsed = json.loads(body)
    return str(parsed.get("content") or "").strip()


def _render_markdown(review_payload: dict[str, object]) -> str:
    summary = str(review_payload.get("summary") or "Automated PR review completed.")

    def render_section(title: str, key: str) -> str:
        values = review_payload.get(key)
        items = values if isinstance(values, list) else []
        if not items:
            return f"## {title}\n- No major issues found."
        lines = [f"## {title}"]
        for item in items:
            lines.append(f"- {item}")
        return "\n".join(lines)

    parts = [
        "# AI PR Review",
        summary,
        render_section("Potential bugs", "potential_bugs"),
        render_section("Architecture concerns", "architecture_concerns"),
        render_section("Recommendations", "recommendations"),
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
            "summary": "Dry-run mode produced a placeholder review.",
            "potential_bugs": ["Review generation was skipped because dry-run mode is enabled."],
            "architecture_concerns": [],
            "recommendations": ["Disable dry-run and configure the local LLM Assistant endpoint to get real review output."],
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
            "summary": "Review generation failed.",
            "potential_bugs": ["LLM_ASSISTANT_URL is not configured."],
            "architecture_concerns": [],
            "recommendations": [
                "Set LLM_ASSISTANT_URL before running PR review.",
                "For example in PowerShell: $env:LLM_ASSISTANT_URL='http://127.0.0.1:8000'",
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
        payload = json.loads(raw_response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
        fallback = {
            "summary": "Review generation failed.",
            "potential_bugs": [f"LLM call failed: {exc}"],
            "architecture_concerns": [],
            "recommendations": [
                "Verify that LLM Assistant is reachable from the self-hosted runner and that the configured provider/model can return valid JSON.",
            ],
        }
        return ReviewResult(markdown=_render_markdown(fallback), raw_response=str(exc))

    return ReviewResult(markdown=_render_markdown(payload), raw_response=raw_response)
