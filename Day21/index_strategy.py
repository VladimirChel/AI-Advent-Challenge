#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from dataclasses import asdict
from pathlib import Path

from index_documents import (
    build_index_for_documents,
    chunk_by_fixed_size,
    chunk_by_structure,
    load_documents,
    write_faiss_index,
    write_json,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Индексация документов только для одной выбранной стратегии чанкинга."
    )
    parser.add_argument(
        "--strategy",
        required=True,
        choices=("fixed", "structure"),
        help="Стратегия чанкинга: fixed или structure.",
    )
    parser.add_argument(
        "--docs-dir",
        default="documents",
        help="Каталог с исходными документами. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Каталог для результатов. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--model",
        default="nomic-embed-text",
        help="Embedding-модель Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="URL локального сервера Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--fixed-size",
        type=int,
        default=450,
        help="Размер чанка в словах для fixed-стратегии. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--fixed-overlap",
        type=int,
        default=75,
        help="Перекрытие чанков в словах для fixed-стратегии. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--chunks-only",
        action="store_true",
        help="Сгенерировать только JSON с чанками без embedding и FAISS.",
    )
    parser.add_argument(
        "--max-embed-words",
        type=int,
        default=350,
        help="Максимум слов в чанке перед автоделением для embedding. По умолчанию: %(default)s",
    )
    return parser.parse_args()


def build_chunks(documents: list, strategy: str, fixed_size: int, fixed_overlap: int) -> list:
    if strategy == "fixed":
        return [
            chunk
            for document in documents
            for chunk in chunk_by_fixed_size(
                document=document,
                chunk_size_words=fixed_size,
                overlap_words=fixed_overlap,
            )
        ]
    return [chunk for document in documents for chunk in chunk_by_structure(document)]


def main() -> int:
    args = parse_args()
    docs_dir = Path(args.docs_dir)
    output_dir = Path(args.output_dir)

    documents = load_documents(docs_dir)
    chunks = build_chunks(
        documents=documents,
        strategy=args.strategy,
        fixed_size=args.fixed_size,
        fixed_overlap=args.fixed_overlap,
    )

    write_json(
        output_dir / f"{args.strategy}_chunks.json",
        {
            "strategy": args.strategy,
            "chunk_count": len(chunks),
            "items": [asdict(chunk) for chunk in chunks],
        },
    )

    if args.chunks_only:
        print(f"Чанки сохранены: {output_dir.resolve()}")
        print(f"- {args.strategy}: {len(chunks)} чанков")
        return 0

    try:
        _, index_payload = build_index_for_documents(
            documents=documents,
            strategy=args.strategy,
            ollama_url=args.ollama_url,
            model=args.model,
            fixed_size_words=args.fixed_size,
            fixed_overlap_words=args.fixed_overlap,
            max_embed_words=args.max_embed_words,
        )
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Подсказка: проверьте `ollama serve` и модель embedding, либо используйте `--chunks-only`.",
            file=sys.stderr,
        )
        return 1

    write_json(output_dir / f"{args.strategy}_index.json", index_payload)
    write_faiss_index(output_dir / f"{args.strategy}.faiss", index_payload)

    print(f"Индексация завершена: {len(documents)} документов сохранено в {output_dir.resolve()}")
    print(
        f"- {args.strategy}: {index_payload['chunk_count']} чанков, "
        f"размерность эмбеддинга {index_payload['embedding_dimension']}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
