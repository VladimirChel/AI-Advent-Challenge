# Day19 MCP Pipeline

Day19 orchestrates a simple automatic pipeline built from three MCP servers:

1. `mqtt_collect` collects the latest MQTT readings
2. `mqtt_summary` builds a human-readable summary
3. `telegram_sender` sends the final message to Telegram

## Flow

```text
mqtt_collect -> mqtt_summary -> telegram_sender
```

## Files

- `config.py` - pipeline configuration and MCP server paths
- `mcp_client.py` - reusable MCP client session over `stdio`
- `pipeline_runner.py` - orchestration logic for collect, summarize, send
- `formatters.py` - Telegram-ready HTML formatting
- `run_pipeline.py` - CLI entrypoint

## Run

```bash
python run_pipeline.py --dry-run
python run_pipeline.py
python run_pipeline.py --send-on-error
```

## Environment

Copy `.env.example` and adjust paths or behavior if needed.

The Telegram bot configuration itself still lives in `../MCP/telegram_sender/.env`.
