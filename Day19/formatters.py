from __future__ import annotations

from typing import Any


def format_summary_message(summary_result: dict[str, Any], readings: list[dict[str, Any]] | None = None) -> str:
    title = _escape_html(str(summary_result.get("title") or "MQTT monitoring summary"))
    summary_text = _escape_html(str(summary_result.get("summary_text") or ""))
    stats = summary_result.get("stats") or {}
    alerts = summary_result.get("alerts") or []

    lines = [
        f"<b>{title}</b>",
        f"Sensors: {stats.get('sensor_count', 0)}",
        f"Alerts: {len(alerts)}",
    ]

    if stats.get("avg_value") is not None:
        lines.append(
            f"Min/Avg/Max: {stats.get('min_value')} / {stats.get('avg_value')} / {stats.get('max_value')} C"
        )

    if summary_text:
        lines.append("")
        lines.append(summary_text)

    if readings:
        lines.append("")
        for item in readings:
            alias = _escape_html(str(item.get("alias") or item.get("sensor_id") or "sensor"))
            value = item.get("value")
            unit = _escape_html(str(item.get("unit") or "C"))
            lines.append(f"{alias}: {value} {unit}")

    return "\n".join(lines).strip()


def format_error_message(stage: str, error: str) -> str:
    safe_stage = _escape_html(stage)
    safe_error = _escape_html(error)
    return f"<b>MQTT pipeline error</b>\nStage: {safe_stage}\nError: {safe_error}"


def _escape_html(value: str) -> str:
    return (
        value.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )
