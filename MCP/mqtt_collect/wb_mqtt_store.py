from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from dataclasses import asdict, dataclass, field
from typing import Any

try:
    import paho.mqtt.client as mqtt
except ModuleNotFoundError:  # pragma: no cover - depends on local environment
    mqtt = None


LOGGER = logging.getLogger(__name__)

VALUE_TOPIC_RE = re.compile(r"^/devices/([^/]+)/controls/([^/]+)$")
META_TOPIC_RE = re.compile(r"^/devices/([^/]+)/controls/([^/]+)/meta/([^/]+)$")
TEMPERATURE_NAME_RE = re.compile(r"(temp|temperature)", re.IGNORECASE)


def load_dotenv(dotenv_path: str = ".env") -> None:
    if not os.path.exists(dotenv_path):
        return

    with open(dotenv_path, encoding="utf-8") as dotenv_file:
        for raw_line in dotenv_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue

            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip("'\"")
            os.environ.setdefault(key, value)


def parse_topic_list(raw_value: str | None) -> list[str]:
    if not raw_value:
        return []

    stripped = raw_value.strip()
    if not stripped:
        return []

    try:
        parsed = json.loads(stripped)
    except json.JSONDecodeError:
        parsed = [item.strip() for item in stripped.split(",")]

    if not isinstance(parsed, list):
        raise ValueError("WB_MQTT_TOPICS must be a JSON array or a comma-separated list")

    return [str(item).strip() for item in parsed if str(item).strip()]


def parse_alias_map(raw_value: str | None) -> dict[str, str]:
    if not raw_value:
        return {}

    stripped = raw_value.strip()
    if not stripped:
        return {}

    parsed = json.loads(stripped)
    if not isinstance(parsed, dict):
        raise ValueError("WB_MQTT_ALIASES must be a JSON object")

    return {str(key): str(value) for key, value in parsed.items()}


def normalize_value_topic(topic: str) -> str:
    stripped = topic.strip()
    if not stripped:
        return stripped
    if stripped.startswith("/devices/"):
        return stripped
    if stripped.count("/") == 1:
        device_id, control_id = stripped.split("/", 1)
        return f"/devices/{device_id}/controls/{control_id}"
    return stripped


@dataclass(slots=True)
class SensorReading:
    sensor_id: str
    device_id: str
    control_id: str
    topic: str
    alias: str | None = None
    value: float | int | None = None
    units: str | None = None
    title: str | None = None
    control_type: str | None = None
    updated_at: float | None = None
    raw_payload: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_temperature(self) -> bool:
        if self.control_type and self.control_type.lower() == "temperature":
            return True
        if self.units and self.units.lower() in {"c", "°c", "deg c", "celsius"}:
            return True
        if TEMPERATURE_NAME_RE.search(self.control_id):
            return True
        if self.title and TEMPERATURE_NAME_RE.search(self.title):
            return True
        return False

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["is_temperature"] = self.is_temperature()
        return data


class WireTemperatureStore:
    def __init__(self) -> None:
        load_dotenv()
        self._lock = threading.RLock()
        self._readings: dict[str, SensorReading] = {}
        self._client: Any = None
        self._connected = threading.Event()
        self._stopping = False
        self._value_topics = [normalize_value_topic(topic) for topic in parse_topic_list(os.getenv("WB_MQTT_TOPICS"))]
        self._aliases = parse_alias_map(os.getenv("WB_MQTT_ALIASES"))

    def start(self) -> None:
        if mqtt is None:
            raise RuntimeError(
                "Missing dependency 'paho-mqtt'. Install it with: pip install -r requirements.txt"
            )

        host = os.getenv("WB_MQTT_HOST", "127.0.0.1")
        port = int(os.getenv("WB_MQTT_PORT", "1883"))
        username = os.getenv("WB_MQTT_USERNAME")
        password = os.getenv("WB_MQTT_PASSWORD")
        client_id = os.getenv("WB_MQTT_CLIENT_ID", "wb-temperature-mcp")
        keepalive = int(os.getenv("WB_MQTT_KEEPALIVE", "60"))

        client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
        if username:
            client.username_pw_set(username, password=password)

        client.on_connect = self._on_connect
        client.on_message = self._on_message
        client.on_disconnect = self._on_disconnect

        client.connect_async(host, port=port, keepalive=keepalive)
        client.loop_start()
        self._client = client

    def stop(self) -> None:
        if not self._client:
            return
        self._stopping = True
        self._client.disconnect()
        self._client.loop_stop()
        self._client = None

    def connection_info(self) -> dict[str, Any]:
        return {
            "mqtt_connected": self._connected.is_set(),
            "sensor_count": len(self.list_temperature_sensors()),
            "total_topics_seen": len(self._readings),
            "subscribed_topics": self._subscription_topics(),
        }

    def list_temperature_sensors(self) -> list[dict[str, Any]]:
        with self._lock:
            sensors = [reading.to_dict() for reading in self._readings.values() if reading.is_temperature()]
        sensors.sort(key=lambda item: item["sensor_id"])
        return sensors

    def get_temperature_readings(self) -> list[dict[str, Any]]:
        with self._lock:
            readings = [
                reading.to_dict()
                for reading in self._readings.values()
                if reading.is_temperature() and reading.value is not None
            ]
        readings.sort(key=lambda item: item["sensor_id"])
        return readings

    def get_sensor(self, sensor_id: str) -> dict[str, Any] | None:
        with self._lock:
            reading = self._readings.get(sensor_id)
            if not reading or not reading.is_temperature():
                return None
            return reading.to_dict()

    def _on_connect(
        self,
        client: mqtt.Client,
        userdata: Any,
        flags: mqtt.ConnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        if reason_code.is_failure:
            LOGGER.error("MQTT connection failed: %s", reason_code)
            self._connected.clear()
            return

        LOGGER.info("Connected to MQTT broker")
        self._connected.set()
        for topic in self._subscription_topics():
            client.subscribe(topic)

    def _on_disconnect(
        self,
        client: mqtt.Client,
        userdata: Any,
        disconnect_flags: mqtt.DisconnectFlags,
        reason_code: mqtt.ReasonCode,
        properties: mqtt.Properties | None,
    ) -> None:
        self._connected.clear()
        if self._stopping:
            LOGGER.info("Disconnected from MQTT broker")
            return
        reason_text = str(reason_code)
        if reason_text == "Unspecified error":
            LOGGER.info("Disconnected from MQTT broker: %s", reason_code)
            return
        LOGGER.warning("Disconnected from MQTT broker: %s", reason_code)

    def _on_message(self, client: mqtt.Client, userdata: Any, message: mqtt.MQTTMessage) -> None:
        topic = message.topic
        payload_text = message.payload.decode("utf-8", errors="replace").strip()

        if match := VALUE_TOPIC_RE.match(topic):
            device_id, control_id = match.groups()
            sensor_id = f"{device_id}/{control_id}"
            value = self._parse_payload(payload_text)
            with self._lock:
                reading = self._readings.get(sensor_id) or SensorReading(
                    sensor_id=sensor_id,
                    device_id=device_id,
                    control_id=control_id,
                    topic=topic,
                )
                reading.alias = self._resolve_alias(sensor_id=sensor_id, topic=topic)
                reading.value = value
                reading.updated_at = time.time()
                reading.raw_payload = payload_text
                self._readings[sensor_id] = reading
            return

        if match := META_TOPIC_RE.match(topic):
            device_id, control_id, meta_key = match.groups()
            sensor_id = f"{device_id}/{control_id}"
            with self._lock:
                reading = self._readings.get(sensor_id) or SensorReading(
                    sensor_id=sensor_id,
                    device_id=device_id,
                    control_id=control_id,
                    topic=f"/devices/{device_id}/controls/{control_id}",
                )
                reading.alias = self._resolve_alias(sensor_id=sensor_id, topic=reading.topic)
                self._apply_meta(reading, meta_key, payload_text)
                self._readings[sensor_id] = reading

    def _apply_meta(self, reading: SensorReading, meta_key: str, payload_text: str) -> None:
        if meta_key == "type":
            reading.control_type = payload_text
            return
        if meta_key == "units":
            reading.units = payload_text
            return
        if meta_key == "title":
            try:
                title_data = json.loads(payload_text)
                if isinstance(title_data, dict):
                    reading.title = next(iter(title_data.values()), payload_text)
                else:
                    reading.title = str(title_data)
            except json.JSONDecodeError:
                reading.title = payload_text
            return

        reading.metadata[meta_key] = payload_text

    @staticmethod
    def _parse_payload(payload_text: str) -> float | int | None:
        if payload_text == "":
            return None
        try:
            numeric = float(payload_text)
        except ValueError:
            return None
        if numeric.is_integer():
            return int(numeric)
        return numeric

    def _subscription_topics(self) -> list[str]:
        if not self._value_topics:
            return ["/devices/+/controls/+", "/devices/+/controls/+/meta/+"]

        topics: list[str] = []
        for value_topic in self._value_topics:
            topics.append(value_topic)
            if not value_topic.endswith("/meta/+"):
                topics.append(f"{value_topic}/meta/+")
        return topics

    def _resolve_alias(self, sensor_id: str, topic: str) -> str | None:
        return self._aliases.get(sensor_id) or self._aliases.get(topic)
