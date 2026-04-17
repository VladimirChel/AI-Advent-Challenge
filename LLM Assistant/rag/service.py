from __future__ import annotations

import importlib.util
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from fastapi import HTTPException

from config import (
    RAG_DEFAULT_STRATEGY,
    RAG_DENSE_SEARCH_ENABLED,
    RAG_EMBED_MODEL,
    RAG_ENABLED_BY_DEFAULT,
    RAG_INDEX_FILE,
    RAG_LEXICAL_FALLBACK_ENABLED,
    RAG_LEXICAL_RERANK_ENABLED,
    RAG_MAX_CHUNKS,
    RAG_METADATA_FILE,
    RAG_MIN_RELEVANCE_SCORE,
    RAG_OLLAMA_URL,
)
from llm.schemas import ChatMessage, RAGChunkPayload, RAGSettings


ROOT_DIR = Path(__file__).resolve().parents[1]
DAY21_DIR = ROOT_DIR.parent / "Day21"

RUSSIAN_STOPWORDS = {
    "как",
    "включить",
    "включается",
    "мне",
    "нужно",
    "надо",
    "подскажи",
    "подскажите",
    "покажи",
    "покажите",
    "расскажи",
    "расскажите",
    "найти",
    "ищу",
    "нужен",
    "нужна",
    "нужны",
    "ли",
    "в",
    "на",
    "по",
    "для",
    "и",
    "или",
    "что",
    "где",
    "когда",
}


@dataclass(slots=True)
class _RetrievedChunk:
    rank: int
    score: float
    chunk_id: str
    title: str
    source: str
    section: str
    text: str


@dataclass(slots=True)
class Day22RAGResult:
    enabled: bool
    strategy: str | None = None
    chunks: list[RAGChunkPayload] | None = None
    context_message: ChatMessage | None = None
    below_threshold: bool = False
    min_relevance_score: float = 0.0


def resolve_rag_settings(payload_rag: RAGSettings | None) -> RAGSettings | None:
    if payload_rag is not None:
        return payload_rag if payload_rag.enabled else None

    if not RAG_ENABLED_BY_DEFAULT:
        return None

    return RAGSettings(
        enabled=True,
        strategy=RAG_DEFAULT_STRATEGY,
        index_file=str(RAG_INDEX_FILE) if RAG_INDEX_FILE else None,
        metadata_file=str(RAG_METADATA_FILE) if RAG_METADATA_FILE else None,
        embed_model=RAG_EMBED_MODEL,
        ollama_url=RAG_OLLAMA_URL,
        top_k=RAG_MAX_CHUNKS,
        min_relevance_score=RAG_MIN_RELEVANCE_SCORE,
        dense_search_enabled=RAG_DENSE_SEARCH_ENABLED,
        lexical_rerank_enabled=RAG_LEXICAL_RERANK_ENABLED,
        lexical_fallback_enabled=RAG_LEXICAL_FALLBACK_ENABLED,
    )


def build_day22_rag_context(question: str, settings: RAGSettings | None) -> Day22RAGResult:
    if settings is None:
        return Day22RAGResult(enabled=False, chunks=[])

    normalized_question = " ".join(question.split()).strip()
    if not normalized_question:
        return Day22RAGResult(
            enabled=True,
            strategy=settings.strategy,
            chunks=[],
            min_relevance_score=settings.min_relevance_score,
        )

    if not settings.dense_search_enabled and not settings.lexical_fallback_enabled:
        raise HTTPException(status_code=400, detail="rag_requires_dense_or_lexical_fallback")

    index_file, metadata_file = _resolve_retrieval_files(
        strategy=settings.strategy,
        index_file=settings.index_file,
        metadata_file=settings.metadata_file,
    )
    chunks = _retrieve_chunks(
        question=normalized_question,
        index_file=index_file,
        metadata_file=metadata_file,
        embed_model=settings.embed_model,
        ollama_url=settings.ollama_url,
        top_k=settings.top_k,
        enable_dense_search=settings.dense_search_enabled,
        enable_lexical_rerank=settings.lexical_rerank_enabled,
        enable_lexical_fallback=settings.lexical_fallback_enabled,
    )
    relevant_chunks = [chunk for chunk in chunks if chunk.score >= settings.min_relevance_score]
    payload_chunks = [
        RAGChunkPayload(
            rank=chunk.rank,
            score=chunk.score,
            chunk_id=chunk.chunk_id,
            title=chunk.title,
            source=chunk.source,
            section=chunk.section,
            text=chunk.text,
        )
        for chunk in relevant_chunks
    ]
    below_threshold = not payload_chunks
    return Day22RAGResult(
        enabled=True,
        strategy=settings.strategy,
        chunks=payload_chunks,
        context_message=_build_rag_context_message(
            normalized_question,
            settings.strategy,
            relevant_chunks,
            min_relevance_score=settings.min_relevance_score,
            below_threshold=below_threshold,
        ),
        below_threshold=below_threshold,
        min_relevance_score=settings.min_relevance_score,
    )


def enforce_rag_response_contract(content: str, rag_result: Day22RAGResult) -> str:
    if not rag_result.enabled:
        return content

    if rag_result.below_threshold or not rag_result.chunks:
        return (
            "Не знаю. Уточните вопрос, пожалуйста: "
            "в найденных документах не нашлось достаточно релевантных фрагментов."
        )

    body = (content or "").strip()
    if not body:
        body = "Краткий ответ по найденным документам не сформирован."

    sources_block = _build_sources_block(rag_result.chunks)
    quotes_block = _build_quotes_block(rag_result.chunks)
    return f"{body}\n\nИсточники:\n{sources_block}\n\nЦитаты:\n{quotes_block}"


def _load_day21_search_module() -> Any:
    path = DAY21_DIR / "search_faiss.py"
    spec = importlib.util.spec_from_file_location("day21_search_faiss", path)
    if spec is None or spec.loader is None:
        raise HTTPException(status_code=500, detail=f"rag_day21_module_load_failed:{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _retrieve_chunks(
    *,
    question: str,
    index_file: Path,
    metadata_file: Path,
    embed_model: str,
    ollama_url: str,
    top_k: int,
    enable_dense_search: bool,
    enable_lexical_rerank: bool,
    enable_lexical_fallback: bool,
) -> list[_RetrievedChunk]:
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="rag_dependencies_missing") from exc

    if not index_file.exists():
        raise HTTPException(status_code=503, detail=f"rag_index_not_found:{index_file}")
    if not metadata_file.exists():
        raise HTTPException(status_code=503, detail=f"rag_metadata_not_found:{metadata_file}")

    day21_search = _load_day21_search_module()
    metadata = json.loads(metadata_file.read_text(encoding="utf-8"))
    items = metadata["items"]
    index = faiss.read_index(str(index_file))

    candidate_scores: dict[int, float] = {}
    query_variants = _build_query_variants(question)
    embedding_queries = _build_embedding_queries(question)
    search_depth = min(len(items), max(top_k * 10, 20))

    if enable_dense_search:
        for query_variant in embedding_queries:
            query_embedding = day21_search.call_ollama_embed(
                ollama_url=ollama_url,
                model=embed_model,
                text=query_variant,
            )
            query_vector = np.array([query_embedding], dtype="float32")
            faiss.normalize_L2(query_vector)
            distances, indices = index.search(query_vector, search_depth)
            for score, idx in zip(distances[0], indices[0]):
                if idx < 0 or idx >= len(items):
                    continue
                final_score = float(score)
                if enable_lexical_rerank:
                    final_score += _lexical_boost(query_variant, items[idx])
                previous = candidate_scores.get(idx)
                if previous is None or final_score > previous:
                    candidate_scores[idx] = final_score

    if enable_lexical_fallback:
        for idx, raw_item in enumerate(items):
            lexical_score = max(_lexical_boost(query_variant, raw_item) for query_variant in query_variants)
            if lexical_score <= 0:
                continue
            fallback_score = 0.5 + lexical_score
            previous = candidate_scores.get(idx)
            if previous is None or fallback_score > previous:
                candidate_scores[idx] = fallback_score

    ranked_indices = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]
    results: list[_RetrievedChunk] = []
    for rank, (idx, score) in enumerate(ranked_indices, start=1):
        raw_item = items[idx]
        chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
        results.append(
            _RetrievedChunk(
                rank=rank,
                score=float(score),
                chunk_id=str(chunk.get("chunk_id", "")),
                title=str(chunk.get("title", "")),
                source=str(chunk.get("source", "")),
                section=str(chunk.get("section", "")),
                text=str(chunk.get("text", "")).strip(),
            )
        )
    return results


def _build_query_variants(question: str) -> list[str]:
    normalized = " ".join(question.lower().split())
    variants: list[str] = []

    def add_variant(value: str) -> None:
        candidate = " ".join(value.split()).strip()
        if candidate and candidate not in variants:
            variants.append(candidate)

    add_variant(question.strip())
    add_variant(normalized)

    tokens = re.findall(r"[\w=.\-]+", normalized, flags=re.UNICODE)
    filtered_tokens = [token for token in tokens if token not in RUSSIAN_STOPWORDS]
    add_variant(" ".join(filtered_tokens))

    significant_tokens = [token for token in filtered_tokens if len(token) > 2 or token.isascii()]
    for tail_size in (4, 3):
        if len(significant_tokens) >= tail_size:
            add_variant(" ".join(significant_tokens[-tail_size:]))

    return variants


def _build_embedding_queries(question: str) -> list[str]:
    variants = _build_query_variants(question)
    normalized = " ".join(question.lower().split())
    tokens = re.findall(r"[\w=.\-]+", normalized, flags=re.UNICODE)
    filtered_tokens = [token for token in tokens if token not in RUSSIAN_STOPWORDS]
    significant_tokens = [token for token in filtered_tokens if len(token) > 2 or token.isascii()]
    embedding_queries: list[str] = []

    def add_query(value: str) -> None:
        candidate = " ".join(value.split()).strip()
        if candidate and candidate not in embedding_queries:
            embedding_queries.append(candidate)

    if len(significant_tokens) >= 3:
        add_query(" ".join(significant_tokens))
        add_query(" ".join(significant_tokens[-3:]))
    if len(significant_tokens) >= 4:
        add_query(" ".join(significant_tokens[-4:]))
    if len(significant_tokens) < 3:
        for variant in variants:
            add_query(variant)

    return embedding_queries


def _normalize_match_token(token: str) -> str:
    normalized = token.lower().replace("ё", "е")
    normalized = re.sub(r"(.)\1+", r"\1", normalized)
    for suffix in (
        "иями",
        "ями",
        "ами",
        "ого",
        "его",
        "ому",
        "ему",
        "ыми",
        "ими",
        "иях",
        "ах",
        "ях",
        "ия",
        "ья",
        "ов",
        "ев",
        "ом",
        "ем",
        "ой",
        "ей",
        "ам",
        "ям",
        "ы",
        "и",
        "а",
        "я",
        "е",
        "о",
        "у",
        "ю",
    ):
        if len(normalized) > len(suffix) + 2 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def _token_distance_leq_one(left: str, right: str) -> bool:
    if left == right:
        return True
    if abs(len(left) - len(right)) > 1:
        return False

    i = 0
    j = 0
    edits = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            i += 1
            j += 1
            continue
        edits += 1
        if edits > 1:
            return False
        if len(left) == len(right):
            i += 1
            j += 1
        elif len(left) > len(right):
            i += 1
        else:
            j += 1
    if i < len(left) or j < len(right):
        edits += 1
    return edits <= 1


def _count_token_matches(query_tokens: list[str], haystack: str) -> tuple[int, int]:
    haystack_tokens = [
        _normalize_match_token(token)
        for token in re.findall(r"[\w=.\-]+", haystack.lower(), flags=re.UNICODE)
        if token
    ]
    exact_matches = 0
    fuzzy_matches = 0
    for token in query_tokens:
        if token in haystack_tokens:
            exact_matches += 1
            continue
        if len(token) < 5:
            continue
        if any(_token_distance_leq_one(token, hay_token) for hay_token in haystack_tokens):
            fuzzy_matches += 1
    return exact_matches, fuzzy_matches


def _lexical_boost(query: str, raw_item: dict[str, Any]) -> float:
    chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
    title_source_haystack = " ".join(
        [
            str(chunk.get("title", "")).lower(),
            Path(str(chunk.get("source", ""))).name.lower(),
            str(chunk.get("section", "")).lower(),
        ]
    )
    full_haystack = " ".join(
        [
            title_source_haystack,
            str(chunk.get("section", "")).lower(),
            str(chunk.get("text", "")).lower(),
        ]
    )
    tokens = [token for token in re.findall(r"[\w=.\-]+", query.lower(), flags=re.UNICODE) if token]
    normalized_tokens = [_normalize_match_token(token) for token in tokens if token]
    if not normalized_tokens:
        return 0.0

    matched_full, fuzzy_full = _count_token_matches(normalized_tokens, full_haystack)
    matched_title_source, fuzzy_title_source = _count_token_matches(normalized_tokens, title_source_haystack)
    phrase_bonus = 0.0
    compact_query = " ".join(normalized_tokens)
    if compact_query and compact_query in full_haystack:
        phrase_bonus = 0.2

    total_title_matches = matched_title_source + fuzzy_title_source
    if total_title_matches == len(normalized_tokens):
        phrase_bonus += 1.0
    elif total_title_matches >= max(2, len(normalized_tokens) - 1):
        phrase_bonus += 0.6

    return (
        matched_full * 0.03
        + fuzzy_full * 0.02
        + matched_title_source * 0.16
        + fuzzy_title_source * 0.12
        + phrase_bonus
    )


def _resolve_retrieval_files(strategy: str, index_file: str | None, metadata_file: str | None) -> tuple[Path, Path]:
    resolved_index = Path(index_file).resolve() if index_file else DAY21_DIR / "output" / f"{strategy}.faiss"
    resolved_metadata = (
        Path(metadata_file).resolve() if metadata_file else DAY21_DIR / "output" / f"{strategy}_chunks.json"
    )
    return resolved_index, resolved_metadata


def _build_sources_block(chunks: list[RAGChunkPayload]) -> str:
    seen: set[tuple[str, str, str]] = set()
    lines: list[str] = []
    for chunk in chunks:
        key = (chunk.source, chunk.section, chunk.chunk_id)
        if key in seen:
            continue
        seen.add(key)
        lines.append(f"- {chunk.source} | {chunk.section} | {chunk.chunk_id}")
    return "\n".join(lines) if lines else "- Источники не найдены"


def _build_quotes_block(chunks: list[RAGChunkPayload]) -> str:
    lines: list[str] = []
    for chunk in chunks:
        snippet = _build_quote_snippet(chunk.text)
        lines.append(f'- [{chunk.source} | {chunk.section} | {chunk.chunk_id}] "{snippet}"')
    return "\n".join(lines) if lines else '- "Цитаты не найдены"'


def _build_quote_snippet(text: str, limit: int = 220) -> str:
    normalized = " ".join((text or "").split()).strip()
    if not normalized:
        return "Фрагмент отсутствует."
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 3].rstrip() + "..."


def _build_rag_context_message(
    question: str,
    strategy: str,
    chunks: list[_RetrievedChunk],
    *,
    min_relevance_score: float,
    below_threshold: bool,
) -> ChatMessage:
    chunk_blocks: list[str] = []
    for chunk in chunks:
        chunk_blocks.append(
            "\n".join(
                [
                    f"[Chunk {chunk.rank}] score={chunk.score:.4f}",
                    f"title: {chunk.title}",
                    f"source: {chunk.source}",
                    f"section: {chunk.section}",
                    chunk.text,
                ]
            )
        )

    context = "\n\n".join(chunk_blocks) if chunk_blocks else "Релевантные чанки не найдены."
    if below_threshold:
        instruction = (
            "Релевантность найденных фрагментов ниже порога. "
            "Ответь пользователю строго по смыслу так: "
            '"Не знаю. Уточните вопрос, пожалуйста." '
            "Не придумывай факты и не добавляй источники."
        )
    else:
        instruction = (
            "Отвечай только по найденным чанкам. "
            "После краткого ответа обязательно добавь раздел `Источники` со списком "
            "`source | section | chunk_id` и раздел `Цитаты` с фрагментами из найденных чанков. "
            "Не выдумывай источники и не цитируй ничего вне этого контекста."
        )
    return ChatMessage(
        role="system",
        content=(
            "Ниже приведены найденные чанки из локального индекса документов. "
            f"{instruction}\n\n"
            f"Стратегия retrieval: {strategy}\n\n"
            f"Порог релевантности: {min_relevance_score:.2f}\n\n"
            f"Контекст Day22 RAG:\n{context}\n\n"
            f"Исходный вопрос пользователя: {question}"
        ),
    )
