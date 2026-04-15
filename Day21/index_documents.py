#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
import sys
import textwrap
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from pathlib import Path


SUPPORTED_EXTENSIONS = {".txt", ".md", ".pdf"}
TEXT_ENCODINGS = ("utf-8", "utf-8-sig", "cp1251", "cp866", "latin-1")
MAX_EMBED_WORDS = 350


@dataclass
class Document:
    source: str
    title: str
    text: str


@dataclass
class Chunk:
    chunk_id: str
    strategy: str
    source: str
    title: str
    section: str
    text: str
    start_char: int
    end_char: int
    token_estimate: int


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Индексация локальных документов с двумя стратегиями чанкинга и эмбеддингами через Ollama."
    )
    parser.add_argument(
        "--docs-dir",
        default="documents",
        help="Каталог с исходными документами (.txt, .md, .pdf). По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Каталог, куда сохраняются индексы и отчёты. По умолчанию: %(default)s",
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
        "--fixed-size",
        type=int,
        default=450,
        help="Целевой размер чанка для fixed-стратегии, в словах. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--fixed-overlap",
        type=int,
        default=75,
        help="Перекрытие в словах для fixed-size чанкинга. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--chunks-only",
        action="store_true",
        help="Сгенерировать только чанки и сравнение стратегий, без вызова Ollama.",
    )
    parser.add_argument(
        "--max-embed-words",
        type=int,
        default=MAX_EMBED_WORDS,
        help="Максимум слов в чанке, отправляемом в Ollama после автодробления. По умолчанию: %(default)s",
    )
    return parser.parse_args()


def load_documents(docs_dir: Path) -> list[Document]:
    if not docs_dir.exists():
        raise FileNotFoundError(f"Каталог с документами не найден: {docs_dir}")

    documents: list[Document] = []
    for path in sorted(p for p in docs_dir.rglob("*") if p.is_file() and p.suffix.lower() in SUPPORTED_EXTENSIONS):
        text = read_document_text(path)
        source = str(path.resolve())
        title = path.stem
        documents.append(Document(source=source, title=title, text=text))

    if not documents:
        raise ValueError(f"В каталоге {docs_dir} не найдено поддерживаемых документов")
    return documents


def read_document_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:
            raise RuntimeError(
                "Для поддержки PDF нужен пакет `pypdf`. Установите его командой `pip install pypdf` и запустите индексатор снова."
            ) from exc

        reader = PdfReader(str(path))
        pages: list[str] = []
        for page_number, page in enumerate(reader.pages, start=1):
            text = (page.extract_text() or "").strip()
            if text:
                pages.append(f"# Page {page_number}\n{text}")

        if not pages:
            raise RuntimeError(
                f"В PDF не найден извлекаемый текст: {path}. Если это скан, сначала добавьте OCR."
            )
        return "\n\n".join(pages)

    last_error: UnicodeDecodeError | None = None
    for encoding in TEXT_ENCODINGS:
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError as exc:
            last_error = exc

    raise RuntimeError(
        f"Не удалось прочитать текстовый файл {path} в поддерживаемых кодировках: {', '.join(TEXT_ENCODINGS)}"
    ) from last_error


def estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text.split()) * 1.3))


def build_embedding_input(chunk: Chunk) -> str:
    source_name = Path(chunk.source).name
    return "\n".join(
        [
            f"Title: {chunk.title}",
            f"Section: {chunk.section}",
            f"Source: {source_name}",
            "Content:",
            chunk.text,
        ]
    )


def chunk_by_fixed_size(document: Document, chunk_size_words: int, overlap_words: int) -> list[Chunk]:
    words = document.text.split()
    if not words:
        return []

    chunks: list[Chunk] = []
    start_word = 0
    chunk_index = 0
    cursor = 0

    while start_word < len(words):
        end_word = min(len(words), start_word + chunk_size_words)
        text = " ".join(words[start_word:end_word]).strip()
        if not text:
            break

        start_char = document.text.find(text[: min(30, len(text))], cursor)
        if start_char < 0:
            start_char = cursor
        end_char = start_char + len(text)
        cursor = end_char

        chunks.append(
            Chunk(
                chunk_id=f"{document.title}-fixed-{chunk_index:03d}",
                strategy="fixed",
                source=document.source,
                title=document.title,
                section="full_document",
                text=text,
                start_char=start_char,
                end_char=end_char,
                token_estimate=estimate_tokens(text),
            )
        )
        chunk_index += 1

        if end_word == len(words):
            break
        start_word = max(end_word - overlap_words, start_word + 1)

    return chunks


def split_markdown_sections(text: str) -> list[tuple[str, str]]:
    lines = text.splitlines()
    sections: list[tuple[str, list[str]]] = []
    current_title = "Introduction"
    current_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("#"):
            if current_lines:
                sections.append((current_title, current_lines))
            current_title = stripped.lstrip("#").strip() or "Untitled"
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines or not sections:
        sections.append((current_title, current_lines))

    return [(title, "\n".join(content).strip()) for title, content in sections if "\n".join(content).strip()]


def split_text_paragraphs(text: str) -> list[tuple[str, str]]:
    parts = [part.strip() for part in re.split(r"\n\s*\n+", text) if part.strip()]
    if not parts:
        cleaned = text.strip()
        return [("Full document", cleaned)] if cleaned else []
    return [(f"Paragraph block {index + 1}", part) for index, part in enumerate(parts)]


def split_pdf_pages(text: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_title = "Page 1"
    current_lines: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("# Page "):
            if current_lines:
                page_text = "\n".join(current_lines).strip()
                if page_text:
                    sections.append((current_title, page_text))
            current_title = stripped.lstrip("#").strip()
            current_lines = []
        else:
            current_lines.append(line)

    if current_lines:
        page_text = "\n".join(current_lines).strip()
        if page_text:
            sections.append((current_title, page_text))

    return sections


def chunk_by_structure(document: Document) -> list[Chunk]:
    suffix = Path(document.source).suffix.lower()
    if suffix == ".md":
        sections = split_markdown_sections(document.text)
    elif suffix == ".pdf":
        sections = split_pdf_pages(document.text)
    else:
        sections = split_text_paragraphs(document.text)

    chunks: list[Chunk] = []
    cursor = 0
    for index, (section, text) in enumerate(sections):
        start_char = document.text.find(text[: min(30, len(text))], cursor)
        if start_char < 0:
            start_char = cursor
        end_char = start_char + len(text)
        cursor = end_char

        chunks.append(
            Chunk(
                chunk_id=f"{document.title}-structure-{index:03d}",
                strategy="structure",
                source=document.source,
                title=document.title,
                section=section,
                text=text,
                start_char=start_char,
                end_char=end_char,
                token_estimate=estimate_tokens(text),
            )
        )
    return chunks


def split_oversized_chunk(chunk: Chunk, max_words: int = MAX_EMBED_WORDS) -> list[Chunk]:
    words = chunk.text.split()
    if len(words) <= max_words:
        return [chunk]

    subchunks: list[Chunk] = []
    start_word = 0
    part_index = 0

    while start_word < len(words):
        end_word = min(len(words), start_word + max_words)
        subtext = " ".join(words[start_word:end_word]).strip()
        if not subtext:
            break

        subchunks.append(
            Chunk(
                chunk_id=f"{chunk.chunk_id}-part{part_index:02d}",
                strategy=chunk.strategy,
                source=chunk.source,
                title=chunk.title,
                section=chunk.section,
                text=subtext,
                start_char=chunk.start_char,
                end_char=chunk.end_char,
                token_estimate=estimate_tokens(subtext),
            )
        )
        start_word = end_word
        part_index += 1

    return subchunks


def bisect_chunk(chunk: Chunk) -> list[Chunk]:
    words = chunk.text.split()
    if len(words) <= 1:
        raise RuntimeError(
            f"Не удалось дополнительно разделить слишком длинный чанк: {chunk.chunk_id}"
        )

    midpoint = len(words) // 2
    left_text = " ".join(words[:midpoint]).strip()
    right_text = " ".join(words[midpoint:]).strip()

    return [
        Chunk(
            chunk_id=f"{chunk.chunk_id}-a",
            strategy=chunk.strategy,
            source=chunk.source,
            title=chunk.title,
            section=chunk.section,
            text=left_text,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            token_estimate=estimate_tokens(left_text),
        ),
        Chunk(
            chunk_id=f"{chunk.chunk_id}-b",
            strategy=chunk.strategy,
            source=chunk.source,
            title=chunk.title,
            section=chunk.section,
            text=right_text,
            start_char=chunk.start_char,
            end_char=chunk.end_char,
            token_estimate=estimate_tokens(right_text),
        ),
    ]


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
            if exc.code == 500 and "input length exceeds the context length" in error_body:
                raise RuntimeError(
                    "Чанк слишком большой для контекстного окна embedding-модели Ollama."
                ) from exc

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


def build_index(chunks: list[Chunk], ollama_url: str, model: str) -> dict:
    items = []
    embedding_dimension = None

    for chunk in chunks:
        vector = call_ollama_embed(
            ollama_url=ollama_url,
            model=model,
            text=build_embedding_input(chunk),
        )
        embedding_dimension = embedding_dimension or len(vector)
        items.append(
            {
                "chunk": asdict(chunk),
                "embedding": vector,
            }
        )

    return {
        "model": model,
        "embedding_dimension": embedding_dimension,
        "chunk_count": len(items),
        "items": items,
    }


def build_index_for_documents(
    documents: list[Document],
    strategy: str,
    ollama_url: str,
    model: str,
    fixed_size_words: int,
    fixed_overlap_words: int,
    max_embed_words: int,
) -> tuple[list[Chunk], dict]:
    all_chunks: list[Chunk] = []
    items = []
    embedding_dimension = None

    for document in documents:
        print(f"[{strategy}] Обработка файла: {document.source}")
        if strategy == "fixed":
            document_chunks = chunk_by_fixed_size(
                document=document,
                chunk_size_words=fixed_size_words,
                overlap_words=fixed_overlap_words,
            )
        else:
            document_chunks = chunk_by_structure(document)

        expanded_chunks: list[Chunk] = []
        for chunk in document_chunks:
            expanded_chunks.extend(split_oversized_chunk(chunk, max_words=max_embed_words))

        if len(expanded_chunks) != len(document_chunks):
            print(
                f"[{strategy}] Разбиение слишком длинных чанков для {document.title}: "
                f"{len(document_chunks)} -> {len(expanded_chunks)}"
            )

        all_chunks.extend(expanded_chunks)
        total_chunks = len(expanded_chunks)

        for chunk_index, chunk in enumerate(expanded_chunks, start=1):
            print(
                f"[{strategy}] Чанк {chunk_index}/{total_chunks}: {chunk.chunk_id} "
                f"({document.title} -> {chunk.section})"
            )
            pending_chunks = [chunk]
            while pending_chunks:
                current_chunk = pending_chunks.pop(0)
                try:
                    vector = call_ollama_embed(
                        ollama_url=ollama_url,
                        model=model,
                        text=build_embedding_input(current_chunk),
                    )
                    embedding_dimension = embedding_dimension or len(vector)
                    items.append(
                        {
                            "chunk": asdict(current_chunk),
                            "embedding": vector,
                        }
                    )
                except RuntimeError as exc:
                    if "слишком большой" not in str(exc):
                        raise

                    split_chunks = bisect_chunk(current_chunk)
                    print(
                        f"[{strategy}] Дополнительное деление чанка {current_chunk.chunk_id}: "
                        f"{split_chunks[0].chunk_id}, {split_chunks[1].chunk_id}"
                    )
                    pending_chunks = split_chunks + pending_chunks

    return all_chunks, {
        "model": model,
        "embedding_dimension": embedding_dimension,
        "chunk_count": len(items),
        "items": items,
    }


def compare_strategies(indexes: dict[str, dict]) -> dict:
    comparison = {}
    for strategy, index in indexes.items():
        token_estimates = [item["chunk"]["token_estimate"] for item in index["items"]]
        comparison[strategy] = {
            "chunks": index["chunk_count"],
            "avg_tokens": round(sum(token_estimates) / len(token_estimates), 2) if token_estimates else 0,
            "min_tokens": min(token_estimates) if token_estimates else 0,
            "max_tokens": max(token_estimates) if token_estimates else 0,
        }

    fixed_chunks = comparison.get("fixed", {}).get("chunks", 0)
    structure_chunks = comparison.get("structure", {}).get("chunks", 0)

    if fixed_chunks > structure_chunks:
        summary = "Fixed-size чанкинг создал больше и более мелкие чанки, что может улучшить полноту поиска для узких запросов."
    elif fixed_chunks < structure_chunks:
        summary = "Structure-aware чанкинг создал больше секций, что говорит о хорошо выраженной структуре исходных документов."
    else:
        summary = "Обе стратегии дали одинаковое количество чанков на этом наборе документов."

    comparison["summary"] = summary
    comparison["recommendation"] = textwrap.dedent(
        """
        Используйте fixed-size чанкинг, когда нужен предсказуемый размер чанков и более стабильное поведение поиска.
        Используйте structure-aware чанкинг, когда важны заголовки разделов и естественные границы документа.
        """
    ).strip()
    return comparison


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_faiss_index(path: Path, index_payload: dict) -> None:
    try:
        import faiss
        import numpy as np
    except ImportError as exc:
        raise RuntimeError(
            "Для сохранения FAISS-индекса установите зависимости `pip install faiss-cpu numpy`."
        ) from exc

    vectors = np.array([item["embedding"] for item in index_payload["items"]], dtype="float32")
    if len(vectors) == 0:
        raise RuntimeError("Невозможно создать FAISS-индекс: список эмбеддингов пуст.")

    faiss.normalize_L2(vectors)
    index = faiss.IndexFlatIP(vectors.shape[1])
    index.add(vectors)
    faiss.write_index(index, str(path))


def write_markdown_report(path: Path, comparison: dict) -> None:
    lines = [
        "# Сравнение стратегий чанкинга",
        "",
        "| Стратегия | Чанков | Среднее токенов | Мин. токенов | Макс. токенов |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for strategy in ("fixed", "structure"):
        stats = comparison.get(strategy, {})
        lines.append(
            f"| {strategy} | {stats.get('chunks', 0)} | {stats.get('avg_tokens', 0)} | "
            f"{stats.get('min_tokens', 0)} | {stats.get('max_tokens', 0)} |"
        )

    lines.extend(
        [
            "",
            "## Вывод",
            "",
            comparison["summary"],
            "",
            "## Рекомендация",
            "",
            comparison["recommendation"],
            "",
        ]
    )
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    docs_dir = Path(args.docs_dir)
    output_dir = Path(args.output_dir)

    documents = load_documents(docs_dir)

    chunk_sets = {
        "fixed": [
            chunk
            for document in documents
            for chunk in chunk_by_fixed_size(
                document=document,
                chunk_size_words=args.fixed_size,
                overlap_words=args.fixed_overlap,
            )
        ],
        "structure": [chunk for document in documents for chunk in chunk_by_structure(document)],
    }

    for strategy, chunks in chunk_sets.items():
        write_json(
            output_dir / f"{strategy}_chunks.json",
            {
                "strategy": strategy,
                "chunk_count": len(chunks),
                "items": [asdict(chunk) for chunk in chunks],
            },
        )

    if args.chunks_only:
        comparison = compare_strategies(
            {
                strategy: {
                    "chunk_count": len(chunks),
                    "items": [{"chunk": asdict(chunk)} for chunk in chunks],
                }
                for strategy, chunks in chunk_sets.items()
            }
        )
        write_json(output_dir / "comparison.json", comparison)
        write_markdown_report(output_dir / "comparison.md", comparison)
        print(f"Файлы с чанками сохранены в {output_dir.resolve()}")
        for strategy, chunks in chunk_sets.items():
            print(f"- {strategy}: {len(chunks)} чанков")
        return 0

    try:
        fixed_chunks, fixed_index = build_index_for_documents(
            documents=documents,
            strategy="fixed",
            ollama_url=args.ollama_url,
            model=args.model,
            fixed_size_words=args.fixed_size,
            fixed_overlap_words=args.fixed_overlap,
            max_embed_words=args.max_embed_words,
        )
        structure_chunks, structure_index = build_index_for_documents(
            documents=documents,
            strategy="structure",
            ollama_url=args.ollama_url,
            model=args.model,
            fixed_size_words=args.fixed_size,
            fixed_overlap_words=args.fixed_overlap,
            max_embed_words=args.max_embed_words,
        )
        chunk_sets["fixed"] = fixed_chunks
        chunk_sets["structure"] = structure_chunks
        indexes = {
            "fixed": fixed_index,
            "structure": structure_index,
        }
    except RuntimeError as exc:
        print(str(exc), file=sys.stderr)
        print(
            "Подсказка: выполните `ollama pull nomic-embed-text` и `ollama serve`, либо используйте `--chunks-only` для офлайн-сравнения.",
            file=sys.stderr,
        )
        return 1

    comparison = compare_strategies(indexes)

    for strategy, index in indexes.items():
        write_json(output_dir / f"{strategy}_index.json", index)
        write_faiss_index(output_dir / f"{strategy}.faiss", index)
    write_json(output_dir / "comparison.json", comparison)
    write_markdown_report(output_dir / "comparison.md", comparison)

    print(f"Индексация завершена: {len(documents)} документов сохранено в {output_dir.resolve()}")
    for strategy, index in indexes.items():
        print(f"- {strategy}: {index['chunk_count']} чанков, размерность эмбеддинга {index['embedding_dimension']}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
