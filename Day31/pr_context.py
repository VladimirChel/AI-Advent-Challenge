from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ChangedFile:
    path: str
    status: str
    patch: str
    head_content: str | None


@dataclass(slots=True)
class PullRequestContext:
    base_ref: str
    head_ref: str
    merge_base: str
    changed_files: list[ChangedFile]
    diff_text: str


def _run_git(repo_root: Path, *args: str) -> str:
    completed = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    return completed.stdout


def _resolve_merge_base(repo_root: Path, base_ref: str, head_ref: str) -> str:
    return _run_git(repo_root, "merge-base", base_ref, head_ref).strip()


def _read_head_file(repo_root: Path, relative_path: str) -> str | None:
    target = repo_root / relative_path
    if not target.exists() or not target.is_file():
        return None

    for encoding in ("utf-8", "utf-8-sig", "cp1251", "cp866", "latin-1"):
        try:
            return target.read_text(encoding=encoding)
        except UnicodeDecodeError:
            continue
    return None


def collect_pr_context(
    *,
    repo_root: Path,
    base_ref: str,
    head_ref: str,
    max_diff_chars: int = 120_000,
    max_patch_chars_per_file: int = 12_000,
) -> PullRequestContext:
    merge_base = _resolve_merge_base(repo_root, base_ref, head_ref)
    diff_range = f"{merge_base}..{head_ref}"
    raw_diff = _run_git(repo_root, "diff", "--no-color", "--unified=3", diff_range)
    diff_text = raw_diff[:max_diff_chars]

    name_status = _run_git(repo_root, "diff", "--name-status", diff_range)
    changed_files: list[ChangedFile] = []

    for line in name_status.splitlines():
        if not line.strip():
            continue

        parts = line.split("\t", maxsplit=1)
        if len(parts) != 2:
            continue

        status, relative_path = parts
        patch = _run_git(repo_root, "diff", "--no-color", "--unified=3", diff_range, "--", relative_path)
        changed_files.append(
            ChangedFile(
                path=relative_path,
                status=status,
                patch=patch[:max_patch_chars_per_file],
                head_content=_read_head_file(repo_root, relative_path),
            )
        )

    return PullRequestContext(
        base_ref=base_ref,
        head_ref=head_ref,
        merge_base=merge_base,
        changed_files=changed_files,
        diff_text=diff_text,
    )
