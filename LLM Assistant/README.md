# LLM Assistant

LLM Assistant is a FastAPI backend for building an AI assistant with persistent memory. The service accepts chat requests, enriches them with conversation context, task state, summaries, facts, and retrieved memory fragments, then sends the assembled prompt to an LLM and stores the result back into memory.

## Project Description

This project is not just a proxy to a language model. It is an agent-oriented backend that helps the model work with ongoing conversations and long-running tasks.

The service supports:

- generation through an OpenAI-compatible LLM API, including local servers;
- MCP tools through one or more local `stdio` servers;
- optional Day22 RAG over FAISS artifacts from `../Day21`;
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
6. Optionally retrieves document chunks through the Day22 RAG pipeline.
7. Builds the final prompt and sends it to the model.
8. If MCP is enabled, discovers tools from one or more MCP servers and lets the model call them in a chain.
9. Runs an invariant compliance check against the draft answer.
10. Saves the assistant reply, updates task memory, extracts facts, and refreshes the conversation summary.

This makes the assistant more consistent across long dialogues and better suited for multi-step workflows.

## Main Components

- `main.py` - FastAPI application entrypoint, lifecycle, health checks, and model listing.
- `api/generate.py` - main generation endpoint and post-processing pipeline.
- `llm/` - request schemas, model client, and output validation.
- `llm/mcp_client.py` - local MCP client that starts a `stdio` server and bridges its tools into OpenAI tool calling.
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
  "temperature": 0.2,
  "rag": {
    "enabled": true
  },
  "mcp": {
    "enabled": true,
    "servers": [
      {
        "id": "ops",
        "server_script": "../Day16/server.py"
      }
    ]
  }
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
  "mcp_used": true,
  "mcp_servers": ["../Day16/server.py"],
  "mcp_tools_offered": 4,
  "mcp_tool_calls": ["ops.mqtt_status"],
  "short_term_used": true,
  "working_memory_used": true,
  "long_term_used": true,
  "retrieval_used": true,
  "rag_used": true,
  "rag_chunks_used": 5
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

You can edit the service settings from one place with the GUI configurator:

```bash
python service_config_gui.py
```

On Windows you can also run:

```cmd
config.cmd
```

The configurator groups settings by Server, LLM, Memory, RAG, and MCP. It creates a timestamped `.env` backup before saving and includes a local Ollama preset for smaller prompts.

Key parameters:

- `LLM_API_KEY` - API key for the LLM provider. Optional for local servers that ignore authorization headers. Legacy name: `PROXYAPI_API_KEY`.
- `LLM_BASE_URL` - base URL of the OpenAI-compatible provider or local server. Legacy name: `PROXYAPI_BASE_URL`.
- `DEFAULT_LLM_PROVIDER` - provider profile used when the client does not send `provider_id`.
- `LLM_PROVIDERS` - optional JSON array of OpenAI-compatible provider profiles with `id`, `base_url`, and `api_key` or `api_key_env`.
- `DEFAULT_MODEL` - default model identifier;
- `DATABASE_URL` - PostgreSQL connection string;
- `INVARIANTS_FILE` - path to the JSON file with hard project invariants;
- `REQUEST_TIMEOUT_SECONDS` - timeout for LLM requests.
- `RAG_ENABLED` - enable Day22 RAG on every `/generate` request unless overridden.
- `RAG_STRATEGY` - Day21 index strategy: `structure` or `fixed`.
- `RAG_INDEX_FILE` - optional explicit FAISS index path for Day22 RAG.
- `RAG_METADATA_FILE` - optional explicit chunks metadata path for Day22 RAG.
- `RAG_EMBED_MODEL` - embedding model used for retrieval against the Day21 index.
- `RAG_OLLAMA_URL` - Ollama base URL for embeddings.
- `RAG_MAX_CHUNKS` - how many retrieved chunks to inject into the prompt.
- `MCP_ENABLED` - enable MCP on every `/generate` request unless overridden.
- `MCP_SERVER_SCRIPT` - single default MCP server script kept for backward compatibility.
- `MCP_SERVER_SCRIPTS` - optional list of default MCP server scripts. Supports JSON array or `;`-separated paths.
- `MCP_WAIT_AFTER_START_SECONDS` - optional delay after server start before the first tool call.
- `TASK_MEMORY_ENABLED` - enable task state tracking for requests with `task_id`.
- `TASK_AUTO_ID_FOR_RAG_CHAT` - use `conversation_id` as `task_id` for `rag_task_chat` when no task id is provided.
- `TASK_REQUIRE_PLAN_APPROVAL` - block execution transitions until a plan is approved.
- `TASK_*_LIMIT` / `TASK_*_MAX_CHARS` - tune how much task context is saved and later injected into prompts.

Example `.env` values for local servers:

```env
# LM Studio
LLM_BASE_URL=http://127.0.0.1:1234/v1
LLM_API_KEY=lm-studio
DEFAULT_MODEL=local-model

# Ollama OpenAI-compatible endpoint
# LLM_BASE_URL=http://127.0.0.1:11434/v1
# LLM_API_KEY=ollama
# DEFAULT_MODEL=qwen2.5:7b-instruct

# Multiple providers selectable from llm_gui_client.py
# DEFAULT_LLM_PROVIDER=ollama
# LLM_PROVIDERS=[{"id":"ollama","base_url":"http://127.0.0.1:11434/v1","api_key":"ollama"},{"id":"cloud","base_url":"https://openai.api.proxyapi.ru/v1","api_key_env":"LLM_CLOUD_API_KEY"}]
```

Per-request Day22 RAG can be toggled through the `rag` field:

```json
{
  "rag": {
    "enabled": false
  }
}
```

## MCP

The backend can expose tools from one or more local MCP servers that speak `stdio`. For this repository, the intended smoke-test server lives in [../Day16/server.py](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/Day16/server.py).

When `mcp.enabled=true`, Day12:

- starts each configured server as a subprocess;
- reads tool lists via MCP;
- namespaces tool names as `server_id__tool_name` to avoid collisions;
- converts all discovered tools into OpenAI-compatible function tools;
- lets the model chain tool calls across different MCP servers before returning final text.

Example request for manual testing:

```json
{
  "conversation_id": "conv-mcp-1",
  "branch_id": "main",
  "model": "gpt-4o-mini",
  "messages": [
    {
      "role": "user",
      "content": "Use available tools, gather data from the connected MCP servers, and summarize the result."
    }
  ],
  "mcp": {
    "enabled": true,
    "servers": [
      {
        "id": "ops",
        "server_script": "../Day16/server.py"
      },
      {
        "id": "aux",
        "server_script": "../AnotherServer/server.py"
      }
    ]
  }
}
```

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
