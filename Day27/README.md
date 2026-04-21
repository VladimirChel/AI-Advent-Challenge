# LLM Chat App

Scaffold for a web chat application that supports:

- cloud LLMs via `ProxyAPI`
- local LLMs via `Ollama`

## Structure

- `backend/` FastAPI backend with provider abstraction
- `frontend/` Next.js frontend with chat UI scaffold
- `docs/` architecture and API specifications

## Run with Docker

```bash
docker compose up --build
```

App URLs:

- frontend: `http://localhost:3000`
- backend: `http://localhost:8000`
- postgres: `localhost:5432`

Default database config:

- database: `llmchat`
- user: `llmchat`
- password: `llmchat`

Backend uses `PostgreSQL` by default through `DATABASE_URL`.

## Next steps

1. Install backend dependencies.
2. Install frontend dependencies.
3. Implement real provider integrations.
4. Add migrations with `Alembic`.
