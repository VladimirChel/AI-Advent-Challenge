from __future__ import annotations

from typing import Any

from mcp_client import MCPClientSession
from repository_readings import insert_sensor_readings


def collect_latest_temperature_readings() -> dict[str, Any]:
    with MCPClientSession() as session:
        result = session.call_tool("get_latest_temperatures", {})
        payload = session.extract_tool_payload(result)

    readings = payload if isinstance(payload, list) else []
    inserted = insert_sensor_readings(readings)
    return {
        "readings_received": len(readings),
        "readings_inserted": inserted,
    }
