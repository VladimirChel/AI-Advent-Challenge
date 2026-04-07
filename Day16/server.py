from __future__ import annotations

import logging
import sys
import traceback
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from wb_mqtt_store import WireTemperatureStore


logging.basicConfig(level=logging.INFO)

SERVER_NAME = "wb-temperature-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "list_temperature_sensors",
        "description": "Returns all discovered Wireen Board temperature sensors from MQTT.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_latest_temperatures",
        "description": "Returns the latest numeric temperature values for all discovered sensors.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "get_temperature_sensor",
        "description": "Returns one temperature sensor by id. Example id: wb-msw-v4_12/Temperature.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "sensor_id": {"type": "string"},
            },
            "required": ["sensor_id"],
            "additionalProperties": False,
        },
    },
    {
        "name": "mqtt_status",
        "description": "Returns MQTT connection state and how many topics have been discovered.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
]


def success_response(request_id: Any, result: dict[str, Any]) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": "2.0",
        "id": request_id,
        "error": {
            "code": code,
            "message": message,
        },
    }


def tool_result(payload: Any) -> dict[str, Any]:
    return {
        "content": [
            {
                "type": "text",
                "text": str(payload),
            }
        ],
        "structuredContent": payload,
        "isError": False,
    }


def handle_request(message: dict[str, Any], store: WireTemperatureStore) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")

    if method == "initialize":
        return success_response(
            request_id,
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {"listChanged": False},
                },
                "serverInfo": {
                    "name": SERVER_NAME,
                    "version": SERVER_VERSION,
                },
            },
        )

    if method == "notifications/initialized":
        return None

    if method == "tools/list":
        return success_response(request_id, {"tools": TOOLS})

    if method == "tools/call":
        params = message.get("params", {})
        tool_name = params.get("name")
        arguments = params.get("arguments", {})

        if tool_name == "list_temperature_sensors":
            return success_response(request_id, tool_result(store.list_temperature_sensors()))

        if tool_name == "get_latest_temperatures":
            return success_response(request_id, tool_result(store.get_temperature_readings()))

        if tool_name == "get_temperature_sensor":
            sensor_id = arguments.get("sensor_id")
            if not sensor_id:
                return error_response(request_id, -32602, "Missing required argument: sensor_id")
            sensor = store.get_sensor(sensor_id)
            if sensor is None:
                return error_response(request_id, -32001, f"Temperature sensor not found: {sensor_id}")
            return success_response(request_id, tool_result(sensor))

        if tool_name == "mqtt_status":
            return success_response(request_id, tool_result(store.connection_info()))

        return error_response(request_id, -32601, f"Unknown tool: {tool_name}")

    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    store = WireTemperatureStore()
    try:
        store.start()
    except Exception as exc:  # noqa: BLE001
        write_log(f"Failed to start MQTT listener: {exc}")
        raise SystemExit(1) from exc

    try:
        while True:
            message = read_message(stdin=sys.stdin)
            if message is None:
                break
            if "id" not in message:
                handle_request(message, store)
                continue

            try:
                response = handle_request(message, store)
            except Exception as exc:  # noqa: BLE001
                write_log(traceback.format_exc())
                response = error_response(message.get("id"), -32000, f"Internal server error: {exc}")

            if response is not None:
                write_message(stdout=sys.stdout, message=response)
    finally:
        store.stop()


if __name__ == "__main__":
    main()
