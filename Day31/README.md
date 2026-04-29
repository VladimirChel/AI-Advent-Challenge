# Day31 Project Help Toolkit

This folder contains the standalone project index builder used by `LLM Assistant` project-help mode.

It now also contains an MVP pipeline for local AI pull request review on a `self-hosted` GitHub Actions runner.

## GUI client

Use [Day31/project_help_client.py](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/Day31/project_help_client.py) for manual testing of the project-help flow.

```bash
python project_help_client.py
```

The client sends `project` in the request payload, so it is suitable for testing:

- `/help`
- `/help <question>`
- `/mode`
- `/exit`
- external `project_root`
- external `index_dir`

## Environment config

`build_project_index.py` reads settings from [Day31/.env](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/Day31/.env).

Main variable:

- `INDEX_OUTPUT_DIR` - where built indexes are stored

## Build an index for any project

```bash
python build_project_index.py --project-root "D:\path\to\project" --project-id my-project --output-dir ".\indexes"
```

If `--output-dir` is omitted, the script uses `INDEX_OUTPUT_DIR` from `.env`.

Useful flags:

- `--strategy structure` for section-aware chunking
- `--chunks-only` to generate chunks and manifest without embeddings
- `--model nomic-embed-text` to choose an Ollama embedding model

## Output

The script stores index artifacts outside the target project:

- `indexes/<project-id>/manifest.json`
- `indexes/<project-id>/structure_chunks.json`
- `indexes/<project-id>/structure.faiss` when embeddings are enabled

`manifest.json` is the main handoff file for `LLM Assistant`.

## AI PR review MVP

The MVP entrypoint is [run_pr_review.py](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/Day31/run_pr_review.py).

It is designed for a `self-hosted` GitHub Actions runner and works fully from local git state:

- reads PR `diff` with `git diff`
- loads local project context from docs and nearby code
- optionally uses a prebuilt Day31 index
- calls `LLM Assistant /generate`
- writes a markdown review with potential bugs, architecture concerns, and recommendations

Example local run:

```bash
python run_pr_review.py ^
  --repo-root "D:\path\to\repo" ^
  --project-root "D:\path\to\repo" ^
  --project-id my-project ^
  --index-dir ".\indexes" ^
  --base-ref origin/main ^
  --head-ref HEAD ^
  --dry-run
```

Default local LLM Assistant settings are now embedded in [run_pr_review.py](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/Day31/run_pr_review.py):

- `LLM_ASSISTANT_URL=http://127.0.0.1:8000`
- `LLM_ASSISTANT_PROVIDER_ID=cloud`
- `LLM_ASSISTANT_MODEL=openai/gpt-4.1-mini-2025-04-14`

You only need to set environment variables manually if you want to override these defaults.

Environment variables for real review generation:

- `LLM_ASSISTANT_URL` - local URL of `LLM Assistant`, for example `http://127.0.0.1:8000`
- `LLM_ASSISTANT_PROVIDER_ID` - optional provider id known to `LLM Assistant`
- `LLM_ASSISTANT_MODEL` - model name to send to `LLM Assistant`
- `PR_REVIEW_TEMPERATURE` - default `0.1`

The manual workflow currently hardcodes the `LLM Assistant` connection in YAML:

- `LLM_ASSISTANT_URL: http://127.0.0.1:8000`
- `LLM_ASSISTANT_PROVIDER_ID: cloud`
- `LLM_ASSISTANT_MODEL: openai/gpt-4.1-mini-2025-04-14`

If you want review generation through a local provider configured inside `LLM Assistant`, edit those values directly in:

- [ai-pr-review-manual.yml](/D:/Yandex.Disk/Docs/AI/AI%20Advent%20Challenge/Repo/AI%20Advent%20Challenge/.github/workflows/ai-pr-review-manual.yml)
