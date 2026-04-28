from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parent
DAY21_INDEXER = ROOT_DIR.parent / "Day21" / "index_documents.py"

SUPPORTED_FILENAMES = {"readme.md", "readme.txt"}
SUPPORTED_DOC_EXTENSIONS = {".md", ".txt", ".rst", ".json", ".yaml", ".yml", ".sql", ".proto"}
STRUCTURE_DIR_NAMES = {"docs", "doc", "documentation", "schema", "schemas", "openapi", "api"}


def _load_day21_indexer() -> Any:
    spec = importlib.util.spec_from_file_location("day21_index_documents", DAY21_INDEXER)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Unable to load Day21 indexer from {DAY21_INDEXER}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


_DAY21 = _load_day21_indexer()
Document = _DAY21.Document


def slugify_project_id(project_root: Path) -> str:
    raw = project_root.name.strip().lower()
    slug = "".join(ch if ch.isalnum() else "-" for ch in raw).strip("-")
    return slug or "project"


def discover_project_documents(project_root: Path) -> list[Path]:
    paths: list[Path] = []
    seen: set[Path] = set()

    for child in project_root.iterdir():
        if not child.is_file():
            continue
        if child.name.lower() in SUPPORTED_FILENAMES:
            resolved = child.resolve()
            if resolved not in seen:
                seen.add(resolved)
                paths.append(resolved)

    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in SUPPORTED_DOC_EXTENSIONS:
            continue
        if not _should_include_path(project_root, path):
            continue
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            paths.append(resolved)

    return sorted(paths)


def _should_include_path(project_root: Path, path: Path) -> bool:
    relative_parts = [part.lower() for part in path.relative_to(project_root).parts]
    lower_name = path.name.lower()

    if lower_name in SUPPORTED_FILENAMES:
        return True
    if any(part in STRUCTURE_DIR_NAMES for part in relative_parts[:-1]):
        return True
    if lower_name.startswith(("openapi", "swagger")):
        return True
    if lower_name.endswith((".schema.json", ".schema.yaml", ".schema.yml")):
        return True
    if lower_name in {"schema.sql", "api.json", "api.yaml", "api.yml"}:
        return True
    return False


def load_project_documents(project_root: Path) -> list[Document]:
    documents: list[Document] = []
    for path in discover_project_documents(project_root):
        text = _read_text_document(path)
        relative_path = path.relative_to(project_root).as_posix()
        title = path.stem
        documents.append(Document(source=relative_path, title=title, text=text))

    if not documents:
        raise RuntimeError(f"No supported project documents found in {project_root}")
    return documents


def _read_text_document(path: Path) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251", "cp866", "latin-1"):
        try:
            return path.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    raise RuntimeError(f"Unable to read {path} using supported encodings")


def classify_doc_type(source: str) -> str:
    source_lower = source.lower()
    name = Path(source_lower).name
    if name in SUPPORTED_FILENAMES:
        return "readme"
    if any(part in STRUCTURE_DIR_NAMES for part in Path(source_lower).parts[:-1]):
        return "docs"
    if name.startswith(("openapi", "swagger")) or "/api/" in source_lower or name in {"api.json", "api.yaml", "api.yml"}:
        return "api"
    if name.endswith((".schema.json", ".schema.yaml", ".schema.yml")) or name in {"schema.sql"}:
        return "schema"
    return "doc"


def build_project_index(
    *,
    project_root: Path,
    project_id: str,
    output_dir: Path,
    strategy: str,
    ollama_url: str,
    model: str,
    fixed_size_words: int,
    fixed_overlap_words: int,
    max_embed_words: int,
    chunks_only: bool,
) -> dict[str, Any]:
    documents = load_project_documents(project_root)

    strategy_name = strategy.strip().lower()
    if strategy_name not in {"fixed", "structure"}:
        raise RuntimeError(f"Unsupported strategy: {strategy}")

    if strategy_name == "fixed":
        chunks = [
            chunk
            for document in documents
            for chunk in _DAY21.chunk_by_fixed_size(
                document=document,
                chunk_size_words=fixed_size_words,
                overlap_words=fixed_overlap_words,
            )
        ]
    else:
        chunks = [chunk for document in documents for chunk in _DAY21.chunk_by_structure(document)]

    chunk_items = []
    for chunk in chunks:
        item = asdict(chunk)
        item["doc_type"] = classify_doc_type(item["source"])
        chunk_items.append(item)

    output_dir.mkdir(parents=True, exist_ok=True)
    chunks_file = output_dir / f"{strategy_name}_chunks.json"
    chunks_file.write_text(
        json.dumps(
            {
                "project_id": project_id,
                "project_root": str(project_root.resolve()),
                "strategy": strategy_name,
                "chunk_count": len(chunk_items),
                "items": chunk_items,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result: dict[str, Any] = {
        "project_id": project_id,
        "project_root": str(project_root.resolve()),
        "strategy": strategy_name,
        "embed_model": model,
        "ollama_url": ollama_url,
        "documents_count": len(documents),
        "chunk_count": len(chunk_items),
        "chunks_file": str(chunks_file.resolve()),
        "index_file": None,
        "index_payload_file": None,
    }

    if not chunks_only:
        _, index_payload = _DAY21.build_index_for_documents(
            documents=documents,
            strategy=strategy_name,
            ollama_url=ollama_url,
            model=model,
            fixed_size_words=fixed_size_words,
            fixed_overlap_words=fixed_overlap_words,
            max_embed_words=max_embed_words,
        )
        index_payload_file = output_dir / f"{strategy_name}_index.json"
        index_file = output_dir / f"{strategy_name}.faiss"
        _DAY21.write_json(index_payload_file, index_payload)
        _DAY21.write_faiss_index(index_file, index_payload)
        result["index_file"] = str(index_file.resolve())
        result["index_payload_file"] = str(index_payload_file.resolve())
        result["embedding_dimension"] = index_payload.get("embedding_dimension")

    manifest = {
        **result,
        "created_from": "Day31/build_project_index.py",
    }
    manifest_file = output_dir / "manifest.json"
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    result["manifest_file"] = str(manifest_file.resolve())
    return result
