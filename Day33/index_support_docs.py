from __future__ import annotations

import sys
from pathlib import Path

from config import DAY21_DIR, DOCS_DIR, OUTPUT_DIR


if __name__ == "__main__":
    script_path = DAY21_DIR / "index_strategy.py"
    if not script_path.exists():
        raise SystemExit(f"Day21 indexer not found: {script_path}")
    import subprocess

    command = [
        sys.executable,
        str(script_path),
        "--strategy",
        "structure",
        "--docs-dir",
        str(DOCS_DIR),
        "--output-dir",
        str(OUTPUT_DIR),
        "--model",
        "nomic-embed-text",
    ]
    raise SystemExit(subprocess.call(command, cwd=str(Path(__file__).resolve().parent)))
