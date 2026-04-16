#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent
RAG_COMPARE_PATH = ROOT_DIR / "rag_compare.py"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Запускает rag_compare.py в трёх режимах retrieval и показывает top-k чанков "
            "для каждого варианта поиска."
        )
    )
    parser.add_argument("question", help="Вопрос для сравнения режимов поиска.")
    parser.add_argument(
        "--strategy",
        choices=("fixed", "structure"),
        default="structure",
        help="Стратегия retrieval. По умолчанию: %(default)s",
    )
    parser.add_argument("--index-file", default="", help="Путь к FAISS-индексу.")
    parser.add_argument("--metadata-file", default="", help="Путь к metadata JSON.")
    parser.add_argument(
        "--embed-model",
        default="bge-m3",
        help="Embedding-модель Ollama для retrieval. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-url",
        default="http://localhost:11434",
        help="URL локального Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument("--top-k", type=int, default=5, help="Сколько чанков показывать.")
    parser.add_argument(
        "--show-retrieval-stages",
        action="store_true",
        help="Пробросить в rag_compare.py подробный вывод этапов retrieval.",
    )
    return parser.parse_args()


def build_base_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(RAG_COMPARE_PATH),
        args.question,
        "--strategy",
        args.strategy,
        "--embed-model",
        args.embed_model,
        "--ollama-url",
        args.ollama_url,
        "--top-k",
        str(args.top_k),
        "--retrieval-only",
    ]
    if args.index_file.strip():
        command.extend(["--index-file", args.index_file])
    if args.metadata_file.strip():
        command.extend(["--metadata-file", args.metadata_file])
    if args.show_retrieval_stages:
        command.append("--show-retrieval-stages")
    return command


def run_mode(title: str, extra_args: list[str], base_command: list[str]) -> tuple[int, str, str]:
    command = [*base_command, *extra_args]
    result = subprocess.run(
        command,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    header = f"=== {title} ==="
    stdout = result.stdout.strip()
    stderr = result.stderr.strip()
    return result.returncode, "\n".join(filter(None, [header, stdout])), stderr


def main() -> int:
    args = parse_args()
    base_command = build_base_command(args)
    modes = [
        ("Все этапы включены", []),
        ("Выключен lexical-rerank", ["--disable-lexical-rerank"]),
        ("Выключен lexical-fallback", ["--disable-lexical-fallback"]),
    ]

    exit_code = 0
    outputs: list[str] = []
    errors: list[str] = []

    for title, extra_args in modes:
        code, output, stderr = run_mode(title, extra_args, base_command)
        outputs.append(output)
        if code != 0:
            exit_code = code
            if stderr:
                errors.append(f"=== {title}: stderr ===\n{stderr}")

    print("\n\n".join(outputs))
    if errors:
        print("")
        print("\n\n".join(errors), file=sys.stderr)
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
