#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from build_eval_report import QuestionSpec, build_eval_rag_prompt, sanitize_retrieval_query
from llm_backends import (
    DEFAULT_ASSISTANT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    generate_text,
    resolve_auth_token,
)
from rag_compare import (
    RetrievedChunk,
    build_rag_user_prompt,
    configure_stdio,
    resolve_retrieval_files,
    retrieve_chunks,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Сравнивает два RAG-пайплайна Day22 на одном вопросе: rag_compare.py и build_eval_report.py."
    )
    parser.add_argument("question", help="Вопрос для сравнения.")
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
    parser.add_argument(
        "--assistant-url",
        default="http://127.0.0.1:8000",
        help="URL LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--assistant-model",
        default=DEFAULT_ASSISTANT_MODEL,
        help="Модель LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Модель Ollama для generate_text. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--llm-backend",
        choices=("assistant", "ollama"),
        default="assistant",
        help="Backend для ветки build_eval_report.py. По умолчанию: %(default)s",
    )
    parser.add_argument("--auth-token", default="", help="Bearer token для LLM Assistant.")
    parser.add_argument("--top-k", type=int, default=5, help="Сколько чанков брать в RAG.")
    parser.add_argument(
        "--skip-generation",
        action="store_true",
        help="Сравнить retrieval и prompt без запросов к LLM.",
    )
    parser.add_argument(
        "--show-prompts",
        action="store_true",
        help="Печатать оба итоговых prompt целиком.",
    )
    return parser.parse_args()


def chunks_to_brief(chunks: list[RetrievedChunk]) -> list[dict[str, Any]]:
    return [
        {
            "rank": chunk.rank,
            "score": round(chunk.score, 6),
            "chunk_id": chunk.chunk_id,
            "source": chunk.source,
            "section": chunk.section,
        }
        for chunk in chunks
    ]


def retrieve_for_eval(
    *,
    question: str,
    index_file: Path,
    metadata_file: Path,
    embed_model: str,
    ollama_url: str,
    top_k: int,
) -> tuple[list[RetrievedChunk], str]:
    retrieval_question = question
    try:
        chunks = retrieve_chunks(
            question=question,
            index_file=index_file,
            metadata_file=metadata_file,
            embed_model=embed_model,
            ollama_url=ollama_url,
            top_k=top_k,
        )
    except RuntimeError as exc:
        if "NaN" not in str(exc):
            raise
        retrieval_question = sanitize_retrieval_query(question)
        chunks = retrieve_chunks(
            question=retrieval_question,
            index_file=index_file,
            metadata_file=metadata_file,
            embed_model=embed_model,
            ollama_url=ollama_url,
            top_k=top_k,
        )
    return chunks, retrieval_question


def generate_rag_compare_answer(
    *,
    prompt: str,
    llm_backend: str,
    assistant_url: str,
    assistant_model: str,
    auth_token: str,
    ollama_url: str,
    ollama_model: str,
) -> str:
    return generate_text(
        llm_backend=llm_backend,
        prompt=prompt,
        temperature=0.2,
        assistant_url=assistant_url,
        assistant_model=assistant_model,
        auth_token=auth_token,
        max_tokens=900,
        user_id="compare-single-rag-rag-compare",
        ollama_url=ollama_url,
        ollama_model=ollama_model,
    )


def generate_eval_answer(
    *,
    prompt: str,
    llm_backend: str,
    assistant_url: str,
    assistant_model: str,
    auth_token: str,
    ollama_url: str,
    ollama_model: str,
) -> str:
    return generate_text(
        llm_backend=llm_backend,
        prompt=prompt,
        temperature=0.1,
        assistant_url=assistant_url,
        assistant_model=assistant_model,
        auth_token=auth_token,
        max_tokens=700,
        user_id="compare-single-rag-build-eval-report",
        ollama_url=ollama_url,
        ollama_model=ollama_model,
    )


def main() -> int:
    configure_stdio()
    args = parse_args()
    index_file, metadata_file = resolve_retrieval_files(
        strategy=args.strategy,
        index_file=args.index_file,
        metadata_file=args.metadata_file,
    )

    rag_chunks = retrieve_chunks(
        question=args.question,
        index_file=index_file,
        metadata_file=metadata_file,
        embed_model=args.embed_model,
        ollama_url=args.ollama_url,
        top_k=args.top_k,
    )
    eval_chunks, eval_retrieval_question = retrieve_for_eval(
        question=args.question,
        index_file=index_file,
        metadata_file=metadata_file,
        embed_model=args.embed_model,
        ollama_url=args.ollama_url,
        top_k=args.top_k,
    )

    rag_prompt = build_rag_user_prompt(args.question, args.strategy, rag_chunks)
    spec = QuestionSpec(
        identifier="single",
        question=args.question,
        expectation="",
        required_sources=[],
        keyword_groups=[],
    )
    eval_prompt = build_eval_rag_prompt(spec, args.strategy, eval_chunks)

    result: dict[str, Any] = {
        "question": args.question,
        "strategy": args.strategy,
        "index_file": str(index_file),
        "metadata_file": str(metadata_file),
        "embed_model": args.embed_model,
        "rag_compare": {
            "temperature": 0.2,
            "max_tokens": 900,
            "chunks": chunks_to_brief(rag_chunks),
            "prompt_equals_eval": rag_prompt == eval_prompt,
        },
        "build_eval_report": {
            "temperature": 0.1,
            "max_tokens": 700,
            "retrieval_question": eval_retrieval_question,
            "chunks": chunks_to_brief(eval_chunks),
        },
        "diff": {
            "same_retrieval_question": args.question == eval_retrieval_question,
            "same_chunks": chunks_to_brief(rag_chunks) == chunks_to_brief(eval_chunks),
            "same_prompt": rag_prompt == eval_prompt,
        },
    }

    if not args.skip_generation:
        auth_token = resolve_auth_token(
            llm_backend=args.llm_backend,
            assistant_url=args.assistant_url,
            auth_token=args.auth_token,
        )
        result["rag_compare"]["answer"] = generate_rag_compare_answer(
            prompt=rag_prompt,
            llm_backend=args.llm_backend,
            assistant_url=args.assistant_url,
            assistant_model=args.assistant_model,
            auth_token=auth_token,
            ollama_url=args.ollama_url,
            ollama_model=args.ollama_model,
        )
        result["build_eval_report"]["answer"] = generate_eval_answer(
            prompt=eval_prompt,
            llm_backend=args.llm_backend,
            assistant_url=args.assistant_url,
            assistant_model=args.assistant_model,
            auth_token=auth_token,
            ollama_url=args.ollama_url,
            ollama_model=args.ollama_model,
        )
        result["diff"]["same_answer"] = (
            result["rag_compare"]["answer"] == result["build_eval_report"]["answer"]
        )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    if args.show_prompts:
        print("\n=== rag_compare prompt ===\n")
        print(rag_prompt)
        print("\n=== build_eval_report prompt ===\n")
        print(eval_prompt)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
