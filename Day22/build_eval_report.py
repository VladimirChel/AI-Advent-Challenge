#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import statistics
import sys
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

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


ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_REPORT_PATH = ROOT_DIR / "rag_quality_report.html"
DEFAULT_QUESTIONS_PATH = ROOT_DIR / "control_questions.json"


@dataclass(frozen=True, slots=True)
class QuestionSpec:
    identifier: str
    question: str
    expectation: str
    required_sources: list[str]
    keyword_groups: list[list[str]]


@dataclass(slots=True)
class ModeResult:
    mode: str
    answer: str
    answer_score: float
    matched_groups: int
    total_groups: int
    chunks: list[RetrievedChunk]
    retrieved_expected_sources: list[str]


@dataclass(slots=True)
class QuestionRun:
    spec: QuestionSpec
    without_rag: ModeResult
    with_rag: ModeResult


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Прогоняет 10 контрольных вопросов в режимах with RAG / without RAG и формирует HTML-отчет."
    )
    parser.add_argument(
        "--llm-backend",
        choices=("assistant", "ollama"),
        default="assistant",
        help="Какой бэкенд использовать для генерации ответов. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--strategy",
        choices=("fixed", "structure"),
        default="structure",
        help="Стратегия retrieval для индекса Day21. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--index-file",
        default="",
        help="Путь к FAISS-индексу. Если не задан, выбирается по --strategy.",
    )
    parser.add_argument(
        "--metadata-file",
        default="",
        help="Путь к JSON с чанками. Если не задан, выбирается по --strategy.",
    )
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
        help="Модель для LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Модель Ollama для генерации ответов. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--auth-token",
        default="",
        help="Bearer token для LLM Assistant. Если не задан, будет зарегистрирован временный пользователь.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.1,
        help="Температура генерации. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=700,
        help="Максимум токенов ответа. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=5,
        help="Сколько чанков брать в RAG-контекст. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--user-id",
        default="day22-eval-report",
        help="User id для запросов к LLM Assistant. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--report-file",
        default=str(DEFAULT_REPORT_PATH),
        help="Куда сохранить HTML-отчет. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--questions-file",
        default=str(DEFAULT_QUESTIONS_PATH),
        help="JSON-файл с контрольными вопросами. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Проверить JSON, источники и retrieval-файлы без запросов к LLM и без генерации HTML.",
    )
    return parser.parse_args()


def load_questions(path: Path) -> list[QuestionSpec]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    raw_questions: Iterable[dict[str, object]]
    if isinstance(payload, dict):
        raw_questions = payload.get("questions", [])
    else:
        raw_questions = payload

    questions: list[QuestionSpec] = []
    for raw in raw_questions:
        if not isinstance(raw, dict):
            raise ValueError(f"Некорректный вопрос в {path}: {raw!r}")
        questions.append(
            QuestionSpec(
                identifier=str(raw["identifier"]),
                question=str(raw["question"]),
                expectation=str(raw["expectation"]),
                required_sources=[str(item) for item in raw.get("required_sources", [])],
                keyword_groups=[
                    [str(option) for option in group]
                    for group in raw.get("keyword_groups", [])
                ],
            )
        )
    if not questions:
        raise ValueError(f"В файле {path} не найдено ни одного вопроса.")
    return questions


def normalize_text(text: str) -> str:
    return " ".join(text.lower().replace("ё", "е").split())


def build_plain_prompt(question: QuestionSpec) -> str:
    return (
        "Ответь кратко и по делу на вопрос ниже. "
        "Если не уверен, лучше прямо скажи, что не хватает подтвержденной информации.\n\n"
        f"Вопрос: {question.question}"
    )


def build_eval_rag_prompt(question: QuestionSpec, strategy: str, chunks: list[RetrievedChunk]) -> str:
    return build_rag_user_prompt(question.question, strategy, chunks)


def sanitize_retrieval_query(text: str) -> str:
    cleaned = re.sub(r"^\s*[QqА-Яа-яA-Za-z]?\d+\s*:\s*", "", text)
    cleaned = re.sub(r"[`\"'“”«»(){}\[\]:;!?]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned or text


def group_is_matched(answer_text: str, group: list[str]) -> bool:
    normalized = normalize_text(answer_text)
    return any(normalize_text(option) in normalized for option in group)


def score_answer(answer_text: str, spec: QuestionSpec) -> tuple[float, int, int]:
    total = len(spec.keyword_groups)
    matched = sum(1 for group in spec.keyword_groups if group_is_matched(answer_text, group))
    score = matched / total if total else 0.0
    return score, matched, total


def collect_expected_sources(chunks: list[RetrievedChunk], required_sources: list[str]) -> list[str]:
    chunk_sources = {Path(chunk.source).name for chunk in chunks}
    return [source for source in required_sources if source in chunk_sources]


def validate_questions_against_metadata(questions: list[QuestionSpec], metadata_file: Path) -> dict[str, Any]:
    payload = json.loads(metadata_file.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    known_sources: set[str] = set()
    for item in items:
        chunk = item["chunk"] if "chunk" in item else item
        known_sources.add(Path(str(chunk.get("source", ""))).name)

    unknown_sources: list[dict[str, str]] = []
    for question in questions:
        for source in question.required_sources:
            if source not in known_sources:
                unknown_sources.append(
                    {
                        "identifier": question.identifier,
                        "source": source,
                    }
                )

    return {
        "question_count": len(questions),
        "known_source_count": len(known_sources),
        "unknown_sources": unknown_sources,
    }


def generate_mode_result(
    *,
    mode: str,
    spec: QuestionSpec,
    args: argparse.Namespace,
    auth_token: str,
    index_file: Path,
    metadata_file: Path,
) -> ModeResult:
    chunks: list[RetrievedChunk] = []
    if mode == "with_rag":
        try:
            chunks = retrieve_chunks(
                question=spec.question,
                index_file=index_file,
                metadata_file=metadata_file,
                embed_model=args.embed_model,
                ollama_url=args.ollama_url,
                top_k=args.top_k,
            )
        except RuntimeError as exc:
            if "NaN" not in str(exc):
                raise
            chunks = retrieve_chunks(
                question=sanitize_retrieval_query(spec.question),
                index_file=index_file,
                metadata_file=metadata_file,
                embed_model=args.embed_model,
                ollama_url=args.ollama_url,
                top_k=args.top_k,
            )
        prompt = build_eval_rag_prompt(spec, args.strategy, chunks)
    else:
        prompt = build_plain_prompt(spec)

    answer = generate_text(
        llm_backend=args.llm_backend,
        prompt=prompt,
        temperature=args.temperature,
        assistant_url=args.assistant_url,
        assistant_model=args.assistant_model,
        auth_token=auth_token,
        max_tokens=args.max_tokens,
        user_id=f"{args.user_id}-{mode.lower()}",
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
    )
    answer_score, matched_groups, total_groups = score_answer(answer, spec)
    return ModeResult(
        mode=mode,
        answer=answer,
        answer_score=answer_score,
        matched_groups=matched_groups,
        total_groups=total_groups,
        chunks=chunks,
        retrieved_expected_sources=collect_expected_sources(chunks, spec.required_sources),
    )


def badge_class(delta: float) -> str:
    if delta > 0.15:
        return "good"
    if delta < -0.15:
        return "bad"
    return "neutral"


def render_chunks(chunks: list[RetrievedChunk]) -> str:
    if not chunks:
        return "<p class='muted'>Чанки не использовались.</p>"

    parts: list[str] = ["<div class='chunk-list'>"]
    for chunk in chunks:
        snippet = " ".join(chunk.text.split())
        if len(snippet) > 320:
            snippet = snippet[:320].rstrip() + "..."
        parts.append(
            "<article class='chunk'>"
            f"<div class='chunk-meta'>#{chunk.rank} | score={chunk.score:.4f}</div>"
            f"<div><strong>{html.escape(Path(chunk.source).name)}</strong> | {html.escape(chunk.section)}</div>"
            f"<div class='chunk-text'>{html.escape(snippet)}</div>"
            "</article>"
        )
    parts.append("</div>")
    return "".join(parts)


def render_report(runs: list[QuestionRun], args: argparse.Namespace, report_path: Path) -> str:
    without_scores = [run.without_rag.answer_score for run in runs]
    with_scores = [run.with_rag.answer_score for run in runs]
    deltas = [w.answer_score - wo.answer_score for w, wo in ((run.with_rag, run.without_rag) for run in runs)]
    retrieved_source_hits = [
        len(run.with_rag.retrieved_expected_sources) / len(run.spec.required_sources)
        if run.spec.required_sources
        else 1.0
        for run in runs
    ]

    summary_rows = []
    for run in runs:
        delta = run.with_rag.answer_score - run.without_rag.answer_score
        summary_rows.append(
            "<tr>"
            f"<td>{html.escape(run.spec.identifier)}</td>"
            f"<td>{html.escape(run.spec.question)}</td>"
            f"<td>{run.without_rag.answer_score:.0%}</td>"
            f"<td>{run.with_rag.answer_score:.0%}</td>"
            f"<td><span class='badge {badge_class(delta)}'>{delta:+.0%}</span></td>"
            f"<td>{len(run.with_rag.retrieved_expected_sources)}/{len(run.spec.required_sources) or 1}</td>"
            "</tr>"
        )

    sections: list[str] = []
    for run in runs:
        delta = run.with_rag.answer_score - run.without_rag.answer_score
        sections.append(
            "<section class='question-card'>"
            f"<h2>{html.escape(run.spec.identifier)}. {html.escape(run.spec.question)}</h2>"
            "<div class='meta-grid'>"
            f"<div><span class='label'>Ожидание</span><p>{html.escape(run.spec.expectation)}</p></div>"
            f"<div><span class='label'>Ожидаемые источники</span><p>{html.escape(', '.join(run.spec.required_sources) if run.spec.required_sources else 'Не фиксируются')}</p></div>"
            f"<div><span class='label'>Качество без RAG</span><p>{run.without_rag.answer_score:.0%} ({run.without_rag.matched_groups}/{run.without_rag.total_groups})</p></div>"
            f"<div><span class='label'>Качество с RAG</span><p>{run.with_rag.answer_score:.0%} ({run.with_rag.matched_groups}/{run.with_rag.total_groups})</p></div>"
            f"<div><span class='label'>Разница</span><p><span class='badge {badge_class(delta)}'>{delta:+.0%}</span></p></div>"
            f"<div><span class='label'>Найдены нужные источники</span><p>{html.escape(', '.join(run.with_rag.retrieved_expected_sources) if run.with_rag.retrieved_expected_sources else 'Нет')}</p></div>"
            "</div>"
            "<div class='answer-grid'>"
            "<article>"
            "<h3>Без RAG</h3>"
            f"<pre>{html.escape(run.without_rag.answer)}</pre>"
            "</article>"
            "<article>"
            "<h3>С RAG</h3>"
            f"<pre>{html.escape(run.with_rag.answer)}</pre>"
            "</article>"
            "</div>"
            "<h3>Retrieval-чunks для режима с RAG</h3>"
            f"{render_chunks(run.with_rag.chunks)}"
            "</section>"
        )

    return f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>RAG Quality Report</title>
  <style>
    :root {{
      --bg: #f5f1e8;
      --card: #fffdf8;
      --ink: #20201c;
      --muted: #6c685f;
      --line: #d9d0c1;
      --accent: #114b5f;
      --good: #2f6f4f;
      --bad: #9f3a2f;
      --neutral: #8a6d3b;
      --soft: #efe6d8;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top right, rgba(17,75,95,0.10), transparent 28%),
        linear-gradient(180deg, #f7f2e7 0%, #f2ebdc 100%);
    }}
    .wrap {{ max-width: 1280px; margin: 0 auto; padding: 32px 20px 56px; }}
    .hero, .question-card {{
      background: rgba(255,253,248,0.92);
      border: 1px solid var(--line);
      border-radius: 18px;
      box-shadow: 0 20px 60px rgba(44, 36, 17, 0.08);
    }}
    .hero {{ padding: 28px; margin-bottom: 24px; }}
    h1, h2, h3 {{ margin: 0 0 12px; line-height: 1.15; }}
    h1 {{ font-size: 2rem; }}
    h2 {{ font-size: 1.4rem; }}
    h3 {{ font-size: 1.05rem; }}
    p {{ margin: 0; line-height: 1.5; }}
    .summary {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
      gap: 12px;
      margin-top: 18px;
    }}
    .summary article {{
      background: var(--soft);
      border-radius: 14px;
      padding: 14px 16px;
      border: 1px solid rgba(17,75,95,0.10);
    }}
    .summary .value {{
      display: block;
      font-size: 1.6rem;
      font-weight: 700;
      margin-top: 6px;
    }}
    .label {{
      display: block;
      color: var(--muted);
      font-size: 0.9rem;
      margin-bottom: 4px;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    table {{
      width: 100%;
      border-collapse: collapse;
      margin-top: 22px;
      background: var(--card);
      border-radius: 16px;
      overflow: hidden;
    }}
    th, td {{
      padding: 12px 10px;
      border-bottom: 1px solid var(--line);
      text-align: left;
      vertical-align: top;
      font-size: 0.95rem;
    }}
    th {{
      background: #f0e7d7;
      font-size: 0.85rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
    }}
    .badge {{
      display: inline-block;
      padding: 4px 10px;
      border-radius: 999px;
      color: white;
      font-weight: 700;
      font-size: 0.85rem;
    }}
    .badge.good {{ background: var(--good); }}
    .badge.bad {{ background: var(--bad); }}
    .badge.neutral {{ background: var(--neutral); }}
    .question-card {{ padding: 22px; margin-top: 22px; }}
    .meta-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 12px;
      margin-bottom: 18px;
    }}
    .meta-grid > div {{
      background: var(--soft);
      border: 1px solid rgba(17,75,95,0.10);
      border-radius: 14px;
      padding: 12px 14px;
    }}
    .answer-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
      gap: 14px;
      margin-bottom: 18px;
    }}
    .answer-grid article {{
      background: #fcfaf5;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 14px;
    }}
    pre {{
      margin: 0;
      white-space: pre-wrap;
      word-break: break-word;
      font-family: Consolas, "Courier New", monospace;
      font-size: 0.92rem;
      line-height: 1.5;
    }}
    .chunk-list {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(260px, 1fr));
      gap: 12px;
    }}
    .chunk {{
      background: #fcfaf5;
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 12px;
    }}
    .chunk-meta {{
      color: var(--muted);
      font-size: 0.84rem;
      margin-bottom: 6px;
    }}
    .chunk-text {{
      margin-top: 8px;
      line-height: 1.45;
      color: #312b24;
      font-size: 0.94rem;
    }}
    .muted {{ color: var(--muted); }}
    @media (max-width: 700px) {{
      .wrap {{ padding: 20px 14px 36px; }}
      h1 {{ font-size: 1.6rem; }}
    }}
  </style>
</head>
<body>
  <main class="wrap">
    <section class="hero">
      <h1>Сравнение агента в двух режимах: с RAG и без RAG</h1>
      <p>Отчет собран автоматически по 10 контрольным вопросам из базы документов Day21. Для каждого вопроса зафиксированы ожидания, обязательные источники, ответы обеих стратегий и найденные чанки retrieval.</p>
      <div class="summary">
        <article><span class="label">Среднее качество без RAG</span><span class="value">{statistics.mean(without_scores):.0%}</span></article>
        <article><span class="label">Среднее качество с RAG</span><span class="value">{statistics.mean(with_scores):.0%}</span></article>
        <article><span class="label">Средний прирост</span><span class="value">{statistics.mean(deltas):+.0%}</span></article>
        <article><span class="label">Попадание в ожидаемые источники</span><span class="value">{statistics.mean(retrieved_source_hits):.0%}</span></article>
      </div>
      <table>
        <thead>
          <tr>
            <th>ID</th>
            <th>Вопрос</th>
            <th>Без RAG</th>
            <th>С RAG</th>
            <th>Дельта</th>
            <th>Источники</th>
          </tr>
        </thead>
        <tbody>
          {''.join(summary_rows)}
        </tbody>
      </table>
      <p class="muted" style="margin-top: 16px;">Индекс: {html.escape(str(resolve_retrieval_files(args.strategy, args.index_file, args.metadata_file)[0]))}<br>Отчет: {html.escape(str(report_path))}</p>
    </section>
    {''.join(sections)}
  </main>
</body>
</html>
"""


def main() -> int:
    configure_stdio()
    args = parse_args()
    questions_path = Path(args.questions_file)
    index_file, metadata_file = resolve_retrieval_files(
        strategy=args.strategy,
        index_file=args.index_file,
        metadata_file=args.metadata_file,
    )
    report_path = Path(args.report_file)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    questions = load_questions(questions_path)

    if not index_file.exists():
        raise FileNotFoundError(f"FAISS-индекс не найден: {index_file}")
    if not metadata_file.exists():
        raise FileNotFoundError(f"Metadata-файл не найден: {metadata_file}")

    if args.dry_run:
        validation = validate_questions_against_metadata(questions, metadata_file)
        result = {
            "dry_run": True,
            "questions_file": str(questions_path),
            "index_file": str(index_file),
            "metadata_file": str(metadata_file),
            "question_count": validation["question_count"],
            "unknown_sources": validation["unknown_sources"],
            "status": "ok" if not validation["unknown_sources"] else "has_unknown_sources",
        }
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    auth_token = resolve_auth_token(
        llm_backend=args.llm_backend,
        assistant_url=args.assistant_url,
        auth_token=args.auth_token,
    )
    runs: list[QuestionRun] = []

    total_questions = len(questions)
    for idx, spec in enumerate(questions, start=1):
        print(f"[{idx}/{total_questions}] {spec.identifier}: {spec.question}", file=sys.stderr)
        without_rag = generate_mode_result(
            mode="without_rag",
            spec=spec,
            args=args,
            auth_token=auth_token,
            index_file=index_file,
            metadata_file=metadata_file,
        )
        with_rag = generate_mode_result(
            mode="with_rag",
            spec=spec,
            args=args,
            auth_token=auth_token,
            index_file=index_file,
            metadata_file=metadata_file,
        )
        runs.append(QuestionRun(spec=spec, without_rag=without_rag, with_rag=with_rag))
        time.sleep(0.2)

    report_html = render_report(runs, args, report_path)
    report_path.write_text(report_html, encoding="utf-8")

    payload = {
        "report_file": str(report_path),
        "questions_file": str(questions_path),
        "questions": len(runs),
        "avg_without_rag": statistics.mean(run.without_rag.answer_score for run in runs),
        "avg_with_rag": statistics.mean(run.with_rag.answer_score for run in runs),
        "avg_delta": statistics.mean(run.with_rag.answer_score - run.without_rag.answer_score for run in runs),
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
