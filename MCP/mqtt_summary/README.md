# MQTT Summary MCP Server

`mqtt_summary` is a lightweight MCP server over `stdio` that receives MQTT readings and turns them into a deterministic human-readable summary.

## Tools

- `mqtt_summary_status` - returns server status and supported summary modes.
- `build_mqtt_summary` - accepts MQTT readings and returns summary text, stats, and alerts.

## Input

`build_mqtt_summary` expects:

```json
{
  "readings": [
    {
      "sensor_id": "wb-msw-v4_12/Temperature",
      "alias": "Kitchen",
      "value": 23.4,
      "unit": "C",
      "updated_at": "2026-04-10T10:15:00Z"
    }
  ],
  "title": "MQTT monitoring summary",
  "mode": "brief",
  "thresholds": {
    "min_value": 18,
    "max_value": 30
  }
}
```

## Run

```bash
python server.py
python client.py status
python client.py summary --readings-file sample.json
```
