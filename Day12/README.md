# LLM Assistant

LLM Assistant is a FastAPI backend for building an AI assistant with persistent memory. The service accepts chat requests, enriches them with conversation context, task state, summaries, facts, and retrieved memory fragments, then sends the assembled prompt to an LLM and stores the result back into memory.

## Project Description

This project is not just a proxy to a language model. It is an agent-oriented backend that helps the model work with ongoing conversations and long-running tasks.

The service supports:

- generation through an external LLM API;
- short-term memory from recent messages;
- working memory tied to a specific task;
- long-term memory with summaries and extracted facts;
- retrieval of relevant memory chunks for the current request;
- project invariants stored outside the dialogue and enforced as hard constraints;
- branching conversations through `conversation_id` and `branch_id`;
- response validation rules, including JSON checks and required fragments;
- storage of dialogue history and memory artifacts in PostgreSQL.

## How It Works

When a user sends a request to `/generate`, the system:

1. Loads recent dialogue history.
2. Loads project invariants from a dedicated file outside the chat history.
3. Adds task context if `task_id` is provided.
4. Restores long-term summary and sticky facts.
5. Retrieves relevant memory chunks based on the current user input.
6. Builds the final prompt and sends it to the model.
7. Runs an invariant compliance check against the draft answer.
8. Saves the assistant reply, updates task memory, extracts facts, and refreshes the conversation summary.

This makes the assistant more consistent across long dialogues and better suited for multi-step workflows.

## Main Components

- `main.py` - FastAPI application entrypoint, lifecycle, health checks, and model listing.
- `api/generate.py` - main generation endpoint and post-processing pipeline.
- `llm/` - request schemas, model client, and output validation.
- `memory/` - orchestration of short-term, working, and long-term memory.
- `invariants/` - loading, prompt injection, and compliance checks for hard project constraints.
- `repositories/` - persistence layer for messages, facts, summaries, and chunks.
- `tasks/` - task-aware memory management.
- `db.py` - PostgreSQL connection pool and schema initialization.
- `docs/assistant_invariants.json` - dedicated source of truth for architectural, technical, stack, and business invariants.

## API

### `POST /generate`

Creates an assistant response using live messages plus memory context.

Example request:

```json
{
  "conversation_id": "conv-1",
  "branch_id": "main",
  "task_id": "task-42",
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "user",
      "content": "Составь краткий план реализации"
    }
  ],
  "temperature": 0.2
}
```

Example response:

```json
{
  "request_id": "5eb7b4a4-2d7a-4d66-9e68-6c62f4d94f48",
  "conversation_id": "conv-1",
  "branch_id": "main",
  "task_id": "task-42",
  "model": "gpt-4o-mini",
  "content": "Вот краткий план реализации...",
  "latency_ms": 842,
  "short_term_used": true,
  "working_memory_used": true,
  "long_term_used": true,
  "retrieval_used": true
}
```

### `GET /health`

Returns service status, database state, default model, and current UTC time.

### `GET /models`

Returns the list of models available through the configured LLM provider.

### `GET /invariants/current`

Returns the current project invariant set loaded from the dedicated invariants file. Requires authentication.

## Tech Stack

- Python
- FastAPI
- OpenAI-compatible client
- PostgreSQL
- Psycopg + connection pooling
- Pydantic

## Configuration

The application uses environment variables from `.env`.

Key parameters:

- `PROXYAPI_API_KEY` - API key for the LLM provider;
- `PROXYAPI_BASE_URL` - base URL of the provider;
- `DEFAULT_MODEL` - default model identifier;
- `DATABASE_URL` - PostgreSQL connection string;
- `INVARIANTS_FILE` - path to the JSON file with hard project invariants;
- `REQUEST_TIMEOUT_SECONDS` - timeout for LLM requests.

## Invariants

Project invariants are stored separately from the dialogue in `docs/assistant_invariants.json`.

The backend uses them in two places:

- while assembling the system context for the main model call;
- while checking the generated answer for invariant violations before returning it.

Because of this, the assistant:

- explicitly reports which invariants were taken into account;
- refuses options that violate architecture, stack, technical, or business constraints;
- does not allow chat messages to rewrite the invariant set.

## Run

```bash
uvicorn main:app --reload
```

After startup:

- API: `http://localhost:8000`
- Swagger UI: `http://localhost:8000/docs`

## Why This Project Matters

This backend is useful as a foundation for assistants that need memory, continuity, and structured task support. It can serve as a base for internal copilots, research assistants, support bots, or agent systems where the model should remember prior context instead of answering each request in isolation.
