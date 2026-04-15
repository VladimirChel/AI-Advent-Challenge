#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from llm_backends import (
    DEFAULT_ASSISTANT_MODEL,
    DEFAULT_OLLAMA_MODEL,
    generate_text,
    resolve_auth_token,
)
from rag_compare import configure_stdio


ROOT_DIR = Path(__file__).resolve().parent
DAY21_DIR = ROOT_DIR.parent / "Day21"
DEFAULT_METADATA_FILE = DAY21_DIR / "output" / "structure_chunks.json"
DEFAULT_DOCUMENTS_DIR = DAY21_DIR / "documents"
DEFAULT_OUTPUT_FILE = ROOT_DIR / "generated_control_questions.json"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Читает указанный список файлов из базы документов/чанков Day21 "
            "и автоматически формирует JSON с контрольными вопросами."
        )
    )
    parser.add_argument(
        "--file",
        default="",
        help="Путь к txt/json-файлу со списком имен файлов для анализа.",
    )
    parser.add_argument(
        "--source-file",
        dest="source_files",
        action="append",
        default=[],
        help="Имя файла из Day21/documents. Параметр можно передавать несколько раз.",
    )
    parser.add_argument(
        "--metadata-file",
        default=str(DEFAULT_METADATA_FILE),
        help="Путь к JSON с чанками. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--documents-dir",
        default=str(DEFAULT_DOCUMENTS_DIR),
        help="Каталог с исходными документами. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--llm-backend",
        choices=("assistant", "ollama"),
        default="assistant",
        help="Какой бэкенд использовать для генерации вопросов. По умолчанию: %(default)s",
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
        "--ollama-url",
        default="http://127.0.0.1:11434",
        help="URL локальной Ollama. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--ollama-model",
        default=DEFAULT_OLLAMA_MODEL,
        help="Модель Ollama для генерации вопросов. По умолчанию: %(default)s",
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
        default=5000,
        help="Максимум токенов ответа модели. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--question-count",
        type=int,
        default=10,
        help="Сколько вопросов сгенерировать. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--per-file-question-mode",
        choices=("off", "one_or_two"),
        default="one_or_two",
        help=(
            "Режим распределения вопросов по файлам. "
            "`one_or_two` просит модель сделать 1-2 вопроса на файл, где хватает данных. "
            "По умолчанию: %(default)s"
        ),
    )
    parser.add_argument(
        "--max-chunks-per-file",
        type=int,
        default=4,
        help="Сколько чанков максимум брать на один файл. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--max-total-chunks",
        type=int,
        default=30,
        help="Жесткий лимит на общее число анализируемых чанков по всем файлам. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--max-raw-chars",
        type=int,
        default=4000,
        help="Сколько символов сырого текста максимум брать из txt/md файла. По умолчанию: %(default)s",
    )
    parser.add_argument(
        "--output-file",
        default=str(DEFAULT_OUTPUT_FILE),
        help="Куда сохранить итоговый JSON. По умолчанию: %(default)s",
    )
    return parser.parse_args()


def read_files_list(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8").strip()
    if not raw:
        return []
    if path.suffix.lower() == ".json":
        payload = json.loads(raw)
        if not isinstance(payload, list):
            raise ValueError(f"Ожидался JSON-массив в {path}")
        return [str(item).strip() for item in payload if str(item).strip()]
    return [line.strip() for line in raw.splitlines() if line.strip()]


def unique_preserve_order(items: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        key = item.casefold()
        if key in seen:
            continue
        seen.add(key)
        result.append(item)
    return result


def load_requested_files(args: argparse.Namespace) -> list[str]:
    requested = list(args.source_files)
    if args.file:
        requested.extend(read_files_list(Path(args.file)))
    requested = unique_preserve_order([item for item in requested if item.strip()])
    if not requested:
        raise ValueError("Нужно передать --file со списком документов или хотя бы один --source-file.")
    return requested


def load_metadata(path: Path) -> list[dict[str, Any]]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    items = payload.get("items", [])
    if not isinstance(items, list):
        raise ValueError(f"В metadata-файле {path} поле items имеет неверный формат.")
    return items


def get_chunk_fields(item: dict[str, Any]) -> dict[str, Any]:
    return item["chunk"] if "chunk" in item else item


def select_chunks_for_file(
    metadata_items: list[dict[str, Any]],
    filename: str,
    max_chunks: int,
) -> list[dict[str, str]]:
    matched: list[dict[str, str]] = []
    filename_fold = filename.casefold()
    for item in metadata_items:
        chunk = get_chunk_fields(item)
        source_name = Path(str(chunk.get("source", ""))).name
        if source_name.casefold() != filename_fold:
            continue
        matched.append(
            {
                "title": str(chunk.get("title", "")),
                "section": str(chunk.get("section", "")),
                "text": str(chunk.get("text", "")).strip(),
            }
        )

    if len(matched) <= max_chunks:
        return matched

    # For large files, spread the sample across the whole document instead of
    # taking only the first chunks. This gives the model visibility into the
    # beginning, middle, and end of the file.
    picked_indices: list[int] = []
    last_section = ""
    for slot in range(max_chunks):
        raw_index = round(slot * (len(matched) - 1) / max(max_chunks - 1, 1))
        candidate_index = raw_index

        # Prefer a nearby chunk from a different section to avoid selecting a
        # cluster of almost identical neighboring chunks when the file is long.
        search_radius = 2
        while (
            candidate_index < len(matched)
            and matched[candidate_index]["section"] == last_section
            and search_radius >= 0
        ):
            left = raw_index - search_radius
            right = raw_index + search_radius
            if left >= 0 and left not in picked_indices and matched[left]["section"] != last_section:
                candidate_index = left
                break
            if right < len(matched) and right not in picked_indices and matched[right]["section"] != last_section:
                candidate_index = right
                break
            search_radius -= 1

        while candidate_index in picked_indices and candidate_index + 1 < len(matched):
            candidate_index += 1
        while candidate_index in picked_indices and candidate_index - 1 >= 0:
            candidate_index -= 1

        if candidate_index in picked_indices:
            continue
        picked_indices.append(candidate_index)
        last_section = matched[candidate_index]["section"]

    picked_indices.sort()
    return [matched[index] for index in picked_indices]


def try_read_raw_text(documents_dir: Path, filename: str, max_chars: int) -> str:
    path = documents_dir / filename
    if not path.exists():
        return ""
    if path.suffix.lower() not in {".txt", ".md"}:
        return ""

    for encoding in ("utf-8", "cp1251"):
        try:
            content = path.read_text(encoding=encoding)
            return content[:max_chars].strip()
        except UnicodeDecodeError:
            continue
    return ""


def build_source_payload(
    *,
    requested_files: list[str],
    metadata_items: list[dict[str, Any]],
    documents_dir: Path,
    max_chunks_per_file: int,
    max_total_chunks: int,
    max_raw_chars: int,
) -> dict[str, Any]:
    files_payload: list[dict[str, Any]] = []
    missing_files: list[str] = []
    total_chunks_used = 0

    for filename in requested_files:
        print(f"[source] Обрабатываю файл: {filename}", file=sys.stderr)
        remaining_chunks = max(0, max_total_chunks - total_chunks_used)
        if remaining_chunks == 0:
            print("[source] Достигнут общий лимит чанков, дальнейшие файлы пропускаются.", file=sys.stderr)
            break
        chunks = select_chunks_for_file(
            metadata_items=metadata_items,
            filename=filename,
            max_chunks=min(max_chunks_per_file, remaining_chunks),
        )
        raw_text = try_read_raw_text(documents_dir, filename, max_raw_chars)
        if not chunks and not raw_text:
            print("[source] Файл не найден в чанках и не прочитан как raw text, пропускаю.", file=sys.stderr)
            missing_files.append(filename)
            continue
        print(
            f"[source] Взято чанков: {len(chunks)}; raw_text_excerpt: {'yes' if raw_text else 'no'}; "
            f"осталось общего лимита: {remaining_chunks - len(chunks)}",
            file=sys.stderr,
        )
        files_payload.append(
            {
                "file": filename,
                "raw_text_excerpt": raw_text,
                "chunks": chunks,
            }
        )
        total_chunks_used += len(chunks)

    if not files_payload:
        raise ValueError("Не удалось найти ни одного указанного файла ни в документах, ни в чанках.")

    return {
        "documents_dir": str(documents_dir),
        "requested_files": requested_files,
        "missing_files": missing_files,
        "total_chunks_used": total_chunks_used,
        "max_total_chunks": max_total_chunks,
        "files": files_payload,
    }


def build_prompt(source_payload: dict[str, Any], question_count: int, per_file_question_mode: str) -> str:
    source_json = json.dumps(source_payload, ensure_ascii=False, indent=2)
    distribution_rule = ""
    if per_file_question_mode == "one_or_two":
        distribution_rule = (
            f"2. Постарайся сделать по 1-2 вопроса на файл, если по файлу действительно хватает фактуры.\n"
            f"3. Не делай больше 2 вопросов на один файл.\n"
            f"4. Итоговое число вопросов должно быть не больше {question_count}.\n"
            "5. Распределяй вопросы по файлам равномерно.\n"
        )
    else:
        distribution_rule = (
            "2. Распределяй вопросы по разным файлам настолько равномерно, насколько это возможно.\n"
            f"3. Итоговое число вопросов должно быть не больше {question_count}.\n"
        )
    return f"""
Ты генерируешь контрольные вопросы по локальной базе документов.

Ниже дан список выбранных файлов и извлеченные по ним данные:
- raw_text_excerpt: фрагмент исходного txt/md файла, если он доступен;
- chunks: релевантные чанки из индексированной базы.

Собери мини-набор из {question_count} контрольных вопросов только по этим файлам.

Требования:
1. Вопросы должны быть проверяемыми и опираться на факты из переданных документов/чанков.
{distribution_rule}4. Избегай слишком общих вопросов; предпочитай конкретные команды, параметры, пути, шаги, ограничения, интерфейсы, роли, условия.
5. Для каждого вопроса обязательно верни:
   - identifier
   - question
   - expectation
   - required_sources
   - keyword_groups
6. required_sources должен содержать только имена файлов из входного списка.
7. keyword_groups — это список списков с ключевыми маркерами ответа. Каждый внутренний список содержит синонимы/варианты для одной смысловой проверки.
8. expectation должно кратко фиксировать, что обязательно должно быть в правильном ответе.
9. Если данных по какому-то файлу мало, можно не включать его в финальный набор.

Верни только JSON без пояснений и без markdown.
Формат:
{{
  "generated_from": "selected Day21 files",
  "question_count": <int>,
  "questions": [
    {{
      "identifier": "Q1",
      "question": "...",
      "expectation": "...",
      "required_sources": ["file.ext"],
      "keyword_groups": [["..."], ["...", "..."]]
    }}
  ]
}}

Входные данные:
{source_json}
""".strip()


def extract_json_block(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", stripped)
        stripped = re.sub(r"\s*```$", "", stripped)
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError("Модель не вернула JSON-объект.")
    return stripped[start : end + 1]


def validate_generated_questions(
    payload: dict[str, Any],
    allowed_sources: set[str],
    requested_count: int,
    per_file_question_mode: str,
) -> dict[str, Any]:
    questions = payload.get("questions")
    if not isinstance(questions, list) or not questions:
        raise ValueError("В ответе модели нет непустого массива questions.")

    normalized_questions: list[dict[str, Any]] = []
    per_file_counts: dict[str, int] = {}
    for index, item in enumerate(questions, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Вопрос #{index} имеет неверный формат.")

        required_sources = [str(src) for src in item.get("required_sources", [])]
        invalid_sources = [src for src in required_sources if src not in allowed_sources]
        if invalid_sources:
            raise ValueError(f"Вопрос #{index} содержит неизвестные источники: {invalid_sources}")

        keyword_groups = item.get("keyword_groups", [])
        if not isinstance(keyword_groups, list) or not keyword_groups:
            raise ValueError(f"Вопрос #{index} не содержит keyword_groups.")

        normalized_groups: list[list[str]] = []
        for group in keyword_groups:
            if not isinstance(group, list) or not group:
                raise ValueError(f"Вопрос #{index} содержит пустую группу keyword_groups.")
            normalized_groups.append([str(option) for option in group if str(option).strip()])

        normalized_questions.append(
            {
                "identifier": str(item.get("identifier") or f"Q{index}"),
                "question": str(item.get("question", "")).strip(),
                "expectation": str(item.get("expectation", "")).strip(),
                "required_sources": required_sources,
                "keyword_groups": normalized_groups,
            }
        )
        for src in required_sources:
            per_file_counts[src] = per_file_counts.get(src, 0) + 1

    if per_file_question_mode == "one_or_two":
        offenders = {src: count for src, count in per_file_counts.items() if count > 2}
        if offenders:
            raise ValueError(f"Превышен лимит 2 вопроса на файл: {offenders}")

    payload["generated_from"] = str(payload.get("generated_from") or "selected Day21 files")
    payload["question_count"] = min(requested_count, len(normalized_questions))
    payload["questions"] = normalized_questions[:requested_count]
    return payload


def main() -> int:
    configure_stdio()
    args = parse_args()

    requested_files = load_requested_files(args)
    metadata_file = Path(args.metadata_file)
    documents_dir = Path(args.documents_dir)
    output_file = Path(args.output_file)

    metadata_items = load_metadata(metadata_file)
    source_payload = build_source_payload(
        requested_files=requested_files,
        metadata_items=metadata_items,
        documents_dir=documents_dir,
        max_chunks_per_file=args.max_chunks_per_file,
        max_total_chunks=args.max_total_chunks,
        max_raw_chars=args.max_raw_chars,
    )

    prompt = build_prompt(
        source_payload,
        args.question_count,
        args.per_file_question_mode,
    )
    print(f"[llm] Отправляю собранный контекст в {args.llm_backend}.", file=sys.stderr)
    auth_token = resolve_auth_token(
        llm_backend=args.llm_backend,
        assistant_url=args.assistant_url,
        auth_token=args.auth_token,
    )
    response_text = generate_text(
        llm_backend=args.llm_backend,
        prompt=prompt,
        temperature=args.temperature,
        assistant_url=args.assistant_url,
        assistant_model=args.assistant_model,
        auth_token=auth_token,
        max_tokens=args.max_tokens,
        user_id="day22-question-generator",
        ollama_url=args.ollama_url,
        ollama_model=args.ollama_model,
    )
    print("[llm] Ответ от модели получен, валидирую JSON.", file=sys.stderr)

    payload = json.loads(extract_json_block(response_text))
    payload = validate_generated_questions(
        payload=payload,
        allowed_sources={Path(name).name for name in requested_files},
        requested_count=args.question_count,
        per_file_question_mode=args.per_file_question_mode,
    )

    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    result = {
        "questions_file": str(output_file),
        "question_count": payload["question_count"],
        "requested_files": requested_files,
        "missing_files": source_payload["missing_files"],
        "total_chunks_used": source_payload["total_chunks_used"],
        "max_total_chunks": source_payload["max_total_chunks"],
        "per_file_question_mode": args.per_file_question_mode,
        "llm_backend": args.llm_backend,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise
