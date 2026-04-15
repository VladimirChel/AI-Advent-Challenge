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
    candidate_scores: dict[int, float] = {}
    query_variants = build_query_variants(question)
    embedding_queries = build_embedding_queries(question)
    search_depth = min(len(items), max(top_k * 10, 20))

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
            reranked_score = float(score) + lexical_boost(query_variant, items[idx])
            previous = candidate_scores.get(idx)
            if previous is None or reranked_score > previous:
                candidate_scores[idx] = reranked_score

    for idx, raw_item in enumerate(items):
        lexical_score = max(lexical_boost(query_variant, raw_item) for query_variant in query_variants)
        if lexical_score <= 0:
            continue
        # Keyword fallback helps when the exact topic appears in title/source,
        # but the dense embedding search ranks the chunk too low.
        fallback_score = 0.5 + lexical_score
        previous = candidate_scores.get(idx)
        if previous is None or fallback_score > previous:
            candidate_scores[idx] = fallback_score

    ranked_indices = sorted(candidate_scores.items(), key=lambda item: item[1], reverse=True)[:top_k]

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

    return (
        matched_full * 0.03
        + fuzzy_full * 0.02
        + matched_title_source * 0.16
        + fuzzy_title_source * 0.12
        + phrase_bonus
    )


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


def main() -> int:
    configure_stdio()
    args = parse_args()
    index_file, metadata_file = resolve_retrieval_files(
        strategy=args.strategy,
        index_file=args.index_file,
        metadata_file=args.metadata_file,
    )

    chunks = retrieve_chunks(
        question=args.question,
        index_file=index_file,
        metadata_file=metadata_file,
        embed_model=args.embed_model,
        ollama_url=args.ollama_url,
        top_k=args.top_k,
    )

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

    print_chunks(chunks)
    print("=== Ответ без RAG ===")
    print(answer_without_rag or "[Пустой ответ]")
    print("")
    print("=== Ответ с RAG ===")
    print(answer_with_rag or "[Пустой ответ]")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
