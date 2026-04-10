from __future__ import annotations

from statistics import mean
from typing import Any


def build_summary(
    readings: list[dict[str, Any]],
    title: str | None = None,
    mode: str = "brief",
    thresholds: dict[str, Any] | None = None,
) -> dict[str, Any]:
    normalized = normalize_readings(readings)
    stats = compute_stats(normalized)
    alerts = detect_alerts(normalized, thresholds=thresholds)
    summary_text = render_deterministic_summary(
        readings=normalized,
        stats=stats,
        alerts=alerts,
        title=title or "MQTT monitoring summary",
        mode=mode,
    )
    return {
        "summary_text": summary_text,
        "stats": stats,
        "alerts": alerts,
        "mode": mode,
        "title": title or "MQTT monitoring summary",
    }


def normalize_readings(readings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    for item in readings:
        if not isinstance(item, dict):
            continue

        sensor_id = str(item.get("sensor_id") or item.get("topic") or "").strip()
        if not sensor_id:
            continue

        raw_value = item.get("value")
        try:
            value = float(raw_value)
        except (TypeError, ValueError):
            continue

        alias = str(item.get("alias") or sensor_id).strip()
        unit = str(item.get("unit") or "C").strip()
        updated_at = str(item.get("updated_at") or item.get("timestamp") or "").strip()

        normalized.append(
            {
                "sensor_id": sensor_id,
                "alias": alias,
                "value": value,
                "unit": unit,
                "updated_at": updated_at,
            }
        )

    normalized.sort(key=lambda item: item["alias"].lower())
    return normalized


def compute_stats(readings: list[dict[str, Any]]) -> dict[str, Any]:
    values = [item["value"] for item in readings]
    if not values:
        return {
            "sensor_count": 0,
            "min_value": None,
            "max_value": None,
            "avg_value": None,
        }

    return {
        "sensor_count": len(values),
        "min_value": round(min(values), 2),
        "max_value": round(max(values), 2),
        "avg_value": round(mean(values), 2),
    }


def detect_alerts(
    readings: list[dict[str, Any]],
    thresholds: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    thresholds = thresholds or {}
    min_value = _float_or_none(thresholds.get("min_value"))
    max_value = _float_or_none(thresholds.get("max_value"))

    alerts: list[dict[str, Any]] = []
    for item in readings:
        value = item["value"]
        if min_value is not None and value < min_value:
            alerts.append(
                {
                    "sensor_id": item["sensor_id"],
                    "alias": item["alias"],
                    "value": value,
                    "kind": "below_min",
                    "threshold": min_value,
                }
            )
        if max_value is not None and value > max_value:
            alerts.append(
                {
                    "sensor_id": item["sensor_id"],
                    "alias": item["alias"],
                    "value": value,
                    "kind": "above_max",
                    "threshold": max_value,
                }
            )
    return alerts


def render_deterministic_summary(
    readings: list[dict[str, Any]],
    stats: dict[str, Any],
    alerts: list[dict[str, Any]],
    title: str,
    mode: str,
) -> str:
    if not readings:
        return f"{title}\nNo readings were received from mqtt_collect."

    lines = [
        title,
        f"Sensors: {stats['sensor_count']}",
        f"Min/Avg/Max: {stats['min_value']} / {stats['avg_value']} / {stats['max_value']} C",
        f"Alerts: {len(alerts)}",
        "",
    ]

    if mode == "compact":
        sensor_line = ", ".join(f"{item['alias']}: {item['value']} {item['unit']}" for item in readings)
        lines.append(sensor_line)
        return "\n".join(lines).strip()

    for item in readings:
        suffix = f" ({item['updated_at']})" if item["updated_at"] else ""
        lines.append(f"{item['alias']}: {item['value']} {item['unit']}{suffix}")

    if alerts:
        lines.append("")
        lines.append("Alerts:")
        for alert in alerts:
            direction = "below" if alert["kind"] == "below_min" else "above"
            lines.append(
                f"- {alert['alias']}: {alert['value']} C is {direction} threshold {alert['threshold']} C"
            )

    return "\n".join(lines).strip()


def _float_or_none(value: Any) -> float | None:
    try:
        if value is None or value == "":
            return None
        return float(value)
    except (TypeError, ValueError):
        return None
