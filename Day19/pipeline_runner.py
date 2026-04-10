from __future__ import annotations

from typing import Any

from config import (
    MQTT_COLLECT_SERVER_SCRIPT,
    MQTT_SUMMARY_SERVER_SCRIPT,
    PIPELINE_MESSAGE_TITLE,
    PIPELINE_SEND_ENABLED,
    PIPELINE_SUMMARY_MODE,
    PIPELINE_TELEGRAM_PARSE_MODE,
    TELEGRAM_SENDER_SERVER_SCRIPT,
)
from formatters import format_error_message, format_summary_message
from mcp_client import MCPClientSession


def collect_readings() -> list[dict[str, Any]]:
    with MCPClientSession(MQTT_COLLECT_SERVER_SCRIPT) as session:
        result = session.call_tool("get_latest_temperatures", {})
        payload = session.extract_tool_payload(result)
    return payload if isinstance(payload, list) else []


def build_summary(
    readings: list[dict[str, Any]],
    *,
    title: str = PIPELINE_MESSAGE_TITLE,
    mode: str = PIPELINE_SUMMARY_MODE,
) -> dict[str, Any]:
    with MCPClientSession(MQTT_SUMMARY_SERVER_SCRIPT) as session:
        result = session.call_tool(
            "build_mqtt_summary",
            {
                "readings": readings,
                "title": title,
                "mode": mode,
            },
        )
        payload = session.extract_tool_payload(result)
    return payload if isinstance(payload, dict) else {}


def send_summary(summary_text: str) -> dict[str, Any]:
    with MCPClientSession(TELEGRAM_SENDER_SERVER_SCRIPT) as session:
        result = session.call_tool(
            "send_telegram_message",
            {
                "text": summary_text,
                "parse_mode": PIPELINE_TELEGRAM_PARSE_MODE,
            },
        )
        payload = session.extract_tool_payload(result)
    return payload if isinstance(payload, dict) else {"result": payload}


def run_pipeline(
    *,
    send_enabled: bool = PIPELINE_SEND_ENABLED,
    send_on_error: bool = False,
) -> dict[str, Any]:
    steps: dict[str, Any] = {
        "collect": {"ok": False},
        "summary": {"ok": False},
        "telegram": {"ok": False, "skipped": not send_enabled},
    }

    try:
        readings = collect_readings()
        steps["collect"] = {"ok": True, "readings_count": len(readings)}

        summary_result = build_summary(readings)
        steps["summary"] = {
            "ok": True,
            "summary_created": bool(summary_result.get("summary_text")),
            "alerts_count": len(summary_result.get("alerts") or []),
        }

        message_text = format_summary_message(summary_result, readings=None)

        telegram_result: dict[str, Any] | None = None
        if send_enabled:
            telegram_result = send_summary(message_text)
            steps["telegram"] = {"ok": True, "sent": True}

        return {
            "ok": True,
            "steps": steps,
            "readings_count": len(readings),
            "summary_result": summary_result,
            "message_text": message_text,
            "telegram_result": telegram_result,
        }
    except Exception as exc:  # noqa: BLE001
        error_stage = _detect_failed_stage(steps)
        error_message = str(exc)
        if send_enabled and send_on_error:
            try:
                send_summary(format_error_message(error_stage, error_message))
                steps["telegram"] = {"ok": True, "sent": True, "error_notification": True}
            except Exception as telegram_exc:  # noqa: BLE001
                steps["telegram"] = {
                    "ok": False,
                    "sent": False,
                    "error": f"failed to send error notification: {telegram_exc}",
                }

        return {
            "ok": False,
            "steps": steps,
            "failed_stage": error_stage,
            "error": error_message,
        }


def _detect_failed_stage(steps: dict[str, Any]) -> str:
    if not steps.get("collect", {}).get("ok"):
        return "collect"
    if not steps.get("summary", {}).get("ok"):
        return "summary"
    return "telegram"
