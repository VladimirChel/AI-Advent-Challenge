from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from project_index import discover_project_documents


TEXT_FILE_EXTENSIONS = {
    ".py",
    ".md",
    ".txt",
    ".rst",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".ini",
    ".cfg",
    ".sql",
    ".js",
    ".ts",
    ".tsx",
    ".jsx",
    ".go",
    ".java",
    ".cs",
    ".proto",
    ".sh",
}
STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "from",
    "that",
    "this",
    "into",
    "were",
    "have",
    "has",
    "had",
    "true",
    "false",
    "null",
    "none",
    "return",
    "class",
    "def",
    "self",
    "base",
    "head",
    "pull",
    "request",
    "changed",
    "diff",
}


@dataclass(slots=True)
class RetrievedChunk:
    source: str
    section: str
    text: str
    score: int
    chunk_type: str


def _tokenize(text: str) -> set[str]:
    tokens = set(re.findall(r"[A-Za-z_][A-Za-z0-9_]{2,}", text.lower()))
    return {token for token in tokens if token not in STOP_WORDS}


def _score_text(text: str, query_tokens: set[str]) -> int:
    if not text or not query_tokens:
        return 0
    return len(_tokenize(text) & query_tokens)


def _load_doc_chunks_from_index(index_dir: Path | None, project_id: str | None) -> list[RetrievedChunk]:
    if index_dir is None or not project_id:
        return []

    chunks_file = index_dir / project_id / "structure_chunks.json"
    if not chunks_file.exists():
        return []

    payload = json.loads(chunks_file.read_text(encoding="utf-8"))
    items = payload.get("items") or []
    chunks: list[RetrievedChunk] = []
    for item in items:
        chunks.append(
            RetrievedChunk(
                source=str(item.get("source") or "unknown"),
                section=str(item.get("section") or item.get("title") or "documentation"),
                text=str(item.get("text") or ""),
                score=0,
                chunk_type=str(item.get("doc_type") or "doc"),
            )
        )
    return chunks


def _load_doc_chunks_from_repo(project_root: Path) -> list[RetrievedChunk]:
    chunks: list[RetrievedChunk] = []
    for path in discover_project_documents(project_root):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                text = path.read_text(encoding="utf-8-sig")
            except UnicodeDecodeError:
                continue
        relative = path.relative_to(project_root).as_posix()
        chunks.append(
            RetrievedChunk(
                source=relative,
                section=path.stem,
                text=text[:4_000],
                score=0,
                chunk_type="doc",
            )
        )
    return chunks


def _split_code_chunks(relative_path: str, text: str, max_lines: int = 80) -> list[RetrievedChunk]:
    lines = text.splitlines()
    if not lines:
        return []

    chunks: list[RetrievedChunk] = []
    for index in range(0, len(lines), max_lines):
        window = lines[index:index + max_lines]
        start_line = index + 1
        end_line = index + len(window)
        chunks.append(
            RetrievedChunk(
                source=relative_path,
                section=f"lines {start_line}-{end_line}",
                text="\n".join(window),
                score=0,
                chunk_type="code",
            )
        )
    return chunks


def _collect_related_code_files(project_root: Path, changed_paths: list[str]) -> list[Path]:
    candidates: dict[str, Path] = {}

    for relative_path in changed_paths:
        target = project_root / relative_path
        if target.exists() and target.is_file():
            candidates[relative_path] = target

        parent = target.parent
        if parent.exists():
            for sibling in parent.iterdir():
                if sibling.is_file() and sibling.suffix.lower() in TEXT_FILE_EXTENSIONS:
                    rel = sibling.relative_to(project_root).as_posix()
                    candidates.setdefault(rel, sibling)

    return list(candidates.values())


def retrieve_review_context(
    *,
    project_root: Path,
    diff_text: str,
    changed_paths: list[str],
    index_dir: Path | None,
    project_id: str | None,
    top_k_docs: int = 4,
    top_k_code: int = 6,
) -> tuple[list[RetrievedChunk], list[RetrievedChunk]]:
    query_text = "\n".join(changed_paths) + "\n" + diff_text
    query_tokens = _tokenize(query_text)

    doc_candidates = _load_doc_chunks_from_index(index_dir, project_id)
    if not doc_candidates:
        doc_candidates = _load_doc_chunks_from_repo(project_root)

    for chunk in doc_candidates:
        chunk.score = _score_text(chunk.source + "\n" + chunk.section + "\n" + chunk.text, query_tokens)
    top_docs = [chunk for chunk in sorted(doc_candidates, key=lambda item: item.score, reverse=True) if chunk.score > 0][:top_k_docs]

    code_candidates: list[RetrievedChunk] = []
    for path in _collect_related_code_files(project_root, changed_paths):
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        relative = path.relative_to(project_root).as_posix()
        code_candidates.extend(_split_code_chunks(relative, text))

    for chunk in code_candidates:
        chunk.score = _score_text(chunk.source + "\n" + chunk.text, query_tokens)
    top_code = [chunk for chunk in sorted(code_candidates, key=lambda item: item.score, reverse=True) if chunk.score > 0][:top_k_code]

    return top_docs, top_code
