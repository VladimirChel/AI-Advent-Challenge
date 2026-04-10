from __future__ import annotations

import os
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent


def _load_dotenv_if_present() -> None:
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv_if_present()

MQTT_COLLECT_SERVER_SCRIPT = Path(
    os.getenv("MQTT_COLLECT_SERVER_SCRIPT", "../MCP/mqtt_collect/server.py")
).resolve()
MQTT_SUMMARY_SERVER_SCRIPT = Path(
    os.getenv("MQTT_SUMMARY_SERVER_SCRIPT", "../MCP/mqtt_summary/server.py")
).resolve()
TELEGRAM_SENDER_SERVER_SCRIPT = Path(
    os.getenv("TELEGRAM_SENDER_SERVER_SCRIPT", "../MCP/telegram_sender/server.py")
).resolve()

MCP_WAIT_AFTER_START_SECONDS = float(os.getenv("MCP_WAIT_AFTER_START_SECONDS", "3"))
MCP_TOOL_CALL_TIMEOUT_SECONDS = float(os.getenv("MCP_TOOL_CALL_TIMEOUT_SECONDS", "20"))

PIPELINE_SEND_ENABLED = os.getenv("PIPELINE_SEND_ENABLED", "true").strip().lower() in {
    "1",
    "true",
    "yes",
    "on",
}
PIPELINE_TELEGRAM_PARSE_MODE = os.getenv("PIPELINE_TELEGRAM_PARSE_MODE", "HTML").strip()
PIPELINE_MESSAGE_TITLE = os.getenv("PIPELINE_MESSAGE_TITLE", "MQTT monitoring summary").strip()
PIPELINE_SUMMARY_MODE = os.getenv("PIPELINE_SUMMARY_MODE", "brief").strip()
