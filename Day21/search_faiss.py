#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import urllib.error
import urllib.request


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Поиск по локальному FAISS-индексу с эмбеддингами Ollama."
    )
    parser.add_argument("query", help="Текст запроса для поиска по индексу.")
    parser.add_argument(
        "--index-file",
        default="output/structure.faiss",
        help="Путь к FAISS-индексу. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--metadata-file",
        default="output/structure_index.json",
        help="Путь к JSON-файлу с чанками и метаданными. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--model",
        default="nomic-embed-text",
        help="Embedding-модель Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="Базовый URL локального сервера Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько лучших совпадений вернуть. По умолчанию: %(default)s",
    )
    return parser.parse_args()


def call_ollama_embed(ollama_url: str, model: str, text: str) -> list[float]:
    normalized_url = ollama_url.rstrip("/")
    payloads = [
        (f"{normalized_url}/api/embed", {"model": model, "input": text}),
        (f"{normalized_url}/api/embeddings", {"model": model, "prompt": text}),
    ]

    last_error: Exception | None = None
    for url, payload in payloads:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=120) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(
                f"Ollama request failed for {url} with HTTP {exc.code}: {error_body}"
            )
            continue
        except urllib.error.URLError as exc:
            raise RuntimeError(
                "Не удаётся подключиться к Ollama. Запустите локальный сервер командой `ollama serve` и проверьте URL."
            ) from exc

        embeddings = data.get("embeddings")
        if isinstance(embeddings, list) and embeddings:
            return embeddings[0]

        embedding = data.get("embedding")
        if isinstance(embedding, list) and embedding:
            return embedding

        last_error = RuntimeError(f"Unexpected Ollama response format from {url}: {data}")

    raise last_error or RuntimeError("Не удалось получить эмбеддинг из Ollama.")


def main() -> int:
    args = parse_args()

    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Для поиска через FAISS установите зависимости `pip install faiss-cpu numpy`."
        ) from exc

    index_path = Path(args.index_file)
    metadata_path = Path(args.metadata_file)

    if not index_path.exists():
        raise FileNotFoundError(f"FAISS-индекс не найден: {index_path}")
    if not metadata_path.exists():
        raise FileNotFoundError(f"Файл метаданных не найден: {metadata_path}")

    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    items = metadata["items"]

    query_embedding = call_ollama_embed(
        ollama_url=args.ollama_url,
        model=args.model,
        text=args.query,
    )

    query_vector = np.array([query_embedding], dtype="float32")
    faiss.normalize_L2(query_vector)

    index = faiss.read_index(str(index_path))
    distances, indices = index.search(query_vector, args.top_k)

    print(f"Запрос: {args.query}")
    print(f"Индекс: {index_path}")
    print("")

    for rank, (score, idx) in enumerate(zip(distances[0], indices[0]), start=1):
        if idx < 0 or idx >= len(items):
            continue

        chunk = items[idx]["chunk"]
        snippet = " ".join(chunk["text"].split())[:280]
        print(f"{rank}. score={score:.4f}")
        print(f"   chunk_id: {chunk['chunk_id']}")
        print(f"   source: {chunk['source']}")
        print(f"   section: {chunk['section']}")
        print(f"   text: {snippet}")
        print("")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
