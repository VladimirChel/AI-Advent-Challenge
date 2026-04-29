from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from pr_context import collect_pr_context
from pr_retriever import retrieve_review_context
from review_generator import generate_review


DEFAULT_LLM_ASSISTANT_URL = "http://127.0.0.1:8000"
DEFAULT_LLM_ASSISTANT_PROVIDER_ID = "cloud"
DEFAULT_LLM_ASSISTANT_MODEL = "openai/gpt-4.1-mini-2025-04-14"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run local AI review for a pull request diff.")
    parser.add_argument("--repo-root", required=True, help="Git repository root.")
    parser.add_argument("--project-root", default="", help="Project root used for RAG lookup. Defaults to repo root.")
    parser.add_argument("--project-id", default="", help="Project id used to locate a prebuilt index.")
    parser.add_argument("--index-dir", default="", help="Directory containing prebuilt project indexes.")
    parser.add_argument("--base-ref", required=True, help="Base commit/ref for the PR.")
    parser.add_argument("--head-ref", required=True, help="Head commit/ref for the PR.")
    parser.add_argument("--output-file", default="", help="Optional output markdown file.")
    parser.add_argument("--metadata-file", default="", help="Optional JSON file with retrieval metadata.")
    parser.add_argument("--dry-run", action="store_true", help="Skip the model call and emit a placeholder review.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    os.environ.setdefault("LLM_ASSISTANT_URL", DEFAULT_LLM_ASSISTANT_URL)
    os.environ.setdefault("LLM_ASSISTANT_PROVIDER_ID", DEFAULT_LLM_ASSISTANT_PROVIDER_ID)
    os.environ.setdefault("LLM_ASSISTANT_MODEL", DEFAULT_LLM_ASSISTANT_MODEL)

    repo_root = Path(args.repo_root).resolve()
    project_root = Path(args.project_root).resolve() if args.project_root else repo_root
    index_dir = Path(args.index_dir).resolve() if args.index_dir else None
    project_id = args.project_id.strip() or project_root.name.lower()

    context = collect_pr_context(
        repo_root=repo_root,
        base_ref=args.base_ref,
        head_ref=args.head_ref,
    )
    changed_paths = [item.path for item in context.changed_files]
    docs_chunks, code_chunks = retrieve_review_context(
        project_root=project_root,
        diff_text=context.diff_text,
        changed_paths=changed_paths,
        index_dir=index_dir,
        project_id=project_id,
    )
    review = generate_review(
        context=context,
        docs_chunks=docs_chunks,
        code_chunks=code_chunks,
        dry_run=args.dry_run,
    )

    if args.output_file:
        output_path = Path(args.output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(review.markdown, encoding="utf-8")
    else:
        print(review.markdown)

    if args.metadata_file:
        metadata_path = Path(args.metadata_file)
        metadata_path.parent.mkdir(parents=True, exist_ok=True)
        metadata = {
            "base_ref": context.base_ref,
            "head_ref": context.head_ref,
            "merge_base": context.merge_base,
            "changed_files": [{"path": item.path, "status": item.status} for item in context.changed_files],
            "docs_sources": [{"source": item.source, "section": item.section, "score": item.score} for item in docs_chunks],
            "code_sources": [{"source": item.source, "section": item.section, "score": item.score} for item in code_chunks],
            "raw_response": review.raw_response,
        }
        metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
