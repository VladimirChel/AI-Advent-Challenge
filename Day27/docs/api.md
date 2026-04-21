# API Specification

## 1. Overview

This document defines the backend API for the LLM chat web application.

Base path:

```text
/api
```

Primary goals:

- support chat CRUD
- send messages to cloud and local LLMs
- support streaming responses
- expose model and provider metadata

## 2. General conventions

### Content type

Standard JSON requests and responses:

```http
Content-Type: application/json
```

Streaming endpoint:

```http
Content-Type: text/event-stream
```

### IDs

All resource identifiers use `UUID`.

### Timestamps

All timestamps should be returned in ISO 8601 format.

Example:

```json
"2026-04-21T12:30:45Z"
```

### Error shape

All non-streaming errors should use a common JSON structure:

```json
{
  "error": {
    "code": "provider_timeout",
    "message": "The selected provider did not respond in time.",
    "details": null
  }
}
```

## 3. Shared schemas

### Chat

```json
{
  "id": "uuid",
  "title": "New chat",
  "selected_provider": "proxyapi",
  "selected_model": "gpt-4o-mini",
  "created_at": "2026-04-21T12:30:45Z",
  "updated_at": "2026-04-21T12:35:10Z"
}
```

### Message

```json
{
  "id": "uuid",
  "chat_id": "uuid",
  "role": "assistant",
  "content": "Hello! How can I help?",
  "provider": "proxyapi",
  "model": "gpt-4o-mini",
  "status": "complete",
  "token_input": 120,
  "token_output": 45,
  "latency_ms": 1840,
  "error_text": null,
  "created_at": "2026-04-21T12:35:10Z"
}
```

### ModelInfo

```json
{
  "id": "gpt-4o-mini",
  "display_name": "GPT-4o Mini",
  "provider": "proxyapi",
  "source_type": "cloud",
  "context_window": 128000,
  "supports_streaming": true,
  "supports_tools": false,
  "is_active": true
}
```

### ProviderHealth

```json
{
  "provider": "ollama",
  "status": "ok",
  "latency_ms": 42,
  "details": "Ollama is reachable"
}
```

## 4. Chats API

### 4.1 Create chat

`POST /api/chats`

Creates a new chat.

Request:

```json
{
  "title": "New chat",
  "selected_provider": "proxyapi",
  "selected_model": "gpt-4o-mini"
}
```

Rules:

- `title` is optional
- if title is omitted, backend may generate a default title
- if provider/model are omitted, backend should use configured defaults

Response `201 Created`:

```json
{
  "chat": {
    "id": "uuid",
    "title": "New chat",
    "selected_provider": "proxyapi",
    "selected_model": "gpt-4o-mini",
    "created_at": "2026-04-21T12:30:45Z",
    "updated_at": "2026-04-21T12:30:45Z"
  }
}
```

### 4.2 List chats

`GET /api/chats`

Returns chat list ordered by `updated_at desc`.

Optional query params:

- `limit`
- `offset`
- `search`

Response `200 OK`:

```json
{
  "items": [
    {
      "id": "uuid",
      "title": "Trip planning",
      "selected_provider": "proxyapi",
      "selected_model": "gpt-4o-mini",
      "created_at": "2026-04-21T12:30:45Z",
      "updated_at": "2026-04-21T12:35:10Z"
    }
  ],
  "total": 1
}
```

### 4.3 Get chat by id

`GET /api/chats/{chat_id}`

Returns chat metadata and full message list.

Response `200 OK`:

```json
{
  "chat": {
    "id": "uuid",
    "title": "Trip planning",
    "selected_provider": "proxyapi",
    "selected_model": "gpt-4o-mini",
    "created_at": "2026-04-21T12:30:45Z",
    "updated_at": "2026-04-21T12:35:10Z"
  },
  "messages": [
    {
      "id": "uuid",
      "chat_id": "uuid",
      "role": "user",
      "content": "Plan my trip",
      "provider": "proxyapi",
      "model": "gpt-4o-mini",
      "status": "complete",
      "token_input": null,
      "token_output": null,
      "latency_ms": null,
      "error_text": null,
      "created_at": "2026-04-21T12:31:00Z"
    },
    {
      "id": "uuid",
      "chat_id": "uuid",
      "role": "assistant",
      "content": "Sure. Where are you going?",
      "provider": "proxyapi",
      "model": "gpt-4o-mini",
      "status": "complete",
      "token_input": 120,
      "token_output": 30,
      "latency_ms": 1200,
      "error_text": null,
      "created_at": "2026-04-21T12:31:01Z"
    }
  ]
}
```

### 4.4 Update chat

`PATCH /api/chats/{chat_id}`

Allows updating chat title and default generation target.

Request:

```json
{
  "title": "Travel planning",
  "selected_provider": "ollama",
  "selected_model": "llama3.1"
}
```

Response `200 OK`:

```json
{
  "chat": {
    "id": "uuid",
    "title": "Travel planning",
    "selected_provider": "ollama",
    "selected_model": "llama3.1",
    "created_at": "2026-04-21T12:30:45Z",
    "updated_at": "2026-04-21T12:40:00Z"
  }
}
```

### 4.5 Delete chat

`DELETE /api/chats/{chat_id}`

Response `204 No Content`

## 5. Messages API

### 5.1 Send message and wait for final response

`POST /api/chats/{chat_id}/messages`

Creates a user message, calls the selected provider, waits for the full assistant response, saves it, and returns both records.

Request:

```json
{
  "content": "Explain SSE in simple words",
  "provider": "proxyapi",
  "model": "gpt-4o-mini",
  "settings": {
    "temperature": 0.7,
    "max_tokens": 1024,
    "system_prompt": "Answer briefly and clearly."
  }
}
```

Rules:

- `provider` and `model` are optional if chat defaults exist
- `settings` is optional
- if `system_prompt` is not supplied, backend may use a chat-level or app-level default

Response `200 OK`:

```json
{
  "user_message": {
    "id": "uuid",
    "chat_id": "uuid",
    "role": "user",
    "content": "Explain SSE in simple words",
    "provider": "proxyapi",
    "model": "gpt-4o-mini",
    "status": "complete",
    "token_input": null,
    "token_output": null,
    "latency_ms": null,
    "error_text": null,
    "created_at": "2026-04-21T12:40:01Z"
  },
  "assistant_message": {
    "id": "uuid",
    "chat_id": "uuid",
    "role": "assistant",
    "content": "SSE is a way for the server to keep sending updates to the browser over one open connection.",
    "provider": "proxyapi",
    "model": "gpt-4o-mini",
    "status": "complete",
    "token_input": 140,
    "token_output": 27,
    "latency_ms": 1350,
    "error_text": null,
    "created_at": "2026-04-21T12:40:02Z"
  }
}
```

### 5.2 Send message with streaming

`POST /api/chats/{chat_id}/messages/stream`

This endpoint starts generation and streams the assistant response as SSE events.

Request:

```json
{
  "content": "Explain SSE in simple words",
  "provider": "proxyapi",
  "model": "gpt-4o-mini",
  "settings": {
    "temperature": 0.7,
    "max_tokens": 1024,
    "system_prompt": "Answer briefly and clearly."
  }
}
```

Response headers:

```http
Content-Type: text/event-stream
Cache-Control: no-cache
Connection: keep-alive
```

Event sequence:

1. `start`
2. zero or more `token`
3. `end` or `error`

Example events:

```text
event: start
data: {"chat_id":"uuid","message_id":"uuid","provider":"proxyapi","model":"gpt-4o-mini"}
```

```text
event: token
data: {"message_id":"uuid","delta":"SSE "}
```

```text
event: token
data: {"message_id":"uuid","delta":"is a way "}
```

```text
event: end
data: {"message_id":"uuid","full_text":"SSE is a way for the server to keep sending updates to the browser.","usage":{"input_tokens":140,"output_tokens":27},"latency_ms":1350}
```

Error event example:

```text
event: error
data: {"code":"provider_timeout","message":"The selected provider did not respond in time."}
```

### 5.3 Regenerate last assistant response

Optional for MVP but useful in the API design.

`POST /api/chats/{chat_id}/messages/regenerate`

Request:

```json
{
  "provider": "ollama",
  "model": "llama3.1",
  "settings": {
    "temperature": 0.5,
    "max_tokens": 1024
  }
}
```

Response:

Same shape as `POST /api/chats/{chat_id}/messages`

## 6. Models API

### 6.1 List models

`GET /api/models`

Optional query params:

- `provider`
- `source`
- `active_only`

Examples:

- `GET /api/models`
- `GET /api/models?source=cloud`
- `GET /api/models?provider=ollama`

Response `200 OK`:

```json
{
  "items": [
    {
      "id": "gpt-4o-mini",
      "display_name": "GPT-4o Mini",
      "provider": "proxyapi",
      "source_type": "cloud",
      "context_window": 128000,
      "supports_streaming": true,
      "supports_tools": false,
      "is_active": true
    },
    {
      "id": "llama3.1",
      "display_name": "Llama 3.1",
      "provider": "ollama",
      "source_type": "local",
      "context_window": 8192,
      "supports_streaming": true,
      "supports_tools": false,
      "is_active": true
    }
  ]
}
```

## 7. Providers API

### 7.1 Provider health

`GET /api/providers/health`

Response `200 OK`:

```json
{
  "items": [
    {
      "provider": "proxyapi",
      "status": "ok",
      "latency_ms": 180,
      "details": "Upstream API is reachable"
    },
    {
      "provider": "ollama",
      "status": "ok",
      "latency_ms": 42,
      "details": "Ollama is reachable"
    }
  ]
}
```

Possible status values:

- `ok`
- `degraded`
- `offline`

## 8. Settings API

### 8.1 Get settings

`GET /api/settings`

Returns effective user or app defaults for generation.

Response `200 OK`:

```json
{
  "default_provider": "proxyapi",
  "default_model": "gpt-4o-mini",
  "default_temperature": 0.7,
  "default_max_tokens": 1024,
  "system_prompt": ""
}
```

### 8.2 Update settings

`PATCH /api/settings`

Request:

```json
{
  "default_provider": "ollama",
  "default_model": "llama3.1",
  "default_temperature": 0.6,
  "default_max_tokens": 768,
  "system_prompt": "Answer concisely."
}
```

Response `200 OK`:

```json
{
  "default_provider": "ollama",
  "default_model": "llama3.1",
  "default_temperature": 0.6,
  "default_max_tokens": 768,
  "system_prompt": "Answer concisely."
}
```

## 9. Validation rules

### Message request validation

- `content` must not be empty
- `content` should have a maximum allowed length
- `temperature` should be within a safe range such as `0.0..2.0`
- `max_tokens` must be positive and bounded
- `provider` must be known
- `model` must exist for the selected provider

### Chat validation

- `title` should be trimmed
- empty titles may be replaced with a generated fallback

## 10. Error codes

Suggested application-level error codes:

- `validation_error`
- `chat_not_found`
- `message_not_found`
- `provider_not_found`
- `model_not_found`
- `provider_offline`
- `provider_timeout`
- `provider_auth_failed`
- `provider_rate_limited`
- `provider_internal_error`
- `database_error`
- `internal_error`

Example:

```json
{
  "error": {
    "code": "provider_offline",
    "message": "Local LLM runtime is not available.",
    "details": {
      "provider": "ollama"
    }
  }
}
```

## 11. Suggested status codes

- `200 OK` successful read or synchronous action
- `201 Created` chat created
- `204 No Content` delete success
- `400 Bad Request` invalid payload
- `401 Unauthorized` invalid provider credential in upstream flow if surfaced directly
- `404 Not Found` resource missing
- `409 Conflict` invalid state transition if needed
- `422 Unprocessable Entity` schema validation failure
- `429 Too Many Requests` rate limit reached
- `500 Internal Server Error` unexpected backend error
- `502 Bad Gateway` upstream provider failure
- `504 Gateway Timeout` upstream provider timeout

## 12. Frontend integration notes

- Frontend should prefer `/messages/stream` for chat UX.
- Frontend should optimistically append the user message immediately after submit.
- Frontend should build assistant text incrementally from `token` events.
- Frontend should finalize the assistant message only after the `end` event.
- On `error`, frontend should mark the assistant message as failed and show retry UI.

## 13. MVP endpoint set

The minimum API surface required for the first working version:

- `POST /api/chats`
- `GET /api/chats`
- `GET /api/chats/{chat_id}`
- `PATCH /api/chats/{chat_id}`
- `DELETE /api/chats/{chat_id}`
- `POST /api/chats/{chat_id}/messages/stream`
- `GET /api/models`
- `GET /api/providers/health`
- `GET /api/settings`
- `PATCH /api/settings`

## 14. Summary

This API design keeps the frontend simple and provider-agnostic. The backend owns provider selection, request normalization, error mapping, and persistence. That allows the system to support both `ProxyAPI` and local LLMs from one consistent contract.
