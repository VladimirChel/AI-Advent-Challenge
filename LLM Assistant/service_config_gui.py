from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Literal

import customtkinter as ctk
from tkinter import filedialog, messagebox


EnvType = Literal["str", "int", "float", "bool", "json", "json_list"]


@dataclass(frozen=True)
class ConfigField:
    key: str
    label: str
    group: str
    default: str = ""
    field_type: EnvType = "str"
    secret: bool = False
    help_text: str = ""
    multiline: bool = False
    multiline_height: int = 90


FIELDS: list[ConfigField] = [
    ConfigField("APP_HOST", "Host", "Server", "0.0.0.0"),
    ConfigField("APP_PORT", "Port", "Server", "8000", "int"),
    ConfigField("DEBUG", "Debug mode", "Server", "false", "bool"),
    ConfigField("LOG_LEVEL", "Log level", "Server", "INFO"),
    ConfigField("LOG_DIR", "Log directory", "Server", "logs"),
    ConfigField("STATELESS_MODE", "Stateless mode", "Server", "false", "bool"),
    ConfigField("AUTH_ENABLED", "Auth enabled", "Server", "true", "bool"),
    ConfigField("MEMORY_ENABLED", "Memory enabled", "Server", "true", "bool"),
    ConfigField("DATABASE_URL", "PostgreSQL URL", "Server", "", secret=True),
    ConfigField("AUTH_SECRET_KEY", "Auth secret key", "Server", "", secret=True),
    ConfigField("AUTH_TOKEN_TTL_SECONDS", "Auth token TTL, sec", "Server", "86400", "int"),
    ConfigField("INVARIANTS_FILE", "Project invariants file", "Server", "docs/assistant_invariants.json"),
    ConfigField("DB_POOL_MIN_SIZE", "DB pool min size", "Server", "1", "int"),
    ConfigField("DB_POOL_MAX_SIZE", "DB pool max size", "Server", "10", "int"),
    ConfigField("LLM_API_KEY", "LLM API key", "LLM", "", secret=True),
    ConfigField("LLM_BASE_URL", "LLM base URL", "LLM", "http://127.0.0.1:11434/v1"),
    ConfigField("DEFAULT_LLM_PROVIDER", "Default LLM provider", "LLM", "default"),
    ConfigField(
        "LLM_PROVIDERS",
        "LLM providers",
        "LLM",
        "",
        "json",
        multiline=True,
        multiline_height=220,
    ),
    ConfigField("DEFAULT_MODEL", "Default model", "LLM", "qwen2.5:7b-instruct"),
    ConfigField("REQUEST_TIMEOUT_SECONDS", "LLM timeout, sec", "LLM", "60", "int"),
    ConfigField("MAX_TEMPERATURE", "Max temperature", "LLM", "1.2", "float"),
    ConfigField("MAX_MAX_TOKENS", "Max response tokens", "LLM", "4000", "int"),
    ConfigField("HISTORY_LIMIT", "History limit", "Memory", "20", "int"),
    ConfigField("MAX_HISTORY_LIMIT", "Max history limit", "Memory", "100", "int"),
    ConfigField("SUMMARY_TRIGGER_MESSAGES", "Summary trigger messages", "Memory", "24", "int"),
    ConfigField("SUMMARY_KEEP_LAST_MESSAGES", "Summary keep last messages", "Memory", "10", "int"),
    ConfigField("SUMMARY_MAX_INPUT_MESSAGES", "Summary max input messages", "Memory", "100", "int"),
    ConfigField("SUMMARY_MAX_TOKENS", "Summary max tokens", "Memory", "500", "int"),
    ConfigField("SUMMARY_MODEL", "Summary model override", "Memory", ""),
    ConfigField("RETRIEVAL_ENABLED", "Memory retrieval enabled", "Memory", "true", "bool"),
    ConfigField("RETRIEVAL_LIMIT", "Memory retrieval limit", "Memory", "6", "int"),
    ConfigField("RETRIEVAL_MIN_QUERY_CHARS", "Min retrieval query chars", "Memory", "8", "int"),
    ConfigField("RETRIEVAL_CANDIDATE_POOL", "Retrieval candidate pool", "Memory", "80", "int"),
    ConfigField("RETRIEVAL_MAX_CONTENT_CHARS", "Max memory fragment chars", "Memory", "1200", "int"),
    ConfigField("RETRIEVAL_MIN_SCORE", "Retrieval min score", "Memory", "0.08", "float"),
    ConfigField("RETRIEVAL_USE_TRIGRAM", "Use pg_trgm retrieval", "Memory", "true", "bool"),
    ConfigField("STICKY_FACTS_ENABLED", "Sticky facts enabled", "Memory", "true", "bool"),
    ConfigField("STICKY_FACTS_TRIGGER_MESSAGES", "Sticky facts trigger messages", "Memory", "6", "int"),
    ConfigField("STICKY_FACTS_MAX_INPUT_MESSAGES", "Sticky facts max input messages", "Memory", "24", "int"),
    ConfigField("STICKY_FACTS_MAX_TOKENS", "Sticky facts max tokens", "Memory", "350", "int"),
    ConfigField("STICKY_FACTS_MODEL", "Sticky facts model override", "Memory", ""),
    ConfigField("STICKY_FACTS_MAX_ITEMS", "Sticky facts max items", "Memory", "20", "int"),
    ConfigField("TASK_MEMORY_ENABLED", "Task memory enabled", "Tasks", "true", "bool"),
    ConfigField("TASK_AUTO_ID_FOR_RAG_CHAT", "Auto task id for RAG chat", "Tasks", "true", "bool"),
    ConfigField("TASK_SHOW_TRANSITIONS", "Show task transitions", "Tasks", "true", "bool"),
    ConfigField("TASK_REQUIRE_PLAN_APPROVAL", "Require plan approval", "Tasks", "true", "bool"),
    ConfigField("TASK_GOAL_MAX_CHARS", "Goal max chars", "Tasks", "1000", "int"),
    ConfigField("TASK_LAST_USER_MESSAGE_MAX_CHARS", "Last user message chars", "Tasks", "1000", "int"),
    ConfigField("TASK_LAST_RESPONSE_PREVIEW_CHARS", "Response preview chars", "Tasks", "500", "int"),
    ConfigField("TASK_CLARIFIED_POINTS_LIMIT", "Clarified points limit", "Tasks", "12", "int"),
    ConfigField("TASK_CONSTRAINTS_LIMIT", "Constraints limit", "Tasks", "10", "int"),
    ConfigField("TASK_FIXED_TERMS_LIMIT", "Fixed terms limit", "Tasks", "12", "int"),
    ConfigField("TASK_OPEN_QUESTIONS_LIMIT", "Open questions limit", "Tasks", "5", "int"),
    ConfigField("RAG_ENABLED", "RAG enabled", "RAG", "false", "bool"),
    ConfigField("RAG_STRATEGY", "RAG strategy", "RAG", "structure"),
    ConfigField("RAG_INDEX_FILE", "RAG FAISS index file", "RAG", ""),
    ConfigField("RAG_METADATA_FILE", "RAG metadata file", "RAG", ""),
    ConfigField("RAG_EMBED_MODEL", "RAG embedding model", "RAG", "bge-m3"),
    ConfigField("RAG_OLLAMA_URL", "RAG Ollama URL", "RAG", "http://localhost:11434"),
    ConfigField("RAG_MAX_CHUNKS", "RAG max chunks", "RAG", "5", "int"),
    ConfigField("RAG_MIN_RELEVANCE_SCORE", "RAG min relevance score", "RAG", "0.75", "float"),
    ConfigField("RAG_DENSE_SEARCH_ENABLED", "Dense search", "RAG", "true", "bool"),
    ConfigField("RAG_LEXICAL_RERANK_ENABLED", "Lexical rerank", "RAG", "true", "bool"),
    ConfigField("RAG_LEXICAL_FALLBACK_ENABLED", "Lexical fallback", "RAG", "true", "bool"),
    ConfigField("MCP_ENABLED", "MCP enabled", "MCP", "false", "bool"),
    ConfigField("MCP_SERVER_SCRIPT", "Default MCP server script", "MCP", "../Day16/server.py"),
    ConfigField("MCP_SERVER_SCRIPTS", "MCP server scripts", "MCP", "[]", "json_list", multiline=True),
    ConfigField("MCP_WAIT_AFTER_START_SECONDS", "MCP startup wait, sec", "MCP", "0", "float"),
    ConfigField("MCP_MAX_TOOL_ROUNDTRIPS", "MCP max tool roundtrips", "MCP", "4", "int"),
    ConfigField("MCP_TOOL_CALL_TIMEOUT_SECONDS", "MCP tool timeout, sec", "MCP", "20", "float"),
]

FIELD_COMMENTS: dict[str, str] = {
    "APP_HOST": "Адрес, на котором слушает FastAPI.",
    "APP_PORT": "HTTP-порт FastAPI.",
    "DEBUG": "Включает подробный режим разработки.",
    "LOG_LEVEL": "Уровень логов: DEBUG, INFO, WARNING.",
    "LOG_DIR": "Папка для логов приложения.",
    "DATABASE_URL": "Строка подключения к PostgreSQL.",
    "AUTH_SECRET_KEY": "Секрет подписи JWT, храните приватно.",
    "AUTH_TOKEN_TTL_SECONDS": "Срок жизни токена авторизации.",
    "INVARIANTS_FILE": "Файл правил, добавляемых в prompt.",
    "DB_POOL_MIN_SIZE": "Минимум открытых соединений с БД.",
    "DB_POOL_MAX_SIZE": "Максимум открытых соединений с БД.",
    "LLM_API_KEY": "Ключ провайдера; для Ollama можно 'ollama'.",
    "LLM_BASE_URL": "OpenAI-compatible endpoint.",
    "DEFAULT_LLM_PROVIDER": "Provider, если клиент не выбрал другой.",
    "LLM_PROVIDERS": "JSON-массив профилей: id, base_url, api_key/api_key_env.",
    "DEFAULT_MODEL": "Модель по умолчанию.",
    "REQUEST_TIMEOUT_SECONDS": "Таймаут основного запроса к модели.",
    "MAX_TEMPERATURE": "Верхний лимит temperature.",
    "MAX_MAX_TOKENS": "Верхний лимит токенов ответа.",
    "HISTORY_LIMIT": "Сколько последних сообщений добавлять.",
    "MAX_HISTORY_LIMIT": "Жесткий максимум истории.",
    "SUMMARY_TRIGGER_MESSAGES": "Когда обновлять summary.",
    "SUMMARY_KEEP_LAST_MESSAGES": "Сколько сообщений оставить в summary.",
    "SUMMARY_MAX_INPUT_MESSAGES": "Сколько сообщений читать для summary.",
    "SUMMARY_MAX_TOKENS": "Примерный бюджет summary.",
    "SUMMARY_MODEL": "Отдельная модель для summary, если нужна.",
    "RETRIEVAL_ENABLED": "Добавлять фрагменты памяти.",
    "RETRIEVAL_LIMIT": "Сколько фрагментов памяти добавлять.",
    "RETRIEVAL_MIN_QUERY_CHARS": "Не искать для слишком коротких запросов.",
    "RETRIEVAL_CANDIDATE_POOL": "Сколько свежих записей памяти смотреть.",
    "RETRIEVAL_MAX_CONTENT_CHARS": "Максимум символов на фрагмент памяти.",
    "RETRIEVAL_MIN_SCORE": "Минимальный lexical score.",
    "RETRIEVAL_USE_TRIGRAM": "Режим поиска через pg_trgm.",
    "STICKY_FACTS_ENABLED": "Добавлять сохраненные факты пользователя.",
    "STICKY_FACTS_TRIGGER_MESSAGES": "Когда запускать извлечение фактов.",
    "STICKY_FACTS_MAX_INPUT_MESSAGES": "Сообщений для извлечения фактов.",
    "STICKY_FACTS_MAX_TOKENS": "Бюджет ответа извлечения фактов.",
    "STICKY_FACTS_MODEL": "Отдельная модель для фактов, если нужна.",
    "STICKY_FACTS_MAX_ITEMS": "Максимум сохраненных фактов.",
    "TASK_MEMORY_ENABLED": "Включать task memory для запросов с task_id.",
    "TASK_AUTO_ID_FOR_RAG_CHAT": "Использовать conversation_id как task_id в RAG-чате.",
    "TASK_SHOW_TRANSITIONS": "Показывать заметки о переходах задачи в чате.",
    "TASK_REQUIRE_PLAN_APPROVAL": "Блокировать выполнение до подтверждения плана.",
    "TASK_GOAL_MAX_CHARS": "Максимальная длина цели задачи.",
    "TASK_LAST_USER_MESSAGE_MAX_CHARS": "Сколько символов хранить из последнего вопроса.",
    "TASK_LAST_RESPONSE_PREVIEW_CHARS": "Сколько символов хранить из ответа ассистента.",
    "TASK_CLARIFIED_POINTS_LIMIT": "Сколько уточнений пользователя помнить.",
    "TASK_CONSTRAINTS_LIMIT": "Сколько ограничений задачи помнить.",
    "TASK_FIXED_TERMS_LIMIT": "Сколько терминов и ссылок помнить.",
    "TASK_OPEN_QUESTIONS_LIMIT": "Сколько открытых вопросов хранить.",
    "RAG_ENABLED": "Автоматически добавлять чанки документов.",
    "RAG_STRATEGY": "Индекс Day21: structure или fixed.",
    "RAG_INDEX_FILE": "Явный путь к FAISS-индексу.",
    "RAG_METADATA_FILE": "Явный путь к metadata чанков.",
    "RAG_EMBED_MODEL": "Embedding-модель Ollama для RAG.",
    "RAG_OLLAMA_URL": "Базовый URL Ollama для embeddings.",
    "RAG_MAX_CHUNKS": "Сколько document chunks добавлять.",
    "RAG_MIN_RELEVANCE_SCORE": "Минимальный score релевантности.",
    "RAG_DENSE_SEARCH_ENABLED": "Искать по embedding similarity.",
    "RAG_LEXICAL_RERANK_ENABLED": "Усиливать совпадения по словам.",
    "RAG_LEXICAL_FALLBACK_ENABLED": "Текстовый fallback, если dense не помог.",
    "MCP_ENABLED": "Автоматически подключать MCP tools.",
    "MCP_SERVER_SCRIPT": "Старый одиночный MCP server script.",
    "MCP_SERVER_SCRIPTS": "Один MCP server script на строку.",
    "MCP_WAIT_AFTER_START_SECONDS": "Пауза после старта MCP server.",
    "MCP_MAX_TOOL_ROUNDTRIPS": "Максимум циклов model-tool.",
    "MCP_TOOL_CALL_TIMEOUT_SECONDS": "Таймаут одного MCP tool call.",
}


LOCAL_OLLAMA_PRESET = {
    "LLM_API_KEY": "ollama",
    "LLM_BASE_URL": "http://127.0.0.1:11434/v1",
    "DEFAULT_MODEL": "qwen2.5:7b-instruct",
    "REQUEST_TIMEOUT_SECONDS": "120",
    "RAG_OLLAMA_URL": "http://localhost:11434",
    "RAG_MAX_CHUNKS": "3",
    "RETRIEVAL_LIMIT": "2",
    "HISTORY_LIMIT": "8",
    "SUMMARY_KEEP_LAST_MESSAGES": "6",
    "TASK_REQUIRE_PLAN_APPROVAL": "true",
    "TASK_OPEN_QUESTIONS_LIMIT": "3",
    "MCP_ENABLED": "false",
}


class EnvDocument:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.lines: list[str] = []
        self.values: dict[str, str] = {}
        self.positions: dict[str, list[int]] = {}

    def load(self) -> None:
        if self.path.exists():
            self.lines = self.path.read_text(encoding="utf-8").splitlines()
        else:
            self.lines = []
        self.values = {}
        self.positions = {}
        for index, raw_line in enumerate(self.lines):
            parsed = self._parse_assignment(raw_line)
            if parsed is None:
                continue
            key, value = parsed
            self.values[key] = value
            self.positions.setdefault(key, []).append(index)

    def save(self, values: dict[str, str], fields: list[ConfigField]) -> Path | None:
        backup_path: Path | None = None
        if self.path.exists():
            stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
            backup_path = self.path.with_name(f"{self.path.name}.backup-{stamp}")
            shutil.copy2(self.path, backup_path)

        lines = list(self.lines)
        field_by_key = {field.key: field for field in fields}
        for key, value in values.items():
            formatted = self._format_assignment(key, value, field_by_key[key])
            positions = self.positions.get(key, [])
            if positions:
                keep = positions[-1]
                for duplicate in positions[:-1]:
                    lines[duplicate] = f"# duplicate disabled by service_config_gui: {lines[duplicate]}"
                lines[keep] = formatted
            else:
                if lines and lines[-1].strip():
                    lines.append("")
                lines.append(formatted)

        self.path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        self.load()
        return backup_path

    @staticmethod
    def _parse_assignment(line: str) -> tuple[str, str] | None:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            return None
        key, value = stripped.split("=", 1)
        key = key.strip()
        if not key:
            return None
        return key, value.strip()

    @staticmethod
    def _format_assignment(key: str, value: str, field: ConfigField) -> str:
        normalized = value.strip()
        if field.field_type == "bool":
            normalized = normalize_bool(normalized)
        elif field.field_type == "json":
            normalized = normalize_json(normalized)
        elif field.field_type == "json_list":
            normalized = normalize_json_list(normalized)
        return f"{key}={normalized}"


class ServiceConfigApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM Assistant Service Config")
        self.geometry("1280x760")
        self.minsize(1100, 660)

        self.root_dir = Path(__file__).resolve().parent
        self.env_path = self.root_dir / ".env"
        self.env_doc = EnvDocument(self.env_path)
        self.widgets: dict[str, ctk.CTkEntry | ctk.CTkTextbox | ctk.CTkSwitch] = {}
        self.boolean_vars: dict[str, ctk.BooleanVar] = {}
        self.status_var = ctk.StringVar(value="Ready")
        self.path_var = ctk.StringVar(value=str(self.env_path))
        self.show_secrets_var = ctk.BooleanVar(value=False)

        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")
        self._build_layout()
        self.reload_config()

    def _build_layout(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(self)
        header.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        header.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            header,
            text="Service Configuration",
            font=ctk.CTkFont(size=20, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(8, 0), sticky="w")
        ctk.CTkLabel(header, textvariable=self.path_var, anchor="w").grid(
            row=1, column=0, columnspan=2, padx=10, pady=(0, 8), sticky="ew"
        )

        button_row = ctk.CTkFrame(header, fg_color="transparent")
        button_row.grid(row=0, column=1, padx=10, pady=8, sticky="e")
        ctk.CTkButton(button_row, text="Reload", width=100, command=self.reload_config).grid(
            row=0, column=0, padx=3, pady=0
        )
        ctk.CTkButton(button_row, text="Validate", width=100, command=self.validate_config).grid(
            row=0, column=1, padx=3, pady=0
        )
        ctk.CTkButton(button_row, text="Save", width=100, command=self.save_config).grid(
            row=0, column=2, padx=3, pady=0
        )
        ctk.CTkButton(button_row, text="Ollama preset", width=130, command=self.apply_ollama_preset).grid(
            row=0, column=3, padx=3, pady=0
        )

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=(0, 8))

        for group in dict.fromkeys(field.group for field in FIELDS):
            self._build_group_tab(group)

        footer = ctk.CTkFrame(self)
        footer.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        footer.grid_columnconfigure(0, weight=1)
        ctk.CTkLabel(footer, textvariable=self.status_var, anchor="w").grid(
            row=0, column=0, padx=10, pady=6, sticky="ew"
        )
        ctk.CTkSwitch(
            footer,
            text="Show secrets",
            variable=self.show_secrets_var,
            command=self._toggle_secret_visibility,
        ).grid(row=0, column=1, padx=10, pady=6, sticky="e")

    def _build_group_tab(self, group: str) -> None:
        self.tabs.add(group)
        tab = self.tabs.tab(group)
        tab.grid_columnconfigure(0, weight=1)
        tab.grid_rowconfigure(0, weight=1)

        scroll = ctk.CTkScrollableFrame(tab)
        scroll.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)
        scroll.grid_columnconfigure(1, weight=1)

        row = 0
        for field in [item for item in FIELDS if item.group == group]:
            comment = field.help_text or FIELD_COMMENTS.get(field.key, field.key)
            label_frame = ctk.CTkFrame(scroll, fg_color="transparent")
            label_frame.grid(row=row, column=0, padx=(8, 6), pady=(2, 5), sticky="new")
            label_frame.grid_columnconfigure(1, weight=1)
            ctk.CTkLabel(label_frame, text=field.label, anchor="w").grid(
                row=0, column=0, sticky="w", pady=(0, 0)
            )
            ctk.CTkLabel(
                label_frame,
                text=f" - {comment}",
                text_color="#777777",
                anchor="w",
                font=ctk.CTkFont(size=11),
            ).grid(row=0, column=1, sticky="ew", pady=(0, 0))
            if field.field_type == "bool":
                var = ctk.BooleanVar(value=False)
                widget = ctk.CTkSwitch(scroll, text=field.key, variable=var, height=26)
                self.boolean_vars[field.key] = var
            elif field.multiline:
                widget = ctk.CTkTextbox(scroll, height=field.multiline_height, wrap="word")
            else:
                widget = ctk.CTkEntry(scroll, height=26, show="*" if field.secret else "")
            widget.grid(row=row, column=1, padx=(6, 6), pady=(2, 5), sticky="new")
            self.widgets[field.key] = widget

            if field.key.endswith("_FILE") or field.key.endswith("_DIR") or field.key == "INVARIANTS_FILE":
                ctk.CTkButton(
                    scroll,
                    text="Browse",
                    width=80,
                    height=26,
                    command=lambda key=field.key: self._browse_path(key),
                ).grid(row=row, column=2, padx=(0, 8), pady=(2, 5), sticky="new")

            row += 1

    def reload_config(self) -> None:
        self.env_doc.load()
        for field in FIELDS:
            value = self.env_doc.values.get(field.key, field.default)
            self._set_field_value(field, value)
        duplicates = [key for key, positions in self.env_doc.positions.items() if len(positions) > 1]
        suffix = f" Duplicates detected: {', '.join(duplicates)}." if duplicates else ""
        self.status_var.set(f"Loaded {self.env_path}.{suffix}")

    def save_config(self) -> None:
        values = self._collect_values()
        errors = validate_values(values, FIELDS)
        if errors:
            messagebox.showerror("Invalid configuration", "\n".join(errors))
            self.status_var.set("Validation failed. Fix highlighted values and save again.")
            return
        backup_path = self.env_doc.save(values, FIELDS)
        backup_note = f" Backup: {backup_path.name}" if backup_path else ""
        self.status_var.set(f"Saved {self.env_path.name}.{backup_note} Restart the service to apply changes.")
        messagebox.showinfo("Saved", "Configuration saved. Restart the FastAPI service to apply changes.")

    def validate_config(self) -> None:
        values = self._collect_values()
        errors = validate_values(values, FIELDS)
        if errors:
            messagebox.showerror("Invalid configuration", "\n".join(errors))
            self.status_var.set("Validation failed.")
            return
        warnings = build_warnings(values, self.env_doc.positions)
        if warnings:
            messagebox.showwarning("Configuration warnings", "\n".join(warnings))
            self.status_var.set("Validation passed with warnings.")
            return
        messagebox.showinfo("Valid configuration", "Configuration looks valid.")
        self.status_var.set("Validation passed.")

    def apply_ollama_preset(self) -> None:
        if not messagebox.askyesno(
            "Apply Ollama preset",
            "Apply local Ollama defaults optimized for a smaller prompt?",
        ):
            return
        field_by_key = {field.key: field for field in FIELDS}
        for key, value in LOCAL_OLLAMA_PRESET.items():
            field = field_by_key.get(key)
            if field:
                self._set_field_value(field, value)
        self.status_var.set("Applied local Ollama preset. Review values, then Save.")

    def _browse_path(self, key: str) -> None:
        current_value = self._get_field_value(key)
        initial_dir = self.root_dir
        if current_value:
            candidate = Path(current_value)
            if not candidate.is_absolute():
                candidate = (self.root_dir / candidate).resolve()
            if candidate.parent.exists():
                initial_dir = candidate.parent

        if key.endswith("_DIR"):
            selected = filedialog.askdirectory(initialdir=str(initial_dir))
        else:
            selected = filedialog.askopenfilename(initialdir=str(initial_dir))
        if not selected:
            return
        try:
            display_path = str(Path(selected).resolve().relative_to(self.root_dir))
        except ValueError:
            display_path = selected
        self._set_raw_widget_value(key, display_path)

    def _collect_values(self) -> dict[str, str]:
        return {field.key: self._get_field_value(field.key) for field in FIELDS}

    def _set_field_value(self, field: ConfigField, value: str) -> None:
        if field.field_type == "bool":
            self.boolean_vars[field.key].set(value.strip().lower() in {"1", "true", "yes", "on"})
            return
        if field.field_type == "json":
            value = pretty_json(value)
        elif field.field_type == "json_list":
            value = pretty_json_list(value)
        self._set_raw_widget_value(field.key, value)

    def _set_raw_widget_value(self, key: str, value: str) -> None:
        widget = self.widgets[key]
        if isinstance(widget, ctk.CTkTextbox):
            widget.delete("1.0", "end")
            widget.insert("1.0", value)
        else:
            widget.delete(0, "end")
            widget.insert(0, value)

    def _get_field_value(self, key: str) -> str:
        widget = self.widgets[key]
        if key in self.boolean_vars:
            return "true" if self.boolean_vars[key].get() else "false"
        if isinstance(widget, ctk.CTkTextbox):
            return widget.get("1.0", "end").strip()
        return widget.get().strip()

    def _toggle_secret_visibility(self) -> None:
        show = "" if self.show_secrets_var.get() else "*"
        secret_keys = {field.key for field in FIELDS if field.secret}
        for key in secret_keys:
            widget = self.widgets.get(key)
            if isinstance(widget, ctk.CTkEntry):
                widget.configure(show=show)


def normalize_bool(value: str) -> str:
    return "true" if value.strip().lower() in {"1", "true", "yes", "on"} else "false"


def pretty_json_list(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    if not isinstance(parsed, list):
        return normalized
    return "\n".join(str(item) for item in parsed)


def pretty_json(value: str) -> str:
    normalized = value.strip()
    if not normalized:
        return ""
    try:
        parsed = json.loads(normalized)
    except json.JSONDecodeError:
        return normalized
    return json.dumps(parsed, ensure_ascii=False, indent=2)


def normalize_json(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return ""
    parsed = json.loads(stripped)
    return json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))


def normalize_json_list(value: str) -> str:
    stripped = value.strip()
    if not stripped:
        return "[]"
    try:
        parsed = json.loads(stripped)
        if isinstance(parsed, list):
            return json.dumps([str(item) for item in parsed], ensure_ascii=False, separators=(",", ":"))
    except json.JSONDecodeError:
        pass
    items = [line.strip() for line in stripped.replace(";", "\n").splitlines() if line.strip()]
    return json.dumps(items, ensure_ascii=False, separators=(",", ":"))


def validate_values(values: dict[str, str], fields: list[ConfigField]) -> list[str]:
    errors: list[str] = []
    for field in fields:
        value = values[field.key].strip()
        if field.field_type == "int" and value:
            try:
                int(value)
            except ValueError:
                errors.append(f"{field.key} must be an integer.")
        elif field.field_type == "float" and value:
            try:
                float(value)
            except ValueError:
                errors.append(f"{field.key} must be a number.")
        elif field.field_type == "json" and value:
            try:
                json.loads(value)
            except json.JSONDecodeError:
                errors.append(f"{field.key} must be valid JSON.")
        elif field.field_type == "json_list":
            try:
                parsed = json.loads(normalize_json_list(value))
            except json.JSONDecodeError:
                errors.append(f"{field.key} must be a JSON list or one item per line.")
                continue
            if not isinstance(parsed, list):
                errors.append(f"{field.key} must be a list.")

    stateless_mode = values.get("STATELESS_MODE", "").strip().lower() in {"1", "true", "yes", "on"}
    auth_enabled = values.get("AUTH_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    memory_enabled = values.get("MEMORY_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}
    if not stateless_mode and (auth_enabled or memory_enabled) and not values.get("DATABASE_URL", "").strip():
        errors.append("DATABASE_URL is required unless STATELESS_MODE=true or both AUTH_ENABLED=false and MEMORY_ENABLED=false.")
    if not values.get("LLM_BASE_URL", "").strip():
        errors.append("LLM_BASE_URL is required.")
    if not values.get("DEFAULT_MODEL", "").strip():
        errors.append("DEFAULT_MODEL is required.")
    return errors


def build_warnings(values: dict[str, str], positions: dict[str, list[int]]) -> list[str]:
    warnings: list[str] = []
    duplicates = [key for key, key_positions in positions.items() if len(key_positions) > 1]
    if duplicates:
        warnings.append("Duplicate keys will be normalized on save: " + ", ".join(sorted(duplicates)))
    if "11434" in values.get("LLM_BASE_URL", "") and values.get("LLM_API_KEY", "") == "":
        warnings.append("Ollama usually accepts any non-empty LLM_API_KEY placeholder, for example 'ollama'.")
    return warnings


def main() -> None:
    app = ServiceConfigApp()
    app.mainloop()


if __name__ == "__main__":
    main()
