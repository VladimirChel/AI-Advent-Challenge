from __future__ import annotations

import logging
import sys
from typing import Any

from mcp_stdio import read_message, write_log, write_message
from weather_service import WeatherForecastClient


logging.basicConfig(level=logging.INFO)

SERVER_NAME = "weather-forecast-mcp"
SERVER_VERSION = "0.1.0"

TOOLS = [
    {
        "name": "weather_status",
        "description": "Returns weather API configuration and default settings.",
        "inputSchema": {
            "type": "object",
            "properties": {},
            "additionalProperties": False,
        },
    },
    {
        "name": "weather_geocode",
        "description": "Finds city or settlement coordinates by human-readable location name.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "count": {"type": "integer"},
                "language": {"type": "string"},
            },
            "required": ["location"],
            "additionalProperties": False,
        },
    },
    {
        "name": "get_current_weather",
        "description": "Returns current weather by location name or by latitude and longitude.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "timezone": {"type": "string"},
                "language": {"type": "string"},
            },
            "additionalProperties": False,
        },
    },
    {
        "name": "get_weather_forecast",
        "description": "Returns daily forecast and a 3-hour preview by location name or coordinates.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "location": {"type": "string"},
                "latitude": {"type": "number"},
                "longitude": {"type": "number"},
                "days": {"type": "integer"},
                "timezone": {"type": "string"},
                "language": {"type": "string"},
            },
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


def handle_request(message: dict[str, Any], weather: WeatherForecastClient) -> dict[str, Any] | None:
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

        if tool_name == "weather_status":
            return success_response(request_id, tool_result(weather.status()))

        if tool_name == "weather_geocode":
            location = arguments.get("location")
            if not location:
                return error_response(request_id, -32602, "Missing required argument: location")
            result = weather.geocode(
                location=location,
                count=int(arguments.get("count", 5)),
                language=arguments.get("language"),
            )
            return success_response(request_id, tool_result(result))

        if tool_name == "get_current_weather":
            result = weather.get_current_weather(
                location=arguments.get("location"),
                latitude=arguments.get("latitude"),
                longitude=arguments.get("longitude"),
                timezone=arguments.get("timezone"),
                language=arguments.get("language"),
            )
            return success_response(request_id, tool_result(result))

        if tool_name == "get_weather_forecast":
            result = weather.get_forecast(
                location=arguments.get("location"),
                latitude=arguments.get("latitude"),
                longitude=arguments.get("longitude"),
                days=arguments.get("days"),
                timezone=arguments.get("timezone"),
                language=arguments.get("language"),
            )
            return success_response(request_id, tool_result(result))

        return error_response(request_id, -32601, f"Unknown tool: {tool_name}")

    return error_response(request_id, -32601, f"Method not found: {method}")


def main() -> None:
    weather = WeatherForecastClient()

    while True:
        message = read_message(stdin=sys.stdin)
        if message is None:
            break
        if "id" not in message:
            handle_request(message, weather)
            continue

        try:
            response = handle_request(message, weather)
        except Exception as exc:  # noqa: BLE001
            write_log(f"Tool call failed: {exc}")
            response = error_response(message.get("id"), -32000, str(exc))

        if response is not None:
            write_message(stdout=sys.stdout, message=response)


if __name__ == "__main__":
    main()
