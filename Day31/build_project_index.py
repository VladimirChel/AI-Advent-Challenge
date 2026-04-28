from __future__ import annotations

import argparse
import os
from pathlib import Path

from project_index import build_project_index, slugify_project_id

try:
    from dotenv import load_dotenv
except ImportError:  # pragma: no cover
    load_dotenv = None


if load_dotenv is not None:
    load_dotenv(Path(__file__).with_name(".env"))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build a reusable RAG index for any local project and store it outside the project tree."
    )
    parser.add_argument("--project-root", required=True, help="Path to the target project root.")
    parser.add_argument("--project-id", default="", help="Stable project id used for the output folder name.")
    parser.add_argument(
        "--output-dir",
        default=os.getenv("INDEX_OUTPUT_DIR", "indexes"),
        help="Directory where project indexes are stored.",
    )
    parser.add_argument("--strategy", default="structure", choices=("fixed", "structure"))
    parser.add_argument("--model", default=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"), help="Ollama embedding model.")
    parser.add_argument("--ollama-url", default=os.getenv("OLLAMA_URL", "http://localhost:11434"), help="Ollama base URL.")
    parser.add_argument("--fixed-size", type=int, default=int(os.getenv("FIXED_CHUNK_SIZE", "450")))
    parser.add_argument("--fixed-overlap", type=int, default=int(os.getenv("FIXED_CHUNK_OVERLAP", "75")))
    parser.add_argument("--max-embed-words", type=int, default=int(os.getenv("MAX_EMBED_WORDS", "350")))
    parser.add_argument("--chunks-only", action="store_true", help="Save chunks and manifest without embeddings.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    if not project_root.exists() or not project_root.is_dir():
        raise SystemExit(f"Project root does not exist or is not a directory: {project_root}")

    project_id = (args.project_id or "").strip() or slugify_project_id(project_root)
    target_dir = (Path(args.output_dir).resolve() / project_id)
    result = build_project_index(
        project_root=project_root,
        project_id=project_id,
        output_dir=target_dir,
        strategy=args.strategy,
        ollama_url=args.ollama_url,
        model=args.model,
        fixed_size_words=args.fixed_size,
        fixed_overlap_words=args.fixed_overlap,
        max_embed_words=args.max_embed_words,
        chunks_only=args.chunks_only,
    )

    print(f"Project id: {result['project_id']}")
    print(f"Project root: {result['project_root']}")
    print(f"Strategy: {result['strategy']}")
    print(f"Documents: {result['documents_count']}")
    print(f"Chunks: {result['chunk_count']}")
    print(f"Chunks file: {result['chunks_file']}")
    if result["index_file"]:
        print(f"Index file: {result['index_file']}")
    print(f"Manifest file: {result['manifest_file']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
