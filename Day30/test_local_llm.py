#!/usr/bin/env python3
"""
Simple load and context-limit tester for local LLM Assistant in stateless mode.

Targets:
- burst/rate-limit behavior under parallel requests
- practical max context size for /generate

Uses only the Python standard library.
"""

from __future__ import annotations

import argparse
import html
import json
import statistics
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from typing import Any


DEFAULT_BASE_URL = "http://127.0.0.1:8000"
DEFAULT_TIMEOUT = 120


@dataclass
class RequestResult:
    ok: bool
    status: int | None
    latency_ms: int
    content: str
    error: str | None = None
    usage: dict[str, Any] | None = None
    finish_reason: str | None = None


def http_json(
    method: str,
    url: str,
    payload: dict[str, Any] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
) -> tuple[int, dict[str, Any]]:
    data = None
    headers = {"Accept": "application/json"}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            status = response.getcode()
            body = response.read().decode("utf-8", errors="replace")
            return status, json.loads(body)
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        try:
            parsed = json.loads(body)
        except json.JSONDecodeError:
            parsed = {"raw": body}
        return exc.code, parsed


def get_health(base_url: str, timeout: int) -> dict[str, Any]:
    _, body = http_json("GET", f"{base_url}/health", timeout=timeout)
    return body


def get_models(base_url: str, timeout: int, provider_id: str | None) -> dict[str, Any]:
    query = ""
    if provider_id:
        query = "?" + urllib.parse.urlencode({"provider_id": provider_id})
    _, body = http_json("GET", f"{base_url}/models{query}", timeout=timeout)
    return body


def resolve_model(base_url: str, timeout: int, explicit_model: str | None) -> str:
    if explicit_model:
        return explicit_model
    health = get_health(base_url, timeout)
    model = str(health.get("default_model") or "").strip()
    if not model:
        raise RuntimeError("Could not resolve model from /health; pass --model explicitly.")
    return model


def make_context_messages(total_chars: int, chunk_chars: int = 12000) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [
        {
            "role": "system",
            "content": (
                "You are in a limit test. Ignore filler content. "
                "When you receive the final user message, answer with exactly: CONTEXT_OK"
            ),
        }
    ]
    remaining = max(total_chars, 0)
    chunk_index = 1
    while remaining > 0:
        size = min(chunk_chars, remaining)
        filler = (f"[chunk {chunk_index}] " + ("lorem ipsum " * ((size // 12) + 4)))[:size]
        role = "user" if chunk_index % 2 else "assistant"
        messages.append({"role": role, "content": filler})
        remaining -= size
        chunk_index += 1
    messages.append({"role": "user", "content": "Reply exactly with CONTEXT_OK"})
    return messages


def send_generate(
    *,
    base_url: str,
    model: str,
    messages: list[dict[str, str]],
    timeout: int,
    max_tokens: int = 32,
    temperature: float = 0.0,
    provider_id: str | None = None,
) -> RequestResult:
    payload: dict[str, Any] = {
        "model": model,
        "messages": messages,
        "chat_mode": "default",
        "temperature": temperature,
        "max_tokens": max_tokens,
        "show_task_transition_in_chat": False,
        "mcp": {"enabled": False},
        "rag": {"enabled": False},
    }
    if provider_id:
        payload["provider_id"] = provider_id

    started = time.perf_counter()
    try:
        status, body = http_json("POST", f"{base_url}/generate", payload=payload, timeout=timeout)
        latency_ms = int((time.perf_counter() - started) * 1000)
        content = str(body.get("content") or "")
        ok = status == 200
        error = None if ok else json.dumps(body, ensure_ascii=False)
        return RequestResult(
            ok=ok,
            status=status,
            latency_ms=latency_ms,
            content=content,
            error=error,
            usage=body.get("usage") if isinstance(body, dict) else None,
            finish_reason=body.get("finish_reason") if isinstance(body, dict) else None,
        )
    except Exception as exc:  # noqa: BLE001
        latency_ms = int((time.perf_counter() - started) * 1000)
        return RequestResult(
            ok=False,
            status=None,
            latency_ms=latency_ms,
            content="",
            error=str(exc),
        )


def run_smoke_test(base_url: str, model: str, timeout: int, provider_id: str | None) -> RequestResult:
    return send_generate(
        base_url=base_url,
        model=model,
        messages=[
            {
                "role": "user",
                "content": "Reply with exactly OK",
            }
        ],
        timeout=timeout,
        provider_id=provider_id,
    )


def run_context_sweep(
    *,
    base_url: str,
    model: str,
    timeout: int,
    provider_id: str | None,
    start_chars: int,
    max_chars: int,
    step_chars: int,
) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    total_chars = start_chars

    while total_chars <= max_chars:
        messages = make_context_messages(total_chars)
        result = send_generate(
            base_url=base_url,
            model=model,
            messages=messages,
            timeout=timeout,
            provider_id=provider_id,
        )
        exact_match = result.content.strip() == "CONTEXT_OK"
        results.append(
            {
                "total_chars": total_chars,
                "message_count": len(messages),
                "ok": result.ok,
                "status": result.status,
                "latency_ms": result.latency_ms,
                "exact_match": exact_match,
                "finish_reason": result.finish_reason,
                "usage": result.usage or {},
                "error": result.error,
                "preview": result.content[:120],
            }
        )
        if not result.ok or not exact_match:
            break
        total_chars += step_chars

    return results


def run_rate_test(
    *,
    base_url: str,
    model: str,
    timeout: int,
    provider_id: str | None,
    requests_count: int,
    concurrency: int,
) -> dict[str, Any]:
    def one_call(index: int) -> dict[str, Any]:
        result = send_generate(
            base_url=base_url,
            model=model,
            messages=[
                {
                    "role": "user",
                    "content": f"Reply with exactly RATE_OK_{index}",
                }
            ],
            timeout=timeout,
            provider_id=provider_id,
        )
        exact = result.content.strip() == f"RATE_OK_{index}"
        return {
            "index": index,
            "ok": result.ok,
            "status": result.status,
            "latency_ms": result.latency_ms,
            "exact_match": exact,
            "finish_reason": result.finish_reason,
            "error": result.error,
            "preview": result.content[:120],
        }

    started = time.perf_counter()
    items: list[dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(one_call, i) for i in range(1, requests_count + 1)]
        for future in as_completed(futures):
            items.append(future.result())
    elapsed_ms = int((time.perf_counter() - started) * 1000)

    latencies = [item["latency_ms"] for item in items]
    status_counts: dict[str, int] = {}
    for item in items:
        key = str(item["status"])
        status_counts[key] = status_counts.get(key, 0) + 1

    successes = sum(1 for item in items if item["ok"])
    exact_matches = sum(1 for item in items if item["exact_match"])
    rate_limited = sum(1 for item in items if item["status"] == 429)

    return {
        "requests": requests_count,
        "concurrency": concurrency,
        "elapsed_ms": elapsed_ms,
        "successes": successes,
        "exact_matches": exact_matches,
        "rate_limited": rate_limited,
        "status_counts": status_counts,
        "latency_ms": {
            "min": min(latencies) if latencies else None,
            "p50": int(statistics.median(latencies)) if latencies else None,
            "max": max(latencies) if latencies else None,
            "avg": round(sum(latencies) / len(latencies), 1) if latencies else None,
        },
        "items": sorted(items, key=lambda item: item["index"]),
    }


def print_human_report(
    *,
    base_url: str,
    health: dict[str, Any],
    model: str,
    smoke: RequestResult,
    context_results: list[dict[str, Any]],
    rate_result: dict[str, Any],
) -> None:
    print("=== Local LLM Assistant Test ===")
    print(f"base_url: {base_url}")
    print(f"model:    {model}")
    print(f"status:   {health.get('status')}")
    print(f"memory:   {health.get('memory_enabled')}")
    print(f"stateless:{health.get('stateless_mode')}")
    print()

    print("Smoke test:")
    print(
        f"- ok={smoke.ok} status={smoke.status} latency_ms={smoke.latency_ms} "
        f"reply={smoke.content.strip()!r}"
    )
    if smoke.error:
        print(f"- error={smoke.error}")
    print()

    print("Context sweep:")
    for item in context_results:
        approx_tokens = item["total_chars"] // 4
        print(
            f"- chars={item['total_chars']} (~{approx_tokens} tok) "
            f"messages={item['message_count']} status={item['status']} "
            f"ok={item['ok']} exact={item['exact_match']} latency_ms={item['latency_ms']}"
        )
        if item["error"]:
            print(f"  error={item['error']}")
        elif not item["exact_match"]:
            print(f"  preview={item['preview']!r}")
    print()

    last_success = None
    first_failure = None
    for item in context_results:
        if item["ok"] and item["exact_match"]:
            last_success = item
        else:
            first_failure = item
            break
    print("Context conclusion:")
    if last_success:
        print(
            f"- last successful context: {last_success['total_chars']} chars "
            f"(~{last_success['total_chars'] // 4} tokens)"
        )
    if first_failure:
        print(
            f"- first failed context: {first_failure['total_chars']} chars "
            f"(~{first_failure['total_chars'] // 4} tokens), status={first_failure['status']}"
        )
    if not first_failure:
        print("- no failure reached within the configured sweep range")
    print()

    print("Rate test:")
    print(
        f"- requests={rate_result['requests']} concurrency={rate_result['concurrency']} "
        f"successes={rate_result['successes']} exact_matches={rate_result['exact_matches']} "
        f"rate_limited={rate_result['rate_limited']} elapsed_ms={rate_result['elapsed_ms']}"
    )
    print(f"- status_counts={rate_result['status_counts']}")
    print(f"- latency_ms={rate_result['latency_ms']}")
    for item in rate_result["items"]:
        if not item["ok"] or not item["exact_match"]:
            print(
                f"  request#{item['index']}: status={item['status']} ok={item['ok']} "
                f"exact={item['exact_match']} preview={item['preview']!r} error={item['error']}"
            )


def build_html_report(report: dict[str, Any]) -> str:
    health = report["health"]
    smoke = report["smoke"]
    context_results = report["context_results"]
    rate_result = report["rate_result"]

    last_success = None
    first_failure = None
    for item in context_results:
        if item["ok"] and item["exact_match"]:
            last_success = item
        else:
            first_failure = item
            break

    def esc(value: Any) -> str:
        return html.escape("" if value is None else str(value))

    def badge(ok: bool) -> str:
        color = "#18794e" if ok else "#b42318"
        bg = "#ecfdf3" if ok else "#fef3f2"
        label = "OK" if ok else "FAIL"
        return (
            f"<span style='display:inline-block;padding:2px 8px;border-radius:999px;"
            f"background:{bg};color:{color};font-weight:700'>{label}</span>"
        )

    context_rows = []
    for item in context_results:
        context_rows.append(
            "<tr>"
            f"<td>{esc(item['total_chars'])}</td>"
            f"<td>{esc(item['total_chars'] // 4)}</td>"
            f"<td>{esc(item['message_count'])}</td>"
            f"<td>{esc(item['status'])}</td>"
            f"<td>{badge(bool(item['ok']))}</td>"
            f"<td>{badge(bool(item['exact_match']))}</td>"
            f"<td>{esc(item['latency_ms'])}</td>"
            f"<td><code>{esc(item['preview'])}</code></td>"
            f"<td><code>{esc(item['error'])}</code></td>"
            "</tr>"
        )

    rate_rows = []
    for item in rate_result["items"]:
        rate_rows.append(
            "<tr>"
            f"<td>{esc(item['index'])}</td>"
            f"<td>{esc(item['status'])}</td>"
            f"<td>{badge(bool(item['ok']))}</td>"
            f"<td>{badge(bool(item['exact_match']))}</td>"
            f"<td>{esc(item['latency_ms'])}</td>"
            f"<td><code>{esc(item['preview'])}</code></td>"
            f"<td><code>{esc(item['error'])}</code></td>"
            "</tr>"
        )

    status_rows = "".join(
        f"<li><strong>{esc(code)}</strong>: {esc(count)}</li>"
        for code, count in sorted(rate_result["status_counts"].items())
    )

    summary_parts = []
    if last_success:
        summary_parts.append(
            f"Последний успешный контекст: {last_success['total_chars']} символов "
            f"(~{last_success['total_chars'] // 4} токенов)."
        )
    if first_failure:
        summary_parts.append(
            f"Первый сбой: {first_failure['total_chars']} символов "
            f"(status={first_failure['status']})."
        )
    else:
        summary_parts.append("Сбой по контексту не найден в пределах текущего диапазона.")
    if rate_result["rate_limited"]:
        summary_parts.append(f"Ответ 429 : {rate_result['rate_limited']}.")
    else:
        summary_parts.append("Ошибок 429 не обнаружено.")

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Local LLM Assistant Test Report</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f8fb;
      --panel: #ffffff;
      --text: #17202a;
      --muted: #5b6878;
      --line: #d8dee8;
      --accent: #0f6cbd;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Tahoma, sans-serif;
      background: linear-gradient(180deg, #eef4ff 0%, var(--bg) 220px);
      color: var(--text);
    }}
    .wrap {{
      max-width: 1200px;
      margin: 0 auto;
      padding: 24px;
    }}
    .hero, .panel {{
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 10px 30px rgba(17, 24, 39, 0.05);
    }}
    .hero {{
      padding: 28px;
      margin-bottom: 20px;
    }}
    h1, h2 {{ margin: 0 0 12px 0; }}
    p {{ margin: 0; line-height: 1.55; }}
    .muted {{ color: var(--muted); }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 14px;
      margin-top: 18px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 16px;
      background: #fbfdff;
    }}
    .card .k {{
      color: var(--muted);
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      margin-bottom: 8px;
    }}
    .card .v {{
      font-size: 24px;
      font-weight: 700;
    }}
    .panel {{
      padding: 22px;
      margin-bottom: 20px;
      overflow: hidden;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      font-size: 14px;
    }}
    th, td {{
      padding: 10px 12px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #f7faff;
      font-size: 12px;
      text-transform: uppercase;
      letter-spacing: 0.06em;
      color: var(--muted);
    }}
    code {{
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, "Courier New", monospace;
      font-size: 12px;
    }}
    ul {{
      margin: 10px 0 0 18px;
      padding: 0;
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <section class="hero">
      <h1>Local LLM Assistant Test Report</h1>
      <p class="muted">base_url: <code>{esc(report['base_url'])}</code> | model: <code>{esc(report['model'])}</code></p>
      <p class="muted" style="margin-top:8px;">{esc(" ".join(summary_parts))}</p>
      <div class="grid">
        <div class="card">
          <div class="k">Service Status</div>
          <div class="v">{esc(health.get('status'))}</div>
        </div>
        <div class="card">
          <div class="k">Stateless Mode</div>
          <div class="v">{esc(health.get('stateless_mode'))}</div>
        </div>
        <div class="card">
          <div class="k">Memory Enabled</div>
          <div class="v">{esc(health.get('memory_enabled'))}</div>
        </div>
        <div class="card">
          <div class="k">Smoke Test</div>
          <div class="v">{esc(smoke['status'])} / {badge(bool(smoke['ok']))}</div>
        </div>
        <div class="card">
          <div class="k">Max Successful Context</div>
          <div class="v">{esc(last_success['total_chars'] if last_success else 'n/a')}</div>
        </div>
        <div class="card">
          <div class="k">429 Count</div>
          <div class="v">{esc(rate_result['rate_limited'])}</div>
        </div>
      </div>
    </section>

    <section class="panel">
      <h2>Smoke Test</h2>
      <p class="muted">Single request sanity check before heavier probing.</p>
      <table style="margin-top:14px;">
        <thead>
          <tr>
            <th>Status</th>
            <th>OK</th>
            <th>Latency ms</th>
            <th>Reply</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{esc(smoke['status'])}</td>
            <td>{badge(bool(smoke['ok']))}</td>
            <td>{esc(smoke['latency_ms'])}</td>
            <td><code>{esc(smoke['content'])}</code></td>
            <td><code>{esc(smoke['error'])}</code></td>
          </tr>
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Context Sweep</h2>
      <p class="muted">Progressive context growth until failure or configured maximum.</p>
      <table style="margin-top:14px;">
        <thead>
          <tr>
            <th>Chars</th>
            <th>Approx Tokens</th>
            <th>Messages</th>
            <th>Status</th>
            <th>HTTP OK</th>
            <th>Exact Match</th>
            <th>Latency ms</th>
            <th>Preview</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {''.join(context_rows)}
        </tbody>
      </table>
    </section>

    <section class="panel">
      <h2>Rate Test</h2>
      <p class="muted">
        requests={esc(rate_result['requests'])},
        concurrency={esc(rate_result['concurrency'])},
        elapsed_ms={esc(rate_result['elapsed_ms'])},
        successes={esc(rate_result['successes'])},
        exact_matches={esc(rate_result['exact_matches'])}
      </p>
      <ul>{status_rows}</ul>
      <p class="muted" style="margin-top:10px;">
        latency min/p50/max/avg = {esc(rate_result['latency_ms']['min'])} /
        {esc(rate_result['latency_ms']['p50'])} /
        {esc(rate_result['latency_ms']['max'])} /
        {esc(rate_result['latency_ms']['avg'])}
      </p>
      <table style="margin-top:14px;">
        <thead>
          <tr>
            <th>#</th>
            <th>Status</th>
            <th>HTTP OK</th>
            <th>Exact Match</th>
            <th>Latency ms</th>
            <th>Preview</th>
            <th>Error</th>
          </tr>
        </thead>
        <tbody>
          {''.join(rate_rows)}
        </tbody>
      </table>
    </section>
  </div>
</body>
</html>
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Test local LLM Assistant stateless limits.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="LLM Assistant base URL.")
    parser.add_argument(
        "--model",
        default=None,
        help="Model name for testing. Default: resolve from /health.",
    )
    parser.add_argument("--provider-id", default=None, help="Optional provider_id for /generate.")
    parser.add_argument(
        "--list-models",
        action="store_true",
        help="Print models from /models for the selected provider and exit.",
    )
    parser.add_argument("--timeout", type=int, default=DEFAULT_TIMEOUT, help="Per-request timeout in seconds.")
    parser.add_argument("--context-start", type=int, default=20000, help="Initial total context chars.")
    parser.add_argument("--context-step", type=int, default=20000, help="Context increment in chars.")
    parser.add_argument("--context-max", type=int, default=200000, help="Maximum total context chars to probe.")
    parser.add_argument("--rate-requests", type=int, default=12, help="How many requests to send in the burst.")
    parser.add_argument("--rate-concurrency", type=int, default=4, help="Parallel request count.")
    parser.add_argument(
        "--json-out",
        default=None,
        help="Optional path to save full JSON report.",
    )
    parser.add_argument(
        "--html-out",
        default=None,
        help="Optional path to save HTML report.",
    )
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    base_url = args.base_url.rstrip("/")

    try:
        if args.list_models:
            models_payload = get_models(base_url, args.timeout, args.provider_id)
            provider = models_payload.get("provider_id")
            items = models_payload.get("data") or []
            print(f"provider_id: {provider}")
            if not items:
                print("No models returned.")
                return 0
            print("Available models:")
            for item in items:
                print(f"- {item.get('id')}")
            return 0
        health = get_health(base_url, args.timeout)
        model = resolve_model(base_url, args.timeout, args.model)
        smoke = run_smoke_test(base_url, model, args.timeout, args.provider_id)
        context_results = run_context_sweep(
            base_url=base_url,
            model=model,
            timeout=args.timeout,
            provider_id=args.provider_id,
            start_chars=args.context_start,
            max_chars=args.context_max,
            step_chars=args.context_step,
        )
        rate_result = run_rate_test(
            base_url=base_url,
            model=model,
            timeout=args.timeout,
            provider_id=args.provider_id,
            requests_count=args.rate_requests,
            concurrency=args.rate_concurrency,
        )
    except Exception as exc:  # noqa: BLE001
        print(f"Fatal error: {exc}", file=sys.stderr)
        return 2

    print_human_report(
        base_url=base_url,
        health=health,
        model=model,
        smoke=smoke,
        context_results=context_results,
        rate_result=rate_result,
    )

    report = {
        "base_url": base_url,
        "health": health,
        "model": model,
        "smoke": smoke.__dict__,
        "context_results": context_results,
        "rate_result": rate_result,
        "generated_at_unix": int(time.time()),
    }
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as handle:
            json.dump(report, handle, ensure_ascii=False, indent=2)
        print()
        print(f"JSON report saved to: {args.json_out}")
    if args.html_out:
        html_report = build_html_report(report)
        with open(args.html_out, "w", encoding="utf-8") as handle:
            handle.write(html_report)
        print(f"HTML report saved to: {args.html_out}")

    if not smoke.ok:
        return 1
    if rate_result["successes"] == 0:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
