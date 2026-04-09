# Day18 Scheduled Agent

Day18 is a 24/7 agent service that periodically collects sensor data through the MCP server from `Day16`, stores raw readings in PostgreSQL, builds aggregated metrics, and generates regular summaries with an LLM using the patterns from `Day12`.

## Features

- periodic data collection from an MCP tool source;
- PostgreSQL storage for raw readings, aggregates, summaries, and job runs;
- background scheduler with independent collection, aggregation, and summary jobs;
- REST API for latest readings, aggregate windows, summaries, and agent status.

## Run

1. Copy `.env.example` to `.env`
2. Fill in `DATABASE_URL` and `PROXYAPI_API_KEY`
3. Install dependencies
4. Start the API:

```bash
uvicorn main:app --reload --port 8018
```

## Main Flow

1. `collect_readings_job` calls `get_latest_temperatures` from `../Day16/server.py`
2. Raw readings are written to PostgreSQL
3. `aggregate_readings_job` computes `min/max/avg/last` windows
4. `generate_summary_job` builds a compact summary from fresh aggregates
5. API endpoints return the latest agent state and aggregated result
