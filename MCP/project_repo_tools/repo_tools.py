from __future__ import annotations

import subprocess
from pathlib import Path


def _resolve_project_root(project_root: str) -> Path:
    root = Path(project_root).resolve()
    if not root.exists() or not root.is_dir():
        raise ValueError(f"Project root is not a directory: {project_root}")
    return root


def _resolve_inside_root(project_root: str, path: str) -> Path:
    root = _resolve_project_root(project_root)
    candidate = (root / path).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError("Path escapes project root") from exc
    return candidate


def git_branch(project_root: str) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    result = subprocess.run(
        ["git", "branch", "--list"],
        cwd=root,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git branch failed")
    branches = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    return {"project_root": str(root), "branches": branches}


def list_dir(project_root: str, path: str = ".") -> dict[str, object]:
    target = _resolve_inside_root(project_root, path)
    if not target.exists() or not target.is_dir():
        raise ValueError(f"Directory not found: {path}")
    entries = []
    for child in sorted(target.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
        entries.append({"name": child.name, "is_dir": child.is_dir()})
    return {
        "project_root": str(_resolve_project_root(project_root)),
        "path": str(target),
        "entries": entries,
    }


def read_file(project_root: str, path: str, max_chars: int = 12000) -> dict[str, object]:
    target = _resolve_inside_root(project_root, path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"File not found: {path}")
    content = target.read_text(encoding="utf-8", errors="replace")
    truncated = len(content) > max_chars
    return {
        "project_root": str(_resolve_project_root(project_root)),
        "path": str(target),
        "truncated": truncated,
        "content": content[:max_chars],
    }
