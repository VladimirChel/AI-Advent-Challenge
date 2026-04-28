# Day31 Project Help Toolkit

This folder contains the standalone project index builder used by `LLM Assistant` project-help mode.

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
