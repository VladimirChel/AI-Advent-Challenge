# project_repo_tools

Universal MCP stdio server for local project inspection.

Available tools:

- `git_branch(project_root)`
- `list_dir(project_root, path=".")`
- `read_file(project_root, path, max_chars=12000)`
- `tree_dir(project_root, path=".", max_depth=4, max_entries=500)`
- `find_files(project_root, glob="**/*", max_results=200, name_regex=None, path_regex=None, case_sensitive=False)`
- `count_files(project_root, glob="**/*", name_regex=None, path_regex=None, case_sensitive=False)`
- `search_text(project_root, pattern, glob="**/*", case_sensitive=False, max_results=200, context_chars=120)`
- `check_invariants(project_root, rules_path, glob="**/*", max_files=500)`
- `create_document(project_root, path, file_type, title="", content="")`

`check_invariants` expects a JSON file like:

```json
{
  "rules": [
    {
      "id": "python-files-need-future-import",
      "file_glob": "**/*.py",
      "required_patterns": ["from __future__ import annotations"],
      "forbidden_patterns": []
    }
  ]
}
```

`create_document` allows only:

- `file_type="readme_md"` with target filename `README.md`
- `file_type="report_html"` with target filename `report.html`

Example:

```bash
python server.py
```
