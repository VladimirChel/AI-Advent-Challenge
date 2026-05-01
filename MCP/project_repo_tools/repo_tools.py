from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any


TEXT_EXTENSIONS = {
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
    ".html",
    ".css",
    ".xml",
}


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


def _iter_files(project_root: str, glob: str) -> list[Path]:
    root = _resolve_project_root(project_root)
    candidates = sorted(path for path in root.glob(glob) if path.is_file())
    result: list[Path] = []
    for path in candidates:
        resolved = path.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError("Glob matched path outside project root") from exc
        result.append(resolved)
    return result


def _filter_files(
    files: list[Path],
    *,
    root: Path,
    name_regex: str | None = None,
    path_regex: str | None = None,
    case_sensitive: bool = False,
) -> list[Path]:
    flags = 0 if case_sensitive else re.IGNORECASE
    compiled_name = re.compile(name_regex, flags) if name_regex else None
    compiled_path = re.compile(path_regex, flags) if path_regex else None
    result: list[Path] = []
    for path in files:
        relative_path = _relative(root, path)
        if compiled_name and not compiled_name.search(path.name):
            continue
        if compiled_path and not compiled_path.search(relative_path):
            continue
        result.append(path)
    return result


def _is_text_file(path: Path) -> bool:
    return path.suffix.lower() in TEXT_EXTENSIONS


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _relative(root: Path, path: Path) -> str:
    return path.relative_to(root).as_posix()


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


def tree_dir(
    project_root: str,
    path: str = ".",
    max_depth: int = 4,
    max_entries: int = 500,
) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    target = _resolve_inside_root(project_root, path)
    if not target.exists() or not target.is_dir():
        raise ValueError(f"Directory not found: {path}")
    if max_depth < 0 or max_depth > 20:
        raise ValueError("max_depth must be between 0 and 20")
    if max_entries < 1 or max_entries > 10000:
        raise ValueError("max_entries must be between 1 and 10000")

    entries_count = 0
    truncated = False

    def build_node(current: Path, depth: int) -> dict[str, Any]:
        nonlocal entries_count, truncated
        node: dict[str, Any] = {
            "name": current.name if current != target else (Path(path).name or current.name or "."),
            "path": _relative(root, current),
            "is_dir": current.is_dir(),
        }
        if not current.is_dir() or depth >= max_depth or truncated:
            return node

        children: list[dict[str, Any]] = []
        for child in sorted(current.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower())):
            if entries_count >= max_entries:
                truncated = True
                break
            entries_count += 1
            children.append(build_node(child, depth + 1))
        node["children"] = children
        return node

    tree = build_node(target, 0)
    return {
        "project_root": str(root),
        "path": str(target),
        "max_depth": max_depth,
        "max_entries": max_entries,
        "truncated": truncated,
        "entries_count": entries_count,
        "tree": tree,
    }


def read_file(project_root: str, path: str, max_chars: int = 12000) -> dict[str, object]:
    target = _resolve_inside_root(project_root, path)
    if not target.exists() or not target.is_file():
        raise ValueError(f"File not found: {path}")
    content = _read_text(target)
    truncated = len(content) > max_chars
    return {
        "project_root": str(_resolve_project_root(project_root)),
        "path": str(target),
        "truncated": truncated,
        "content": content[:max_chars],
    }


def find_files(
    project_root: str,
    glob: str = "**/*",
    max_results: int = 200,
    name_regex: str | None = None,
    path_regex: str | None = None,
    case_sensitive: bool = False,
) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    if max_results < 1 or max_results > 5000:
        raise ValueError("max_results must be between 1 and 5000")
    matches = _filter_files(
        _iter_files(project_root, glob),
        root=root,
        name_regex=name_regex,
        path_regex=path_regex,
        case_sensitive=case_sensitive,
    )
    truncated = len(matches) > max_results
    selected = matches[:max_results]
    return {
        "project_root": str(root),
        "glob": glob,
        "name_regex": name_regex,
        "path_regex": path_regex,
        "case_sensitive": case_sensitive,
        "truncated": truncated,
        "count": len(selected),
        "files": [_relative(root, path) for path in selected],
    }


def count_files(
    project_root: str,
    glob: str = "**/*",
    name_regex: str | None = None,
    path_regex: str | None = None,
    case_sensitive: bool = False,
) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    matches = _filter_files(
        _iter_files(project_root, glob),
        root=root,
        name_regex=name_regex,
        path_regex=path_regex,
        case_sensitive=case_sensitive,
    )
    return {
        "project_root": str(root),
        "glob": glob,
        "name_regex": name_regex,
        "path_regex": path_regex,
        "case_sensitive": case_sensitive,
        "count": len(matches),
    }


def search_text(
    project_root: str,
    pattern: str,
    glob: str = "**/*",
    case_sensitive: bool = False,
    max_results: int = 200,
    context_chars: int = 120,
) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    if not pattern:
        raise ValueError("pattern must not be empty")
    if max_results < 1 or max_results > 2000:
        raise ValueError("max_results must be between 1 and 2000")
    if context_chars < 20 or context_chars > 500:
        raise ValueError("context_chars must be between 20 and 500")

    flags = 0 if case_sensitive else re.IGNORECASE
    regex = re.compile(pattern, flags)
    matches: list[dict[str, object]] = []

    for path in _iter_files(project_root, glob):
        if not _is_text_file(path):
            continue
        text = _read_text(path)
        for match in regex.finditer(text):
            start = max(0, match.start() - context_chars)
            end = min(len(text), match.end() + context_chars)
            line_no = text.count("\n", 0, match.start()) + 1
            snippet = text[start:end].replace("\r", "")
            matches.append(
                {
                    "path": _relative(root, path),
                    "line": line_no,
                    "match": match.group(0),
                    "snippet": snippet.strip(),
                }
            )
            if len(matches) >= max_results:
                return {
                    "project_root": str(root),
                    "pattern": pattern,
                    "glob": glob,
                    "truncated": True,
                    "count": len(matches),
                    "matches": matches,
                }

    return {
        "project_root": str(root),
        "pattern": pattern,
        "glob": glob,
        "truncated": False,
        "count": len(matches),
        "matches": matches,
    }


def check_invariants(
    project_root: str,
    rules_path: str,
    glob: str = "**/*",
    max_files: int = 500,
) -> dict[str, object]:
    root = _resolve_project_root(project_root)
    rules_file = _resolve_inside_root(project_root, rules_path)
    if not rules_file.exists() or not rules_file.is_file():
        raise ValueError(f"Rules file not found: {rules_path}")

    payload = json.loads(_read_text(rules_file))
    rules = payload.get("rules")
    if not isinstance(rules, list):
        raise ValueError("Rules file must contain a top-level 'rules' array")

    files = _iter_files(project_root, glob)
    if len(files) > max_files:
        files = files[:max_files]

    violations: list[dict[str, Any]] = []
    checked_files: list[str] = []

    for path in files:
        if not _is_text_file(path):
            continue
        relative_path = _relative(root, path)
        checked_files.append(relative_path)
        text = _read_text(path)

        for raw_rule in rules:
            if not isinstance(raw_rule, dict):
                continue
            rule_id = str(raw_rule.get("id") or "unnamed-rule")
            file_glob = str(raw_rule.get("file_glob") or "**/*")
            if not path.match(file_glob):
                continue

            required_patterns = raw_rule.get("required_patterns") or []
            forbidden_patterns = raw_rule.get("forbidden_patterns") or []
            rule_flags = 0 if raw_rule.get("case_sensitive") else re.IGNORECASE

            for pattern in required_patterns:
                if not re.search(str(pattern), text, rule_flags):
                    violations.append(
                        {
                            "rule_id": rule_id,
                            "path": relative_path,
                            "type": "missing_required_pattern",
                            "pattern": str(pattern),
                        }
                    )

            for pattern in forbidden_patterns:
                if re.search(str(pattern), text, rule_flags):
                    violations.append(
                        {
                            "rule_id": rule_id,
                            "path": relative_path,
                            "type": "forbidden_pattern_found",
                            "pattern": str(pattern),
                        }
                    )

    return {
        "project_root": str(root),
        "rules_path": _relative(root, rules_file),
        "glob": glob,
        "checked_files": checked_files,
        "violations_count": len(violations),
        "violations": violations,
    }


def create_document(
    project_root: str,
    path: str,
    file_type: str,
    title: str = "",
    content: str = "",
) -> dict[str, object]:
    target = _resolve_inside_root(project_root, path)
    normalized_type = file_type.strip().lower()
    file_name = target.name.lower()

    if normalized_type == "readme_md":
        if file_name != "readme.md":
            raise ValueError("readme_md can only create a file named README.md")
        final_content = content.strip() or f"# {title.strip() or 'README'}\n"
    elif normalized_type == "report_html":
        if file_name != "report.html":
            raise ValueError("report_html can only create a file named report.html")
        final_content = content.strip() or (
            "<!doctype html>\n"
            "<html lang=\"en\">\n"
            "<head>\n"
            "  <meta charset=\"utf-8\">\n"
            f"  <title>{title.strip() or 'Report'}</title>\n"
            "</head>\n"
            "<body>\n"
            f"  <h1>{title.strip() or 'Report'}</h1>\n"
            "</body>\n"
            "</html>\n"
        )
    else:
        raise ValueError("file_type must be 'readme_md' or 'report_html'")

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(final_content, encoding="utf-8")
    return {
        "project_root": str(_resolve_project_root(project_root)),
        "path": str(target),
        "file_type": normalized_type,
        "bytes_written": len(final_content.encode("utf-8")),
    }
