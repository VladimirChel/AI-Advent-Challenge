# LLM Assistant Refactor Notes

## Backlog

- Remove the duplicated `_retrieve_chunks(...)` implementation in `rag/service.py`. Keep a single code path for RAG retrieval so bug fixes, diagnostics, and future tuning do not need to be applied in two places.
