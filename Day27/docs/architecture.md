# Architecture

## 1. Overview

This document describes the architecture of a web chat application that works with:

- cloud LLM models via `ProxyAPI`
- local LLM models via a local runtime such as `Ollama`

The goal of the project is to provide a single chat interface where users can:

- create and manage chats
- select a provider and model
- send messages and receive streamed responses
- switch between cloud and local models without changing the user experience

The architecture is designed for an MVP first, but with room for future expansion:

- new model providers
- RAG
- auth
- multimodal inputs
- tools / function calling

## 2. Goals

### Product goals

- Provide a clean web chat UI for interacting with LLMs.
- Support both cloud and local models from one interface.
- Keep provider-specific logic out of the frontend.
- Preserve chat history and model settings.
- Support token streaming for better UX.

### Technical goals

- Introduce a unified provider abstraction.
- Isolate business logic from provider implementation details.
- Keep secrets on the backend only.
- Make it easy to add new providers later.
- Support observability, testing, and incremental scaling.

## 3. Non-goals for MVP

The following features are explicitly out of scope for the first release:

- RAG and document ingestion
- image/audio/video multimodality
- tools or function calling
- team collaboration
- complex auth and permissions
- advanced cost analytics

## 4. High-level architecture

```text
Frontend Web App
  ->
Backend API
  ->
LLM Service Layer
  ->
Provider Registry
  -> ProxyAPI Provider
  -> Local LLM Provider
       -> Ollama
```

### Responsibility split

`Frontend`

- renders chat UI
- sends user requests
- receives streamed tokens
- stores short-lived UI state

`Backend`

- stores chats and messages
- validates requests
- selects the provider adapter
- handles streaming and errors
- protects API secrets

`Provider adapters`

- convert internal requests into provider-specific API calls
- normalize responses into a common format
- expose provider health and model list

## 5. Recommended stack

### Frontend

- `Next.js`
- `TypeScript`
- `React`
- `SSE` for streaming
- `Zustand` or equivalent lightweight state store

### Backend

- `FastAPI`
- `SQLAlchemy`
- `Alembic`
- `httpx`
- `Pydantic`

### Data and infrastructure

- `PostgreSQL` for production and normal development
- `SQLite` only for local experiments
- `Docker Compose` for local orchestration
- `Nginx` optional for reverse proxy

### Local model runtime

- `Ollama` for MVP

## 6. Project structure

Recommended initial layout:

```text
project/
  frontend/
    src/
      app/
      components/
      hooks/
      lib/
      stores/
      styles/
  backend/
    app/
      api/
      core/
      db/
      providers/
      repositories/
      schemas/
      services/
      utils/
    migrations/
    tests/
  docs/
    architecture.md
  docker-compose.yml
  .env.example
```

## 7. Core backend modules

### 7.1 API layer

Handles HTTP endpoints, request validation, and response serialization.

Suggested route groups:

- `/api/chats`
- `/api/messages`
- `/api/models`
- `/api/providers`
- `/api/health`
- `/api/settings`

### 7.2 Services layer

Encapsulates business logic.

Main services:

- `ChatService`
- `MessageService`
- `ModelService`
- `StreamingService`

### 7.3 Provider layer

Contains a base provider interface and specific provider implementations:

- `BaseLlmProvider`
- `ProxyApiProvider`
- `OllamaProvider`
- `ProviderRegistry`

### 7.4 Repository layer

Encapsulates database access for:

- chats
- messages
- users
- model metadata

## 8. Unified provider abstraction

The application should not allow frontend code or business logic to depend on provider-specific request shapes.

Suggested interface:

```python
class BaseLlmProvider:
    async def list_models(self) -> list[ModelInfo]:
        ...

    async def generate(self, request: ChatRequest) -> ChatResponse:
        ...

    async def stream_generate(self, request: ChatRequest):
        ...

    async def health_check(self) -> ProviderHealth:
        ...
```

### Design rules

- Every provider must accept the same internal DTO.
- Every provider must return a normalized response shape.
- Provider-specific metadata can be attached as optional fields.
- Streaming and non-streaming flows should share the same logical request structure.

## 9. Internal DTOs

### ChatRequest

```json
{
  "chat_id": "uuid",
  "provider": "proxyapi",
  "model": "gpt-4o-mini",
  "messages": [
    { "role": "system", "content": "You are a helpful assistant." },
    { "role": "user", "content": "Hello" }
  ],
  "temperature": 0.7,
  "max_tokens": 1024,
  "stream": true
}
```

### ChatResponse

```json
{
  "message_id": "uuid",
  "provider": "proxyapi",
  "model": "gpt-4o-mini",
  "content": "Hello! How can I help?",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 45
  },
  "latency_ms": 1850,
  "finish_reason": "stop"
}
```

### ProviderHealth

```json
{
  "provider": "ollama",
  "status": "ok",
  "latency_ms": 45,
  "details": "Local runtime is reachable"
}
```

## 10. Provider implementations

### 10.1 ProxyAPI provider

Responsibilities:

- send authenticated requests to `ProxyAPI`
- normalize model metadata
- transform internal DTOs into `ProxyAPI` request format
- support standard and streaming responses
- map provider errors to application errors

Expected error classes:

- invalid credentials
- rate limit exceeded
- model unavailable
- upstream timeout
- upstream internal error

### 10.2 Local LLM provider

MVP implementation target: `Ollama`

Responsibilities:

- query local model list
- send prompts to the local endpoint
- support streaming responses
- return health status
- surface useful offline errors when the runtime is unavailable

Future local runtimes:

- `LM Studio`
- `vLLM`
- `llama.cpp server`

## 11. Database design

### 11.1 users

Used for future auth support. For MVP the application may create a default local user.

Fields:

- `id`
- `email` nullable
- `name`
- `created_at`

### 11.2 chats

Represents a conversation.

Fields:

- `id`
- `user_id`
- `title`
- `selected_provider`
- `selected_model`
- `created_at`
- `updated_at`

### 11.3 messages

Stores every message in a conversation.

Fields:

- `id`
- `chat_id`
- `role`
- `content`
- `provider`
- `model`
- `status`
- `token_input` nullable
- `token_output` nullable
- `latency_ms` nullable
- `error_text` nullable
- `created_at`

### 11.4 provider_configs

Stores provider-level metadata if needed.

Fields:

- `id`
- `provider_name`
- `base_url`
- `is_enabled`
- `created_at`
- `updated_at`

### 11.5 model_registry

Optional for MVP. Can be dynamic at first, but should exist if model metadata becomes important.

Fields:

- `id`
- `model_id`
- `display_name`
- `provider_name`
- `source_type`
- `context_window` nullable
- `supports_streaming`
- `supports_tools`
- `is_active`

## 12. Backend API design

### Chats

- `POST /api/chats` create a new chat
- `GET /api/chats` return chat list
- `GET /api/chats/{chat_id}` return a single chat with messages
- `PATCH /api/chats/{chat_id}` update title or selected model/provider
- `DELETE /api/chats/{chat_id}` delete a chat

### Messages

- `POST /api/chats/{chat_id}/messages` send a message and wait for final response
- `POST /api/chats/{chat_id}/messages/stream` send a message and stream tokens

### Models

- `GET /api/models`
- `GET /api/models?source=cloud`
- `GET /api/models?source=local`

### Providers

- `GET /api/providers/health`

### Settings

- `GET /api/settings`
- `PATCH /api/settings`

## 13. Streaming design

The recommended MVP transport is `SSE`.

### Event types

- `start`
- `token`
- `end`
- `error`

### Example event payloads

`token`

```json
{
  "type": "token",
  "chat_id": "uuid",
  "message_id": "uuid",
  "delta": "Hello"
}
```

`end`

```json
{
  "type": "end",
  "message_id": "uuid",
  "full_text": "Hello! How can I help?",
  "usage": {
    "input_tokens": 120,
    "output_tokens": 45
  }
}
```

`error`

```json
{
  "type": "error",
  "message": "Provider timeout",
  "provider": "proxyapi"
}
```

## 14. Message processing flow

1. Frontend sends user input to backend.
2. Backend creates a `user` message record.
3. Backend loads the chat history.
4. Backend resolves the selected `provider + model`.
5. `ProviderRegistry` returns the matching adapter.
6. Adapter sends the request to the upstream model.
7. Response is streamed back to the frontend.
8. Backend stores the final `assistant` message.
9. Chat metadata is updated.

## 15. Frontend architecture

### Main UI areas

- chat list sidebar
- chat message window
- message input box
- provider and model selector
- generation settings panel
- provider health indicator

### Frontend responsibilities

- render message history
- send new prompts
- process streamed tokens
- handle retry and error display
- keep current chat and settings in client state

### Suggested client state

- current chat id
- current messages
- selected provider
- selected model
- generation settings
- generation in progress flag
- last error

## 16. Security requirements

- Never expose provider secrets to the frontend.
- All provider calls must go through backend services.
- Validate message size and request payloads.
- Apply request timeouts.
- Add rate limiting for public or shared deployments.
- Redact secrets from logs.

## 17. Observability

### Logs

Log at least:

- provider name
- model id
- request outcome
- latency
- token usage when available

### Metrics

Track:

- total requests
- error rate
- average latency
- requests by provider
- requests by model

### Health checks

Expose health status for:

- backend API
- database
- `ProxyAPI`
- local runtime such as `Ollama`

## 18. Configuration

Example `.env` keys:

```env
APP_ENV=development
API_HOST=0.0.0.0
API_PORT=8000

DATABASE_URL=postgresql://user:pass@db:5432/llmchat

PROXYAPI_BASE_URL=https://example-proxyapi.local
PROXYAPI_API_KEY=replace_me

OLLAMA_BASE_URL=http://localhost:11434

DEFAULT_PROVIDER=proxyapi
DEFAULT_MODEL=gpt-4o-mini
REQUEST_TIMEOUT_SECONDS=120
```

## 19. Testing strategy

### Backend

- unit tests for provider registry
- unit tests for provider adapters with mocked upstreams
- service tests for chat and message flow
- integration tests for API endpoints

### Frontend

- message list rendering
- model switching
- streaming UI behavior
- provider error rendering

## 20. MVP scope

The first release should include only:

- chat creation and chat history
- provider and model selection
- `ProxyAPI` integration
- `Ollama` integration
- streaming responses
- basic generation settings
- provider health indicators

## 21. Future extensions

The following features should be enabled by the current architecture but implemented later:

- auth and multi-user support
- RAG
- tools / function calling
- multimodal inputs
- model comparison mode
- prompt templates
- cost dashboards

## 22. Delivery roadmap

### Phase 1

- initialize backend and frontend
- connect database
- implement chat CRUD

### Phase 2

- introduce unified provider abstraction
- implement provider registry

### Phase 3

- implement `ProxyAPI` adapter
- add standard and streaming generation

### Phase 4

- implement `Ollama` adapter
- expose local model list and health checks

### Phase 5

- finalize frontend chat UX
- add settings panel and provider state indicators

### Phase 6

- add tests, logs, and deployment polish

## 23. Summary

The core architectural decision is to place a unified provider abstraction in the backend and keep the frontend provider-agnostic. This allows the application to support both cloud models via `ProxyAPI` and local models via `Ollama` with a single user experience and a manageable implementation path.
