from __future__ import annotations

import json
import sys
from pathlib import Path

from config import (
    DAY21_DIR,
    RAG_EMBED_MODEL,
    RAG_INDEX_FILE,
    RAG_METADATA_FILE,
    RAG_MIN_SCORE,
    RAG_OLLAMA_URL,
    RAG_TOP_K,
)
from schemas import RetrievedChunk


if str(DAY21_DIR) not in sys.path:
    sys.path.insert(0, str(DAY21_DIR))

from search_faiss import call_ollama_embed  # type: ignore  # noqa: E402


class RAGAdapterError(RuntimeError):
    pass


class SupportRAGAdapter:
    def __init__(
        self,
        *,
        index_file: str | Path = RAG_INDEX_FILE,
        metadata_file: str | Path = RAG_METADATA_FILE,
        embed_model: str = RAG_EMBED_MODEL,
        ollama_url: str = RAG_OLLAMA_URL,
        top_k: int = RAG_TOP_K,
        min_score: float = RAG_MIN_SCORE,
    ) -> None:
        self.index_file = Path(index_file)
        self.metadata_file = Path(metadata_file)
        self.embed_model = embed_model
        self.ollama_url = ollama_url
        self.top_k = top_k
        self.min_score = min_score

    def search(self, question: str) -> list[RetrievedChunk]:
        normalized_question = " ".join(question.split()).strip()
        if not normalized_question:
            return []
        if not self.index_file.exists():
            raise RAGAdapterError(f"RAG index not found: {self.index_file}")
        if not self.metadata_file.exists():
            raise RAGAdapterError(f"RAG metadata not found: {self.metadata_file}")

        try:
            import faiss
            import numpy as np
        except ImportError as exc:
            raise RAGAdapterError("Install faiss-cpu and numpy to enable retrieval.") from exc

        metadata = json.loads(self.metadata_file.read_text(encoding="utf-8"))
        items = metadata.get("items", [])
        query_embedding = call_ollama_embed(self.ollama_url, self.embed_model, normalized_question)
        query_vector = np.array([query_embedding], dtype="float32")
        faiss.normalize_L2(query_vector)
        index = faiss.read_index(str(self.index_file))
        distances, indices = index.search(query_vector, self.top_k)

        results: list[RetrievedChunk] = []
        for rank, (score, idx) in enumerate(zip(distances[0], indices[0]), start=1):
            if idx < 0 or idx >= len(items):
                continue
            if float(score) < self.min_score:
                continue
            payload = items[idx]
            chunk = payload.get("chunk", payload)
            results.append(
                RetrievedChunk(
                    rank=rank,
                    score=float(score),
                    chunk_id=str(chunk.get("chunk_id", "")),
                    source=str(chunk.get("source", "")),
                    section=str(chunk.get("section", "")),
                    text=str(chunk.get("text", "")),
                    title=str(chunk.get("title", "")) or None,
                )
            )
        return results
