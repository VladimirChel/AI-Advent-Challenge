from __future__ import annotations

import json
import os
import socket
import ssl
from datetime import datetime
from typing import Any
from urllib import error, parse, request


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
DEFAULT_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
DEFAULT_TIMEOUT_SECONDS = 30

WEATHER_CODE_DESCRIPTIONS = {
    0: "Clear sky",
    1: "Mainly clear",
    2: "Partly cloudy",
    3: "Overcast",
    45: "Fog",
    48: "Depositing rime fog",
    51: "Light drizzle",
    53: "Moderate drizzle",
    55: "Dense drizzle",
    56: "Light freezing drizzle",
    57: "Dense freezing drizzle",
    61: "Slight rain",
    63: "Moderate rain",
    65: "Heavy rain",
    66: "Light freezing rain",
    67: "Heavy freezing rain",
    71: "Slight snow fall",
    73: "Moderate snow fall",
    75: "Heavy snow fall",
    77: "Snow grains",
    80: "Slight rain showers",
    81: "Moderate rain showers",
    82: "Violent rain showers",
    85: "Slight snow showers",
    86: "Heavy snow showers",
    95: "Thunderstorm",
    96: "Thunderstorm with slight hail",
    99: "Thunderstorm with heavy hail",
}


def load_dotenv(dotenv_path: str | None = None) -> None:
    dotenv_path = dotenv_path or os.path.join(BASE_DIR, ".env")
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, encoding="utf-8") as dotenv_file:
        for raw_line in dotenv_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip("'\""))


class WeatherForecastClient:
    def __init__(self) -> None:
        load_dotenv()
        self._geocoding_url = os.getenv("WEATHER_GEOCODING_URL", DEFAULT_GEOCODING_URL).strip()
        self._forecast_url = os.getenv("WEATHER_FORECAST_URL", DEFAULT_FORECAST_URL).strip()
        self._default_language = os.getenv("WEATHER_DEFAULT_LANGUAGE", "en").strip() or "en"
        self._default_timezone = os.getenv("WEATHER_DEFAULT_TIMEZONE", "auto").strip() or "auto"
        self._default_forecast_days = self._int_env("WEATHER_DEFAULT_FORECAST_DAYS", 3, minimum=1, maximum=16)
        self._timeout_seconds = self._int_env("WEATHER_TIMEOUT_SECONDS", DEFAULT_TIMEOUT_SECONDS, minimum=1)
        self._user_agent = os.getenv("WEATHER_USER_AGENT", "weather-forecast-mcp/0.1.0").strip()

    def status(self) -> dict[str, Any]:
        return {
            "configured": True,
            "geocoding_url": self._geocoding_url,
            "forecast_url": self._forecast_url,
            "default_language": self._default_language,
            "default_timezone": self._default_timezone,
            "default_forecast_days": self._default_forecast_days,
            "timeout_seconds": self._timeout_seconds,
        }

    def geocode(self, location: str, count: int = 5, language: str | None = None) -> dict[str, Any]:
        normalized_location = location.strip()
        if not normalized_location:
            raise ValueError("location must not be empty")

        resolved_count = max(1, min(int(count), 10))
        params = {
            "name": normalized_location,
            "count": resolved_count,
            "language": language or self._default_language,
            "format": "json",
        }
        payload = self._get_json(self._geocoding_url, params)
        results = payload.get("results", [])

        normalized_results = [
            {
                "name": item.get("name"),
                "country": item.get("country"),
                "country_code": item.get("country_code"),
                "admin1": item.get("admin1"),
                "admin2": item.get("admin2"),
                "latitude": item.get("latitude"),
                "longitude": item.get("longitude"),
                "timezone": item.get("timezone"),
                "elevation": item.get("elevation"),
                "population": item.get("population"),
            }
            for item in results
        ]

        return {
            "query": normalized_location,
            "count": len(normalized_results),
            "results": normalized_results,
        }

    def get_current_weather(
        self,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        timezone: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        resolved_place = self._resolve_place(
            location=location,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            language=language,
        )
        params = {
            "latitude": resolved_place["latitude"],
            "longitude": resolved_place["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,rain,showers,snowfall,weather_code,cloud_cover,surface_pressure,wind_speed_10m,wind_direction_10m",
            "timezone": resolved_place["timezone"],
            "forecast_days": 1,
        }
        payload = self._get_json(self._forecast_url, params)
        return self._build_current_weather_response(payload=payload, place=resolved_place)

    def get_forecast(
        self,
        location: str | None = None,
        latitude: float | None = None,
        longitude: float | None = None,
        days: int | None = None,
        timezone: str | None = None,
        language: str | None = None,
    ) -> dict[str, Any]:
        resolved_place = self._resolve_place(
            location=location,
            latitude=latitude,
            longitude=longitude,
            timezone=timezone,
            language=language,
        )
        resolved_days = days if days is not None else self._default_forecast_days
        resolved_days = max(1, min(int(resolved_days), 16))

        params = {
            "latitude": resolved_place["latitude"],
            "longitude": resolved_place["longitude"],
            "timezone": resolved_place["timezone"],
            "forecast_days": resolved_days,
            "daily": "weather_code,temperature_2m_max,temperature_2m_min,apparent_temperature_max,apparent_temperature_min,precipitation_sum,precipitation_probability_max,wind_speed_10m_max,wind_gusts_10m_max,sunrise,sunset",
            "hourly": "temperature_2m,precipitation_probability,weather_code,wind_speed_10m",
        }
        payload = self._get_json(self._forecast_url, params)
        return self._build_forecast_response(payload=payload, place=resolved_place, days=resolved_days)

    def _resolve_place(
        self,
        location: str | None,
        latitude: float | None,
        longitude: float | None,
        timezone: str | None,
        language: str | None,
    ) -> dict[str, Any]:
        has_coordinates = latitude is not None and longitude is not None
        has_location = bool(location and location.strip())

        if not has_coordinates and not has_location:
            raise ValueError("Provide either location or both latitude and longitude")

        if has_coordinates:
            return {
                "name": location.strip() if has_location else None,
                "latitude": float(latitude),
                "longitude": float(longitude),
                "timezone": timezone or self._default_timezone,
            }

        geocoded = self.geocode(location=location or "", count=1, language=language)
        if not geocoded["results"]:
            raise RuntimeError(f"Location not found: {location}")

        match = geocoded["results"][0]
        return {
            "name": self._format_place_name(match),
            "latitude": float(match["latitude"]),
            "longitude": float(match["longitude"]),
            "timezone": timezone or match.get("timezone") or self._default_timezone,
            "geocoded_match": match,
        }

    def _build_current_weather_response(self, payload: dict[str, Any], place: dict[str, Any]) -> dict[str, Any]:
        current = payload.get("current", {})
        units = payload.get("current_units", {})
        weather_code = current.get("weather_code")

        return {
            "location": {
                "name": place.get("name"),
                "latitude": payload.get("latitude", place.get("latitude")),
                "longitude": payload.get("longitude", place.get("longitude")),
                "timezone": payload.get("timezone", place.get("timezone")),
                "timezone_abbreviation": payload.get("timezone_abbreviation"),
            },
            "current_weather": {
                "time": current.get("time"),
                "temperature": current.get("temperature_2m"),
                "temperature_unit": units.get("temperature_2m"),
                "apparent_temperature": current.get("apparent_temperature"),
                "relative_humidity": current.get("relative_humidity_2m"),
                "precipitation": current.get("precipitation"),
                "rain": current.get("rain"),
                "showers": current.get("showers"),
                "snowfall": current.get("snowfall"),
                "wind_speed": current.get("wind_speed_10m"),
                "wind_speed_unit": units.get("wind_speed_10m"),
                "wind_direction": current.get("wind_direction_10m"),
                "surface_pressure": current.get("surface_pressure"),
                "cloud_cover": current.get("cloud_cover"),
                "weather_code": weather_code,
                "weather_description": describe_weather_code(weather_code),
            },
        }

    def _build_forecast_response(
        self,
        payload: dict[str, Any],
        place: dict[str, Any],
        days: int,
    ) -> dict[str, Any]:
        daily = payload.get("daily", {})
        daily_units = payload.get("daily_units", {})
        hourly = payload.get("hourly", {})
        hourly_units = payload.get("hourly_units", {})

        daily_forecast: list[dict[str, Any]] = []
        for index, date_value in enumerate(daily.get("time", [])):
            weather_code = _value_at(daily.get("weather_code"), index)
            daily_forecast.append(
                {
                    "date": date_value,
                    "weather_code": weather_code,
                    "weather_description": describe_weather_code(weather_code),
                    "temperature_max": _value_at(daily.get("temperature_2m_max"), index),
                    "temperature_min": _value_at(daily.get("temperature_2m_min"), index),
                    "apparent_temperature_max": _value_at(daily.get("apparent_temperature_max"), index),
                    "apparent_temperature_min": _value_at(daily.get("apparent_temperature_min"), index),
                    "precipitation_sum": _value_at(daily.get("precipitation_sum"), index),
                    "precipitation_probability_max": _value_at(daily.get("precipitation_probability_max"), index),
                    "wind_speed_max": _value_at(daily.get("wind_speed_10m_max"), index),
                    "wind_gusts_max": _value_at(daily.get("wind_gusts_10m_max"), index),
                    "sunrise": _value_at(daily.get("sunrise"), index),
                    "sunset": _value_at(daily.get("sunset"), index),
                }
            )

        hourly_preview = self._select_hourly_preview(
            times=hourly.get("time", []),
            temperatures=hourly.get("temperature_2m", []),
            precipitation_probabilities=hourly.get("precipitation_probability", []),
            weather_codes=hourly.get("weather_code", []),
            wind_speeds=hourly.get("wind_speed_10m", []),
            days=days,
        )

        return {
            "location": {
                "name": place.get("name"),
                "latitude": payload.get("latitude", place.get("latitude")),
                "longitude": payload.get("longitude", place.get("longitude")),
                "timezone": payload.get("timezone", place.get("timezone")),
                "timezone_abbreviation": payload.get("timezone_abbreviation"),
            },
            "units": {
                "temperature": daily_units.get("temperature_2m_max") or hourly_units.get("temperature_2m"),
                "wind_speed": daily_units.get("wind_speed_10m_max") or hourly_units.get("wind_speed_10m"),
                "precipitation": daily_units.get("precipitation_sum"),
                "precipitation_probability": hourly_units.get("precipitation_probability"),
            },
            "forecast_days": days,
            "daily_forecast": daily_forecast,
            "hourly_preview": hourly_preview,
            "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        }

    def _select_hourly_preview(
        self,
        times: list[Any],
        temperatures: list[Any],
        precipitation_probabilities: list[Any],
        weather_codes: list[Any],
        wind_speeds: list[Any],
        days: int,
    ) -> list[dict[str, Any]]:
        preview: list[dict[str, Any]] = []
        max_hours = min(len(times), days * 24)
        for index in range(0, max_hours, 3):
            weather_code = _value_at(weather_codes, index)
            preview.append(
                {
                    "time": _value_at(times, index),
                    "temperature": _value_at(temperatures, index),
                    "precipitation_probability": _value_at(precipitation_probabilities, index),
                    "weather_code": weather_code,
                    "weather_description": describe_weather_code(weather_code),
                    "wind_speed": _value_at(wind_speeds, index),
                }
            )
        return preview

    def _get_json(self, base_url: str, params: dict[str, Any]) -> dict[str, Any]:
        query_params = {key: value for key, value in params.items() if value is not None}
        url = f"{base_url}?{parse.urlencode(query_params, doseq=True)}"
        http_request = request.Request(
            url=url,
            headers={
                "Accept": "application/json",
                "User-Agent": self._user_agent,
            },
            method="GET",
        )

        try:
            with request.urlopen(http_request, timeout=self._timeout_seconds) as response:
                response_data = response.read().decode("utf-8")
        except error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"Weather API HTTP {exc.code}: {error_body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Weather API connection error: {exc.reason}") from exc
        except ssl.SSLError as exc:
            raise RuntimeError(
                "Weather API SSL error. Check certificates, proxy/VPN settings, or HTTPS interception. "
                f"Original error: {exc}"
            ) from exc
        except socket.timeout as exc:
            raise RuntimeError(f"Weather API request timed out after {self._timeout_seconds} seconds") from exc
        except OSError as exc:
            raise RuntimeError(f"Weather API OS/network error: {exc}") from exc

        return json.loads(response_data)

    @staticmethod
    def _int_env(name: str, default: int, minimum: int | None = None, maximum: int | None = None) -> int:
        raw_value = os.getenv(name, "").strip()
        if not raw_value:
            return default
        try:
            parsed = int(raw_value)
        except ValueError:
            return default
        if minimum is not None:
            parsed = max(minimum, parsed)
        if maximum is not None:
            parsed = min(maximum, parsed)
        return parsed

    @staticmethod
    def _format_place_name(match: dict[str, Any]) -> str:
        parts = [match.get("name"), match.get("admin1"), match.get("country")]
        return ", ".join(str(part).strip() for part in parts if part)


def describe_weather_code(code: Any) -> str | None:
    try:
        if code is None:
            return None
        return WEATHER_CODE_DESCRIPTIONS.get(int(code), "Unknown weather code")
    except (TypeError, ValueError):
        return None


def _value_at(values: list[Any] | None, index: int) -> Any:
    if not values or index >= len(values):
        return None
    return values[index]
