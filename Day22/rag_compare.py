#!/usr/bin/env python3
from __future__ import annotations

import argparse
import importlib.util
import json
import re
import time
import urllib.error
import urllib.request
import uuid
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[1]
DAY21_DIR = ROOT_DIR / "Day21"
LLM_ASSISTANT_DIR = ROOT_DIR / "LLM Assistant"


@dataclass(slots=True)
class RetrievedChunk:
    rank: int
    score: float
    chunk_id: str
    title: str
    source: str
    section: str
    text: str


@dataclass(slots=True)
class RetrievalCandidate:
    idx: int
    chunk_id: str
    source: str
    section: str
    dense_score: float | None = None
    phrase_score: float | None = None
    lexical_rerank_score: float | None = None
    lexical_fallback_score: float | None = None
    final_score: float | None = None


@dataclass(slots=True)
class RetrievalDebugInfo:
    query_variants: list[str]
    embedding_queries: list[str]
    search_depth: int
    dense_enabled: bool
    lexical_rerank_enabled: bool
    lexical_fallback_enabled: bool
    dense_candidates: list[RetrievalCandidate]
    reranked_candidates: list[RetrievalCandidate]
    phrase_candidates: list[RetrievalCandidate]
    fallback_candidates: list[RetrievalCandidate]
    final_candidates: list[RetrievalCandidate]


RUSSIAN_STOPWORDS = {
    "как",
    "включить",
    "вклюить",
    "включается",
    "включается?",
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


RUSSIAN_STOPWORDS = {
    "как",
    "включить",
    "включается",
    "подключить",
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
RUSSIAN_STOPWORDS.discard("подключить")


def configure_stdio() -> None:
    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except Exception:
                pass


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сравнение ответа модели без RAG и с RAG на базе поиска из Day21 и клиента из LLM Assistant."
    )
    parser.add_argument("question", help="Вопрос пользователя.")
    parser.add_argument(
        "--strategy",
        choices=("fixed", "structure"),
        default="structure",
        help="Какая стратегия индекса Day21 используется для retrieval. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--index-file",
        default="",
        help="Путь к FAISS-индексу из Day21. Если не задан, выбирается по `--strategy`.",
    )
    parser.add_argument(
        "--metadata-file",
        default="",
        help="Путь к JSON с чанками из Day21. Если не задан, выбирается по `--strategy`.",
    )
    parser.add_argument(
        "--embed-model",
        default="bge-m3",
        help="Embedding-модель Ollama для retrieval. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="URL локального сервера Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько релевантных чанков добавить в контекст. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.2,
        help="Температура генерации. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=900,
        help="Максимум токенов ответа. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--user-id",
        default="day22-rag-compare",
        help="Идентификатор пользователя для сравнения. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--assistant-url",
        default="http://127.0.0.1:8000",
        help="URL запущенного LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--auth-token",
        default="",
        help="Bearer token для LLM Assistant. Если не передан, скрипт зарегистрирует временного пользователя.",
    )
    parser.add_argument(
        "--assistant-model",
        default="openai/gpt-4o-mini",
        help="Модель для запроса к LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--disable-dense-search",
        action="store_true",
        help="Disable dense embedding search over FAISS.",
    )
    parser.add_argument(
        "--disable-lexical-rerank",
        action="store_true",
        help="Disable lexical boost for dense-search candidates.",
    )
    parser.add_argument(
        "--disable-lexical-fallback",
        action="store_true",
        help="Disable keyword-based fallback over all chunks.",
    )
    parser.add_argument(
        "--show-retrieval-stages",
        action="store_true",
        help="Print all retrieval stages and their candidates.",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Run retrieval only and skip LLM calls.",
    )
    return parser.parse_args()


def _load_module(module_name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Не удалось загрузить модуль {module_name} из {path}")

    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def retrieve_chunks(
    *,
    question: str,
    index_file: Path,
    metadata_file: Path,
    embed_model: str,
    ollama_url: str,
    top_k: int,
    enable_dense_search: bool = True,
    enable_lexical_rerank: bool = True,
    enable_lexical_fallback: bool = True,
    debug_info: RetrievalDebugInfo | None = None,
) -> list[RetrievedChunk]:
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Для retrieval нужны зависимости `faiss-cpu` и `numpy`."
        ) from exc

    if not index_file.exists():
        raise FileNotFoundError(f"FAISS-индекс не найден: {index_file}")
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata-файл не найден: {metadata_file}")

    day21_search = _load_module("day21_search_faiss", DAY21_DIR / "search_faiss.py")

    with metadata_file.open("r", encoding="utf-8") as fh:
        metadata = json.load(fh)
    items = metadata["items"]

    index = faiss.read_index(str(index_file))
    dense_scores: dict[int, float] = {}
    dense_reranked_scores: dict[int, float] = {}
    phrase_scores: dict[int, float] = {}
    lexical_rerank_scores: dict[int, float] = {}
    fallback_scores: dict[int, float] = {}
    query_variants = build_query_variants(question)
    embedding_queries = build_embedding_queries(question)
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
                dense_score = float(score)
                previous_dense = dense_scores.get(idx)
                if previous_dense is None or dense_score > previous_dense:
                    dense_scores[idx] = dense_score

                reranked_score = dense_score
                if enable_lexical_rerank:
                    lexical_score = lexical_boost(query_variant, items[idx])
                    previous_lexical = lexical_rerank_scores.get(idx)
                    if previous_lexical is None or lexical_score > previous_lexical:
                        lexical_rerank_scores[idx] = lexical_score
                    reranked_score += lexical_score

                previous = dense_reranked_scores.get(idx)
                if previous is None or reranked_score > previous:
                    dense_reranked_scores[idx] = reranked_score

    for idx, raw_item in enumerate(items):
        phrase_score = max(phrase_match_score(query_variant, raw_item) for query_variant in query_variants)
        if phrase_score > 0:
            phrase_scores[idx] = phrase_score

    if enable_lexical_fallback:
        for idx, raw_item in enumerate(items):
            lexical_score = max(lexical_boost(query_variant, raw_item) for query_variant in query_variants)
            if lexical_score <= 0:
                continue
            # Keyword fallback helps when the exact topic appears in title/source,
            # but the dense embedding search ranks the chunk too low.
            fallback_score = 0.5 + lexical_score
            previous_fallback = fallback_scores.get(idx)
            if previous_fallback is None or fallback_score > previous_fallback:
                fallback_scores[idx] = fallback_score

    candidate_scores = reciprocal_rank_fuse(
        [
            (dense_reranked_scores, 1.0 if enable_dense_search else 0.0),
            (phrase_scores, 2.5),
            (fallback_scores, 0.9 if enable_lexical_fallback else 0.0),
        ]
    )
    ranked_indices = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]

    if debug_info is not None:
        debug_info.query_variants = query_variants
        debug_info.embedding_queries = embedding_queries
        debug_info.search_depth = search_depth
        debug_info.dense_enabled = enable_dense_search
        debug_info.lexical_rerank_enabled = enable_lexical_rerank
        debug_info.lexical_fallback_enabled = enable_lexical_fallback
        debug_info.dense_candidates = build_debug_candidates(
            items=items,
            final_scores=dense_scores,
            dense_scores=dense_scores,
            phrase_scores={},
            lexical_rerank_scores=lexical_rerank_scores,
            fallback_scores={},
            limit=search_depth,
        )
        debug_info.reranked_candidates = build_debug_candidates(
            items=items,
            final_scores=dense_reranked_scores if enable_lexical_rerank else dense_scores,
            dense_scores=dense_scores,
            phrase_scores={},
            lexical_rerank_scores=lexical_rerank_scores,
            fallback_scores={},
            limit=search_depth,
        )
        debug_info.phrase_candidates = build_debug_candidates(
            items=items,
            final_scores=phrase_scores,
            dense_scores={},
            phrase_scores=phrase_scores,
            lexical_rerank_scores={},
            fallback_scores={},
            limit=max(top_k * 3, 10),
        )
        debug_info.fallback_candidates = build_debug_candidates(
            items=items,
            final_scores=fallback_scores,
            dense_scores={},
            phrase_scores={},
            lexical_rerank_scores={},
            fallback_scores=fallback_scores,
            limit=max(top_k * 3, 10),
        )
        debug_info.final_candidates = build_debug_candidates(
            items=items,
            final_scores=dict(ranked_indices),
            dense_scores=dense_scores,
            phrase_scores=phrase_scores,
            lexical_rerank_scores=lexical_rerank_scores,
            fallback_scores=fallback_scores,
            limit=top_k,
        )

    results: list[RetrievedChunk] = []
    for rank, (idx, score) in enumerate(ranked_indices, start=1):
        raw_item = items[idx]
        chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
        results.append(
            RetrievedChunk(
                rank=rank,
                score=float(score),
                chunk_id=chunk["chunk_id"],
                title=chunk.get("title", ""),
                source=chunk["source"],
                section=chunk["section"],
                text=chunk["text"].strip(),
            )
        )
    return results


def build_query_variants(question: str) -> list[str]:
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
    filtered_query = " ".join(filtered_tokens).strip()
    add_variant(filtered_query)

    # Prefer the topical tail of the query so that
    # "Как ... сервисный режим контроллера Sigur"
    # and "сервисный режим контроллера Sigur" search similarly.
    significant_tokens = [token for token in filtered_tokens if len(token) > 2 or token.isascii()]
    for tail_size in (4, 3):
        if len(significant_tokens) >= tail_size:
            add_variant(" ".join(significant_tokens[-tail_size:]))

    return variants


def build_embedding_queries(question: str) -> list[str]:
    variants = build_query_variants(question)
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
    if len(significant_tokens) >= 4:
        add_query(" ".join(significant_tokens[-4:]))
    if len(significant_tokens) >= 3:
        add_query(" ".join(significant_tokens[-3:]))

    if len(significant_tokens) < 3:
        for variant in variants:
            add_query(variant)

    return embedding_queries


def build_debug_candidates(
    *,
    items: list[dict[str, Any]],
    final_scores: dict[int, float],
    dense_scores: dict[int, float],
    phrase_scores: dict[int, float],
    lexical_rerank_scores: dict[int, float],
    fallback_scores: dict[int, float],
    limit: int,
) -> list[RetrievalCandidate]:
    ranked = sorted(final_scores.items(), key=lambda item: item[1], reverse=True)[:limit]
    candidates: list[RetrievalCandidate] = []
    for idx, final_score in ranked:
        raw_item = items[idx]
        chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
        candidates.append(
            RetrievalCandidate(
                idx=idx,
                chunk_id=str(chunk.get("chunk_id", "")),
                source=str(chunk.get("source", "")),
                section=str(chunk.get("section", "")),
                dense_score=dense_scores.get(idx),
                phrase_score=phrase_scores.get(idx),
                lexical_rerank_score=lexical_rerank_scores.get(idx),
                lexical_fallback_score=fallback_scores.get(idx),
                final_score=float(final_score),
            )
        )
    return candidates


def normalize_match_token(token: str) -> str:
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


def token_distance_leq_one(left: str, right: str) -> bool:
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


def count_token_matches(query_tokens: list[str], haystack: str) -> tuple[int, int]:
    haystack_tokens = [
        normalize_match_token(token)
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
        if any(token_distance_leq_one(token, hay_token) for hay_token in haystack_tokens):
            fuzzy_matches += 1
    return exact_matches, fuzzy_matches


def lexical_boost(query: str, raw_item: dict[str, Any]) -> float:
    chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
    text_haystack = str(chunk.get("text", "")).lower()
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
            text_haystack,
        ]
    )
    tokens = [token for token in re.findall(r"[\w=.\-]+", query.lower(), flags=re.UNICODE) if token]
    normalized_tokens = [normalize_match_token(token) for token in tokens if token]
    if not normalized_tokens:
        return 0.0

    matched_full, fuzzy_full = count_token_matches(normalized_tokens, full_haystack)
    matched_title_source, fuzzy_title_source = count_token_matches(normalized_tokens, title_source_haystack)
    phrase_bonus = 0.0
    compact_query = " ".join(normalized_tokens)
    if compact_query and compact_query in full_haystack:
        phrase_bonus = 0.2

    total_title_matches = matched_title_source + fuzzy_title_source
    if total_title_matches == len(normalized_tokens):
        phrase_bonus += 1.0
    elif total_title_matches >= max(2, len(normalized_tokens) - 1):
        phrase_bonus += 0.6

    score = (
        matched_full * 0.03
        + fuzzy_full * 0.02
        + matched_title_source * 0.16
        + fuzzy_title_source * 0.12
        + phrase_bonus
    )
    if "оглавление" in text_haystack or len(re.findall(r"\.{4,}", text_haystack)) >= 2:
        score -= 1.0
    return score


def normalize_match_token(token: str) -> str:
    normalized = token.lower().replace("ё", "е")
    normalized = re.sub(r"(.)\1+", r"\1", normalized)
    for suffix in (
        "ирования",
        "ирование",
        "ирован",
        "ениями",
        "ением",
        "ению",
        "ениях",
        "ение",
        "ения",
        "ений",
        "ировать",
        "аться",
        "яться",
        "иться",
        "ывать",
        "овать",
        "ить",
        "ать",
        "ять",
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
        "ый",
        "ий",
        "ая",
        "яя",
        "ое",
        "ее",
        "ы",
        "и",
        "а",
        "я",
        "е",
        "о",
        "у",
        "ю",
        "ь",
    ):
        if len(normalized) > len(suffix) + 2 and normalized.endswith(suffix):
            normalized = normalized[: -len(suffix)]
            break
    return normalized


def query_tokens(query: str) -> list[str]:
    return [
        normalize_match_token(token)
        for token in re.findall(r"[\w=.\-]+", query.lower(), flags=re.UNICODE)
        if token
    ]


def tokens_compatible(left: str, right: str) -> bool:
    if left == right:
        return True
    if len(left) >= 5 and len(right) >= 5:
        prefix_len = 0
        for left_ch, right_ch in zip(left, right):
            if left_ch != right_ch:
                break
            prefix_len += 1
        if prefix_len >= 5:
            return True
    return token_distance_leq_one(left, right)


def count_ordered_phrase_matches(query_tokens: list[str], haystack: str) -> tuple[int, bool]:
    haystack_tokens = [
        normalize_match_token(token)
        for token in re.findall(r"[\w=.\-]+", haystack.lower(), flags=re.UNICODE)
        if token
    ]
    if not query_tokens or not haystack_tokens:
        return 0, False

    best_span = 0
    contiguous = False
    for start_idx, hay_token in enumerate(haystack_tokens):
        if not tokens_compatible(query_tokens[0], hay_token):
            continue
        matched = 1
        last_idx = start_idx
        local_contiguous = True
        for query_idx in range(1, len(query_tokens)):
            next_idx = None
            for candidate_idx in range(last_idx + 1, min(len(haystack_tokens), last_idx + 4)):
                if tokens_compatible(query_tokens[query_idx], haystack_tokens[candidate_idx]):
                    next_idx = candidate_idx
                    if candidate_idx != last_idx + 1:
                        local_contiguous = False
                    break
            if next_idx is None:
                break
            matched += 1
            last_idx = next_idx
        if matched > best_span:
            best_span = matched
        if matched == len(query_tokens) and local_contiguous:
            contiguous = True
            best_span = matched
            break
    return best_span, contiguous


def lexical_boost(query: str, raw_item: dict[str, Any]) -> float:
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
    normalized_tokens = query_tokens(query)
    if not normalized_tokens:
        return 0.0

    matched_full, fuzzy_full = count_token_matches(normalized_tokens, full_haystack)
    matched_title_source, fuzzy_title_source = count_token_matches(normalized_tokens, title_source_haystack)
    ordered_title_matches, contiguous_title_match = count_ordered_phrase_matches(
        normalized_tokens,
        title_source_haystack,
    )
    ordered_full_matches, contiguous_full_match = count_ordered_phrase_matches(
        normalized_tokens,
        full_haystack,
    )

    phrase_bonus = 0.0
    if contiguous_title_match:
        phrase_bonus += 2.0
    elif ordered_title_matches == len(normalized_tokens):
        phrase_bonus += 1.4
    elif ordered_title_matches >= max(2, len(normalized_tokens) - 1):
        phrase_bonus += 0.8

    if contiguous_full_match:
        phrase_bonus += 1.1
    elif ordered_full_matches == len(normalized_tokens):
        phrase_bonus += 0.7

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


def phrase_match_score(query: str, raw_item: dict[str, Any]) -> float:
    chunk = raw_item["chunk"] if "chunk" in raw_item else raw_item
    title = str(chunk.get("title", "")).lower()
    source_name = Path(str(chunk.get("source", ""))).name.lower()
    section = str(chunk.get("section", "")).lower()
    text = str(chunk.get("text", "")).lower()
    title_source_haystack = " ".join([title, source_name, section])
    full_haystack = " ".join([title_source_haystack, text])
    normalized_query_tokens = query_tokens(query)
    if not normalized_query_tokens:
        return 0.0

    ordered_title_matches, contiguous_title_match = count_ordered_phrase_matches(
        normalized_query_tokens,
        title_source_haystack,
    )
    ordered_full_matches, contiguous_full_match = count_ordered_phrase_matches(
        normalized_query_tokens,
        full_haystack,
    )
    exact_title_matches, fuzzy_title_matches = count_token_matches(
        normalized_query_tokens,
        title_source_haystack,
    )
    exact_full_matches, fuzzy_full_matches = count_token_matches(
        normalized_query_tokens,
        full_haystack,
    )
    leading_haystack = full_haystack[:450]
    leading_ordered_matches, leading_contiguous_match = count_ordered_phrase_matches(
        normalized_query_tokens,
        leading_haystack,
    )

    score = 0.0
    if contiguous_title_match:
        score += 8.0
    elif ordered_title_matches == len(normalized_query_tokens):
        score += 6.0
    elif ordered_title_matches >= max(2, len(normalized_query_tokens) - 1):
        score += 4.0

    if contiguous_full_match:
        score += 3.0
    elif ordered_full_matches == len(normalized_query_tokens):
        score += 2.2
    elif ordered_full_matches >= max(2, len(normalized_query_tokens) - 1):
        score += 1.2

    if leading_contiguous_match:
        score += 2.2
    elif leading_ordered_matches == len(normalized_query_tokens):
        score += 1.4

    score += exact_title_matches * 0.7
    score += fuzzy_title_matches * 0.35
    score += exact_full_matches * 0.15
    score += fuzzy_full_matches * 0.08

    if "оглавление" in text or len(re.findall(r"\.{4,}", text)) >= 2:
        score -= 2.5

    return score


def reciprocal_rank_fuse(
    score_maps: list[tuple[dict[int, float], float]],
    *,
    rank_constant: int = 60,
) -> dict[int, float]:
    fused_scores: dict[int, float] = {}
    for score_map, weight in score_maps:
        ranked = sorted(score_map.items(), key=lambda item: item[1], reverse=True)
        for rank, (idx, _score) in enumerate(ranked, start=1):
            fused_scores[idx] = fused_scores.get(idx, 0.0) + weight / (rank_constant + rank)
    return fused_scores


def resolve_retrieval_files(strategy: str, index_file: str, metadata_file: str) -> tuple[Path, Path]:
    if index_file.strip():
        resolved_index = Path(index_file)
    else:
        resolved_index = DAY21_DIR / "output" / f"{strategy}.faiss"

    if metadata_file.strip():
        resolved_metadata = Path(metadata_file)
    else:
        resolved_metadata = DAY21_DIR / "output" / f"{strategy}_chunks.json"

    return resolved_index, resolved_metadata


def build_rag_user_prompt(question: str, strategy: str, chunks: list[RetrievedChunk]) -> str:
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
    return (
        "Ниже приведены найденные чанки из локального индекса документов. "
        "Отвечай только по ним. "
        "Учитывай не только текст чанка, но и его title/source/section: они тоже несут смысл. "
        "Если в title документа указана нужная тема, а в тексте перечислены шаги или настройки, считай это релевантным ответом. "
        "Не требуй буквального совпадения формулировки вопроса с текстом чанка. "
        "Если в контексте действительно недостаточно данных, так и скажи.\n\n"
        f"Стратегия retrieval: {strategy}\n\n"
        f"Контекст:\n{context}\n\n"
        f"Вопрос: {question}"
    )


def call_llm(
    *,
    assistant_url: str,
    auth_token: str,
    model: str,
    prompt: str,
    temperature: float,
    max_tokens: int,
    user_id: str,
) -> str:
    payload = {
        "conversation_id": str(uuid.uuid4()),
        "branch_id": "main",
        "model": model,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{assistant_url.rstrip('/')}/generate",
        data=data,
        headers={
            "Content-Type": "application/json",
            "Authorization": f"Bearer {auth_token}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"LLM Assistant вернул HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Не удалось подключиться к LLM Assistant по адресу {assistant_url}"
        ) from exc

    return str(result.get("content", "")).strip()


def register_temporary_user(assistant_url: str) -> str:
    email = f"day22_{int(time.time())}@example.com"
    password = "Day22TempPass!"
    payload = json.dumps({"email": email, "password": password}).encode("utf-8")
    request = urllib.request.Request(
        f"{assistant_url.rstrip('/')}/auth/register",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            result = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        details = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Не удалось зарегистрировать временного пользователя: HTTP {exc.code}: {details}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(
            f"Не удалось подключиться к LLM Assistant по адресу {assistant_url}"
        ) from exc

    token = str(result.get("access_token", "")).strip()
    if not token:
        raise RuntimeError("LLM Assistant не вернул access_token при регистрации")
    return token


def print_chunks(chunks: list[RetrievedChunk]) -> None:
    print("=== Найденные чанки ===")
    if not chunks:
        print("Чанки не найдены.")
        print("")
        return

    for chunk in chunks:
        snippet = " ".join(chunk.text.split())
        if len(snippet) > 300:
            snippet = snippet[:300].rstrip() + "..."
        print(f"{chunk.rank}. score={chunk.score:.4f}")
        print(f"   chunk_id: {chunk.chunk_id}")
        print(f"   source: {chunk.source}")
        print(f"   section: {chunk.section}")
        print(f"   text: {snippet}")
        print("")


def format_optional_score(value: float | None) -> str:
    if value is None:
        return "-"
    return f"{value:.4f}"


def print_candidate_table(title: str, candidates: list[RetrievalCandidate]) -> None:
    print(title)
    if not candidates:
        print("Нет кандидатов.")
        print("")
        return

    for rank, candidate in enumerate(candidates, start=1):
        print(
            f"{rank}. final={format_optional_score(candidate.final_score)} "
            f"dense={format_optional_score(candidate.dense_score)} "
            f"phrase={format_optional_score(candidate.phrase_score)} "
            f"rerank={format_optional_score(candidate.lexical_rerank_score)} "
            f"fallback={format_optional_score(candidate.lexical_fallback_score)}"
        )
        print(f"   chunk_id: {candidate.chunk_id}")
        print(f"   source: {candidate.source}")
        print(f"   section: {candidate.section}")
    print("")


def print_retrieval_debug_info(debug_info: RetrievalDebugInfo) -> None:
    print("=== Этапы retrieval ===")
    print(f"dense search: {'on' if debug_info.dense_enabled else 'off'}")
    print(f"lexical rerank: {'on' if debug_info.lexical_rerank_enabled else 'off'}")
    print(f"lexical fallback: {'on' if debug_info.lexical_fallback_enabled else 'off'}")
    print(f"search depth: {debug_info.search_depth}")
    print("")

    print("Query variants:")
    if debug_info.query_variants:
        for variant in debug_info.query_variants:
            print(f"- {variant}")
    else:
        print("- none")
    print("")

    print("Embedding queries:")
    if debug_info.embedding_queries:
        for query in debug_info.embedding_queries:
            print(f"- {query}")
    else:
        print("- none")
    print("")

    print_candidate_table("Dense stage candidates:", debug_info.dense_candidates)
    print_candidate_table("After lexical rerank:", debug_info.reranked_candidates)
    print_candidate_table("Phrase stage candidates:", debug_info.phrase_candidates)
    print_candidate_table("Lexical fallback candidates:", debug_info.fallback_candidates)
    print_candidate_table("Final top-k:", debug_info.final_candidates)


def main() -> int:
    configure_stdio()
    args = parse_args()
    if args.disable_dense_search and args.disable_lexical_fallback:
        raise RuntimeError(
            "Нельзя одновременно отключить dense search и lexical fallback: retrieval не из чего будет собирать кандидатов."
        )
    index_file, metadata_file = resolve_retrieval_files(
        strategy=args.strategy,
        index_file=args.index_file,
        metadata_file=args.metadata_file,
    )

    retrieval_debug = RetrievalDebugInfo(
        query_variants=[],
        embedding_queries=[],
        search_depth=0,
        dense_enabled=not args.disable_dense_search,
        lexical_rerank_enabled=not args.disable_lexical_rerank,
        lexical_fallback_enabled=not args.disable_lexical_fallback,
        dense_candidates=[],
        reranked_candidates=[],
        phrase_candidates=[],
        fallback_candidates=[],
        final_candidates=[],
    )
    chunks = retrieve_chunks(
        question=args.question,
        index_file=index_file,
        metadata_file=metadata_file,
        embed_model=args.embed_model,
        ollama_url=args.ollama_url,
        top_k=args.top_k,
        enable_dense_search=not args.disable_dense_search,
        enable_lexical_rerank=not args.disable_lexical_rerank,
        enable_lexical_fallback=not args.disable_lexical_fallback,
        debug_info=retrieval_debug,
    )

    if args.retrieval_only:
        if args.show_retrieval_stages:
            print_retrieval_debug_info(retrieval_debug)
        print_chunks(chunks)
        return 0

    auth_token = args.auth_token.strip() or register_temporary_user(args.assistant_url)
    plain_prompt = args.question

    answer_without_rag = call_llm(
        assistant_url=args.assistant_url,
        auth_token=auth_token,
        model=args.assistant_model,
        prompt=plain_prompt,
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        user_id=args.user_id,
    )

    answer_with_rag = call_llm(
        assistant_url=args.assistant_url,
        auth_token=auth_token,
        model=args.assistant_model,
        prompt=build_rag_user_prompt(args.question, args.strategy, chunks),
        temperature=args.temperature,
        max_tokens=args.max_tokens,
        user_id=args.user_id,
    )

    if args.show_retrieval_stages:
        print_retrieval_debug_info(retrieval_debug)
    print_chunks(chunks)
    print("=== Ответ без RAG ===")
    print(answer_without_rag or "[Пустой ответ]")
    print("")
    print("=== Ответ с RAG ===")
    print(answer_with_rag or "[Пустой ответ]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
