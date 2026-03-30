import json
import threading
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import requests
import customtkinter as ctk
from tkinter import messagebox


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


MEMORY_STRATEGIES = [
    "none",
    "window",
    "summary",
    "retrieval",
    "hybrid",
    "facts",
    "hybrid_facts",
]

ROLES = ["system", "user", "assistant"]


@dataclass
class AppState:
    conversation_id: str = ""
    branch_id: str = "main"
    selected_message_uuid: str = ""
    models: List[str] = field(default_factory=list)


class JsonViewer(ctk.CTkToplevel):
    def __init__(self, master, title: str, data: Any):
        super().__init__(master)
        self.title(title)
        self.geometry("900x650")
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        text = ctk.CTkTextbox(self, wrap="none")
        text.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        try:
            pretty = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            pretty = str(data)
        text.insert("1.0", pretty)
        text.configure(state="disabled")


class LLMGatewayClient:
    def __init__(self, base_url_getter, timeout_getter):
        self._base_url_getter = base_url_getter
        self._timeout_getter = timeout_getter

    @property
    def base_url(self) -> str:
        return self._base_url_getter().rstrip("/")

    @property
    def timeout(self) -> float:
        return float(self._timeout_getter())

    def _request(self, method: str, path: str, **kwargs):
        url = f"{self.base_url}{path}"
        headers = kwargs.pop("headers", {})
        headers.setdefault("Content-Type", "application/json")
        return requests.request(method, url, headers=headers, timeout=self.timeout, **kwargs)

    def health(self):
        return self._request("GET", "/health")

    def models(self):
        return self._request("GET", "/models")

    def generate(self, payload: Dict[str, Any]):
        return self._request("POST", "/generate", json=payload)

    def messages(self, conversation_id: str, branch_id: str, limit: int):
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/messages",
            params={"branch_id": branch_id, "limit": limit},
        )

    def summary(self, conversation_id: str, branch_id: str):
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/summary",
            params={"branch_id": branch_id},
        )

    def refresh_summary(self, conversation_id: str, branch_id: str, model: str, user_id: str):
        params = {"branch_id": branch_id}
        if model:
            params["model"] = model
        if user_id:
            params["user_id"] = user_id
        return self._request("POST", f"/conversations/{conversation_id}/summary/refresh", params=params)

    def facts(self, conversation_id: str, branch_id: str):
        return self._request(
            "GET",
            f"/conversations/{conversation_id}/facts",
            params={"branch_id": branch_id},
        )

    def refresh_facts(self, conversation_id: str, branch_id: str, model: str, user_id: str):
        params = {"branch_id": branch_id}
        if model:
            params["model"] = model
        if user_id:
            params["user_id"] = user_id
        return self._request("POST", f"/conversations/{conversation_id}/facts/refresh", params=params)

    def branches(self, conversation_id: str):
        return self._request("GET", f"/conversations/{conversation_id}/branches")

    def create_branch(self, conversation_id: str, branch_id: str, fork_from_message_uuid: str, source_branch_id: str):
        return self._request(
            "POST",
            f"/conversations/{conversation_id}/branches",
            params={
                "branch_id": branch_id,
                "fork_from_message_uuid": fork_from_message_uuid,
                "source_branch_id": source_branch_id,
            },
        )


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LLM Gateway Tester")
        self.geometry("1680x980")
        self.minsize(1440, 820)

        self.state_data = AppState()
        self.client = LLMGatewayClient(self.get_base_url, self.get_timeout)

        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()
        self._set_status("Готово")

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, corner_radius=0, width=370)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        for i in range(40):
            sidebar.grid_rowconfigure(i, weight=0)
        sidebar.grid_rowconfigure(39, weight=1)
        sidebar.grid_columnconfigure(0, weight=1)

        row = 0
        ctk.CTkLabel(sidebar, text="LLM Gateway Tester", font=ctk.CTkFont(size=24, weight="bold")).grid(
            row=row, column=0, sticky="w", padx=16, pady=(16, 8)
        )
        row += 1

        self.base_url_var = ctk.StringVar(value="http://localhost:8000")
        self.timeout_var = ctk.StringVar(value="60")
        self.model_var = ctk.StringVar(value="")
        self.user_id_var = ctk.StringVar(value="")
        self.conv_var = ctk.StringVar(value="")
        self.branch_var = ctk.StringVar(value="main")
        self.history_limit_var = ctk.StringVar(value="20")
        self.retrieval_limit_var = ctk.StringVar(value="6")
        self.temperature_var = ctk.StringVar(value="0.2")
        self.max_tokens_var = ctk.StringVar(value="500")
        self.top_p_var = ctk.StringVar(value="1.0")
        self.presence_penalty_var = ctk.StringVar(value="0.0")
        self.frequency_penalty_var = ctk.StringVar(value="0.0")
        self.memory_strategy_var = ctk.StringVar(value="hybrid")
        self.use_memory_var = ctk.BooleanVar(value=True)
        self.retrieval_enabled_var = ctk.BooleanVar(value=True)
        self.sticky_facts_enabled_var = ctk.BooleanVar(value=True)
        self.stop_var = ctk.StringVar(value="")

        fields = [
            ("Base URL", self.base_url_var),
            ("Timeout (sec)", self.timeout_var),
            ("Model", self.model_var),
            ("User ID", self.user_id_var),
            ("Conversation ID", self.conv_var),
            ("Branch ID", self.branch_var),
        ]
        for label, var in fields:
            ctk.CTkLabel(sidebar, text=label).grid(row=row, column=0, sticky="w", padx=16)
            row += 1
            ctk.CTkEntry(sidebar, textvariable=var).grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
            row += 1

        ctk.CTkLabel(sidebar, text="Memory strategy").grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        ctk.CTkComboBox(sidebar, values=MEMORY_STRATEGIES, variable=self.memory_strategy_var).grid(
            row=row, column=0, sticky="ew", padx=16, pady=(0, 8)
        )
        row += 1

        ctk.CTkCheckBox(sidebar, text="Use memory", variable=self.use_memory_var).grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        ctk.CTkCheckBox(sidebar, text="Retrieval enabled", variable=self.retrieval_enabled_var).grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        ctk.CTkCheckBox(sidebar, text="Sticky facts enabled", variable=self.sticky_facts_enabled_var).grid(row=row, column=0, sticky="w", padx=16)
        row += 1

        numeric_fields = [
            ("History limit", self.history_limit_var),
            ("Retrieval limit", self.retrieval_limit_var),
            ("Temperature", self.temperature_var),
            ("Max tokens", self.max_tokens_var),
            ("Top-p", self.top_p_var),
            ("Presence penalty", self.presence_penalty_var),
            ("Frequency penalty", self.frequency_penalty_var),
            ("Stop sequences (через |)", self.stop_var),
        ]
        for label, var in numeric_fields:
            ctk.CTkLabel(sidebar, text=label).grid(row=row, column=0, sticky="w", padx=16)
            row += 1
            ctk.CTkEntry(sidebar, textvariable=var).grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
            row += 1

        btn_frame = ctk.CTkFrame(sidebar)
        btn_frame.grid(row=row, column=0, sticky="ew", padx=12, pady=8)
        btn_frame.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(btn_frame, text="Health", command=self.fetch_health).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Models", command=self.fetch_models).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Сообщения", command=self.fetch_messages).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Branches", command=self.fetch_branches).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Summary", command=self.fetch_summary).grid(row=2, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Facts", command=self.fetch_facts).grid(row=2, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Refresh summary", command=self.refresh_summary).grid(row=3, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Refresh facts", command=self.refresh_facts).grid(row=3, column=1, padx=4, pady=4, sticky="ew")
        row += 1

        appearance = ctk.CTkOptionMenu(sidebar, values=["System", "Light", "Dark"], command=ctk.set_appearance_mode)
        appearance.set("System")
        ctk.CTkLabel(sidebar, text="Appearance").grid(row=row, column=0, sticky="w", padx=16, pady=(8, 0))
        row += 1
        appearance.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        row += 1

        self.status_label = ctk.CTkLabel(sidebar, text="", justify="left", wraplength=320)
        self.status_label.grid(row=39, column=0, sticky="sw", padx=16, pady=16)

    def _build_main(self):
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(1, weight=1)
        main.grid_rowconfigure(2, weight=1)

        toolbar = ctk.CTkFrame(main)
        toolbar.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        toolbar.grid_columnconfigure(0, weight=1)

        self.generate_button = ctk.CTkButton(toolbar, text="Generate", height=40, command=self.generate)
        self.generate_button.grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkButton(toolbar, text="Новый conversation_id", command=self.new_conversation).grid(row=0, column=1, padx=8, pady=8)
        ctk.CTkButton(toolbar, text="Очистить чат", command=self.clear_chat).grid(row=0, column=2, padx=8, pady=8)
        ctk.CTkButton(toolbar, text="Показать raw response", command=self.show_last_response).grid(row=0, column=3, padx=8, pady=8)

        left_top = ctk.CTkFrame(main)
        left_top.grid(row=1, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        left_top.grid_columnconfigure(0, weight=1)
        left_top.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(left_top, text="Messages payload", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )

        self.messages_text = ctk.CTkTextbox(left_top, wrap="word")
        self.messages_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        self.messages_text.insert(
            "1.0",
            json.dumps(
                [
                    {"role": "system", "content": "You are a helpful assistant."},
                    {"role": "user", "content": "Привет!"},
                ],
                ensure_ascii=False,
                indent=2,
            ),
        )

        right_top = ctk.CTkFrame(main)
        right_top.grid(row=1, column=1, sticky="nsew", pady=(0, 8))
        right_top.grid_columnconfigure(0, weight=1)
        right_top.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right_top, text="Validation / Metadata", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )

        validation_tabs = ctk.CTkTabview(right_top)
        validation_tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))
        validation_tabs.add("Validation")
        validation_tabs.add("Metadata")
        validation_tabs.add("Headers")

        self.validation_text = ctk.CTkTextbox(validation_tabs.tab("Validation"), wrap="word")
        self.validation_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.validation_text.insert(
            "1.0",
            json.dumps(
                {
                    "min_output_length": None,
                    "max_output_length": None,
                    "must_contain": [],
                    "forbid_phrases": [],
                    "require_json": False,
                },
                ensure_ascii=False,
                indent=2,
            ),
        )

        self.metadata_text = ctk.CTkTextbox(validation_tabs.tab("Metadata"), wrap="word")
        self.metadata_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.metadata_text.insert("1.0", "{}")

        self.headers_text = ctk.CTkTextbox(validation_tabs.tab("Headers"), wrap="word")
        self.headers_text.pack(fill="both", expand=True, padx=6, pady=6)
        self.headers_text.insert("1.0", json.dumps({"Authorization": "Bearer <token-if-needed>"}, ensure_ascii=False, indent=2))

        bottom_left = ctk.CTkFrame(main)
        bottom_left.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        bottom_left.grid_columnconfigure(0, weight=1)
        bottom_left.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(bottom_left, text="Chat / Server response", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )
        self.chat_text = ctk.CTkTextbox(bottom_left, wrap="word")
        self.chat_text.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 12))

        bottom_right = ctk.CTkFrame(main)
        bottom_right.grid(row=2, column=1, sticky="nsew")
        bottom_right.grid_columnconfigure(0, weight=1)
        bottom_right.grid_rowconfigure(1, weight=1)
        bottom_right.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(bottom_right, text="Conversation explorer", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(10, 6)
        )

        self.messages_list = ctk.CTkTextbox(bottom_right, wrap="word")
        self.messages_list.grid(row=1, column=0, sticky="nsew", padx=12, pady=(0, 10))

        branch_frame = ctk.CTkFrame(bottom_right)
        branch_frame.grid(row=2, column=0, sticky="ew", padx=12, pady=(0, 10))
        branch_frame.grid_columnconfigure(0, weight=1)
        branch_frame.grid_columnconfigure(1, weight=1)
        self.new_branch_name_var = ctk.StringVar(value="experiment-1")
        self.fork_message_uuid_var = ctk.StringVar(value="")
        ctk.CTkEntry(branch_frame, textvariable=self.new_branch_name_var, placeholder_text="new branch id").grid(
            row=0, column=0, padx=4, pady=4, sticky="ew"
        )
        ctk.CTkEntry(branch_frame, textvariable=self.fork_message_uuid_var, placeholder_text="fork_from_message_uuid").grid(
            row=0, column=1, padx=4, pady=4, sticky="ew"
        )
        ctk.CTkButton(branch_frame, text="Create branch", command=self.create_branch).grid(
            row=1, column=0, columnspan=2, padx=4, pady=4, sticky="ew"
        )

        self.branches_text = ctk.CTkTextbox(bottom_right, wrap="word")
        self.branches_text.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))

        self.last_response_data: Optional[Any] = None

    def get_base_url(self) -> str:
        return self.base_url_var.get().strip()

    def get_timeout(self) -> str:
        return self.timeout_var.get().strip() or "60"

    def _set_status(self, text: str):
        self.status_label.configure(text=text)

    def _append_chat(self, title: str, data: Any):
        self.chat_text.insert("end", f"\n=== {title} ===\n")
        try:
            self.chat_text.insert("end", json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            self.chat_text.insert("end", str(data))
        self.chat_text.insert("end", "\n")
        self.chat_text.see("end")

    def _run_async(self, label: str, func, on_success=None):
        self._set_status(f"Выполняется: {label}")

        def worker():
            try:
                result = func()
                self.after(0, lambda: self._handle_success(label, result, on_success))
            except Exception as exc:
                self.after(0, lambda: self._handle_error(label, exc))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_success(self, label: str, response, on_success=None):
        try:
            data = response.json()
        except Exception:
            data = {"status_code": response.status_code, "text": response.text}

        self.last_response_data = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": data,
        }

        if response.ok:
            self._set_status(f"Готово: {label} ({response.status_code})")
            if on_success:
                on_success(data)
        else:
            self._set_status(f"Ошибка: {label} ({response.status_code})")
            self._append_chat(f"{label} error", self.last_response_data)
            messagebox.showerror("Request error", f"{label}: HTTP {response.status_code}")

    def _handle_error(self, label: str, exc: Exception):
        self._set_status(f"Ошибка: {label}")
        self._append_chat(f"{label} exception", {"error": str(exc)})
        messagebox.showerror("Exception", f"{label}: {exc}")

    def _parse_json_text(self, widget: ctk.CTkTextbox, label: str):
        raw = widget.get("1.0", "end").strip()
        if not raw:
            return None
        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ValueError(f"{label}: invalid JSON: {exc}") from exc

    def _build_headers(self) -> Dict[str, str]:
        data = self._parse_json_text(self.headers_text, "Headers") or {}
        if not isinstance(data, dict):
            raise ValueError("Headers must be JSON object")
        return {str(k): str(v) for k, v in data.items() if str(v).strip()}

    def _build_generate_payload(self) -> Dict[str, Any]:
        messages = self._parse_json_text(self.messages_text, "Messages payload")
        validation = self._parse_json_text(self.validation_text, "Validation")
        metadata = self._parse_json_text(self.metadata_text, "Metadata")

        if not isinstance(messages, list) or not messages:
            raise ValueError("Messages payload must be a non-empty JSON array")
        if validation is not None and not isinstance(validation, dict):
            raise ValueError("Validation must be a JSON object")
        if metadata is not None and not isinstance(metadata, dict):
            raise ValueError("Metadata must be a JSON object")

        payload: Dict[str, Any] = {
            "model": self.model_var.get().strip() or None,
            "messages": messages,
            "conversation_id": self.conv_var.get().strip() or None,
            "branch_id": self.branch_var.get().strip() or "main",
            "use_memory": self.use_memory_var.get(),
            "memory_strategy": self.memory_strategy_var.get(),
            "history_limit": int(self.history_limit_var.get()),
            "retrieval_enabled": self.retrieval_enabled_var.get(),
            "retrieval_limit": int(self.retrieval_limit_var.get()),
            "sticky_facts_enabled": self.sticky_facts_enabled_var.get(),
            "temperature": float(self.temperature_var.get()),
            "max_tokens": int(self.max_tokens_var.get()),
            "top_p": float(self.top_p_var.get()),
            "presence_penalty": float(self.presence_penalty_var.get()),
            "frequency_penalty": float(self.frequency_penalty_var.get()),
            "user_id": self.user_id_var.get().strip() or None,
            "metadata": metadata or {},
            "validation": validation,
        }

        stop_value = self.stop_var.get().strip()
        if stop_value:
            payload["stop"] = [item.strip() for item in stop_value.split("|") if item.strip()]

        return {k: v for k, v in payload.items() if v is not None}

    def new_conversation(self):
        conv_id = f"conv-{uuid.uuid4().hex[:12]}"
        self.conv_var.set(conv_id)
        self.branch_var.set("main")
        self._set_status(f"Создан новый conversation_id: {conv_id}")

    def clear_chat(self):
        self.chat_text.delete("1.0", "end")
        self.messages_list.delete("1.0", "end")
        self.branches_text.delete("1.0", "end")
        self._set_status("Очищено")

    def show_last_response(self):
        if self.last_response_data is None:
            messagebox.showinfo("Raw response", "Пока нет ответа сервера")
            return
        JsonViewer(self, "Raw response", self.last_response_data)

    def fetch_health(self):
        headers = self._build_headers()
        self._run_async("health", lambda: self.client._request("GET", "/health", headers=headers), self._on_health)

    def _on_health(self, data):
        self._append_chat("health", data)

    def fetch_models(self):
        headers = self._build_headers()
        self._run_async("models", lambda: self.client._request("GET", "/models", headers=headers), self._on_models)

    def _on_models(self, data):
        models = [item.get("id") for item in data.get("data", []) if item.get("id")]
        self.state_data.models = models
        self._append_chat("models", data)
        if models and not self.model_var.get().strip():
            self.model_var.set(models[0])

    def generate(self):
        try:
            payload = self._build_generate_payload()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Payload error", str(exc))
            return

        def do_request():
            return self.client._request("POST", "/generate", json=payload, headers=headers)

        self.generate_button.configure(state="disabled")
        self._run_async("generate", do_request, self._on_generate)

    def _on_generate(self, data):
        self.generate_button.configure(state="normal")
        self._append_chat("generate", data)

        conversation_id = data.get("conversation_id")
        branch_id = data.get("branch_id")
        if conversation_id:
            self.conv_var.set(conversation_id)
        if branch_id:
            self.branch_var.set(branch_id)

        content = data.get("content", "")
        meta = {
            "model": data.get("model"),
            "latency_ms": data.get("latency_ms"),
            "usage": data.get("usage"),
            "summary_used": data.get("summary_used"),
            "summary_updated": data.get("summary_updated"),
            "retrieval_used": data.get("retrieval_used"),
            "retrieval_messages_used": data.get("retrieval_messages_used"),
            "sticky_facts_used": data.get("sticky_facts_used"),
            "sticky_facts_updated": data.get("sticky_facts_updated"),
            "sticky_facts_count": data.get("sticky_facts_count"),
            "validation": data.get("validation"),
        }
        self.chat_text.insert("end", f"\n--- Assistant content ---\n{content}\n")
        self.chat_text.insert("end", f"\n--- Runtime info ---\n{json.dumps(meta, ensure_ascii=False, indent=2)}\n")
        self.chat_text.see("end")
        self.fetch_messages()
        self.fetch_branches()

    def _current_conversation(self) -> str:
        value = self.conv_var.get().strip()
        if not value:
            raise ValueError("Conversation ID is required")
        return value

    def _current_branch(self) -> str:
        return self.branch_var.get().strip() or "main"

    def fetch_messages(self):
        try:
            conversation_id = self._current_conversation()
            branch_id = self._current_branch()
            headers = self._build_headers()
            limit = int(self.history_limit_var.get())
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return

        self._run_async(
            "messages",
            lambda: self.client._request(
                "GET",
                f"/conversations/{conversation_id}/messages",
                params={"branch_id": branch_id, "limit": limit},
                headers=headers,
            ),
            self._on_messages,
        )

    def _on_messages(self, data):
        self.messages_list.delete("1.0", "end")
        lines = []
        for item in data.get("messages", []):
            msg_uuid = item.get("message_uuid", "")
            role = item.get("role", "")
            seq_no = item.get("seq_no", "")
            created_at = item.get("created_at", "")
            content = item.get("content", "")
            preview = content[:500] + ("..." if len(content) > 500 else "")
            lines.append(
                f"[{seq_no}] {role} | uuid={msg_uuid}\ncreated_at={created_at}\n{preview}\n{'-' * 80}"
            )
        self.messages_list.insert("1.0", "\n".join(lines) if lines else "Нет сообщений")

    def fetch_summary(self):
        try:
            conversation_id = self._current_conversation()
            branch_id = self._current_branch()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self._run_async(
            "summary",
            lambda: self.client._request(
                "GET", f"/conversations/{conversation_id}/summary", params={"branch_id": branch_id}, headers=headers
            ),
            lambda data: self._append_chat("summary", data),
        )

    def refresh_summary(self):
        try:
            conversation_id = self._current_conversation()
            branch_id = self._current_branch()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self._run_async(
            "refresh_summary",
            lambda: self.client._request(
                "POST",
                f"/conversations/{conversation_id}/summary/refresh",
                params={
                    "branch_id": branch_id,
                    **({"model": self.model_var.get().strip()} if self.model_var.get().strip() else {}),
                    **({"user_id": self.user_id_var.get().strip()} if self.user_id_var.get().strip() else {}),
                },
                headers=headers,
            ),
            lambda data: self._append_chat("refresh_summary", data),
        )

    def fetch_facts(self):
        try:
            conversation_id = self._current_conversation()
            branch_id = self._current_branch()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self._run_async(
            "facts",
            lambda: self.client._request(
                "GET", f"/conversations/{conversation_id}/facts", params={"branch_id": branch_id}, headers=headers
            ),
            lambda data: self._append_chat("facts", data),
        )

    def refresh_facts(self):
        try:
            conversation_id = self._current_conversation()
            branch_id = self._current_branch()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self._run_async(
            "refresh_facts",
            lambda: self.client._request(
                "POST",
                f"/conversations/{conversation_id}/facts/refresh",
                params={
                    "branch_id": branch_id,
                    **({"model": self.model_var.get().strip()} if self.model_var.get().strip() else {}),
                    **({"user_id": self.user_id_var.get().strip()} if self.user_id_var.get().strip() else {}),
                },
                headers=headers,
            ),
            lambda data: self._append_chat("refresh_facts", data),
        )

    def fetch_branches(self):
        try:
            conversation_id = self._current_conversation()
            headers = self._build_headers()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return
        self._run_async(
            "branches",
            lambda: self.client._request("GET", f"/conversations/{conversation_id}/branches", headers=headers),
            self._on_branches,
        )

    def _on_branches(self, data):
        self.branches_text.delete("1.0", "end")
        branches = data.get("branches", [])
        if not branches:
            self.branches_text.insert("1.0", "Нет branch-ей")
            return
        text = []
        for br in branches:
            text.append(
                f"branch_id={br.get('branch_id')} | messages_count={br.get('messages_count')} | created_at={br.get('created_at')} | updated_at={br.get('updated_at')}"
            )
        self.branches_text.insert("1.0", "\n".join(text))

    def create_branch(self):
        try:
            conversation_id = self._current_conversation()
            source_branch_id = self._current_branch()
            branch_id = self.new_branch_name_var.get().strip()
            fork_uuid = self.fork_message_uuid_var.get().strip()
            headers = self._build_headers()
            if not branch_id:
                raise ValueError("Введите new branch id")
            if not fork_uuid:
                raise ValueError("Введите fork_from_message_uuid")
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return

        self._run_async(
            "create_branch",
            lambda: self.client._request(
                "POST",
                f"/conversations/{conversation_id}/branches",
                params={
                    "branch_id": branch_id,
                    "fork_from_message_uuid": fork_uuid,
                    "source_branch_id": source_branch_id,
                },
                headers=headers,
            ),
            self._after_create_branch,
        )

    def _after_create_branch(self, data):
        self._append_chat("create_branch", data)
        if data.get("branch_id"):
            self.branch_var.set(data["branch_id"])
        self.fetch_branches()


if __name__ == "__main__":
    app = App()
    app.mainloop()
