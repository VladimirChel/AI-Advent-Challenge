import json
import queue
import threading
import uuid
from datetime import datetime
from typing import Any, Dict, Optional

import customtkinter as ctk
import requests
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


class JsonViewer(ctk.CTkToplevel):
    def __init__(self, master, title: str, data: Any):
        super().__init__(master)
        self.title(title)
        self.geometry("900x680")
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)

        box = ctk.CTkTextbox(self, wrap="none")
        box.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)
        try:
            rendered = json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            rendered = str(data)
        box.insert("1.0", rendered)
        box.configure(state="disabled")


class HttpClient:
    def __init__(self, app: "GatewayApp"):
        self.app = app

    def request(self, method: str, path: str, **kwargs):
        base_url = self.app.base_url_var.get().strip().rstrip("/")
        timeout = float(self.app.timeout_var.get().strip() or "60")
        url = f"{base_url}{path}"
        headers = kwargs.pop("headers", {}) or {}
        if "json" in kwargs:
            headers.setdefault("Content-Type", "application/json")
        return requests.request(method=method, url=url, headers=headers, timeout=timeout, **kwargs)


class GatewayApp(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LLM Gateway Tester v2 (simple)")
        self.geometry("1500x960")
        self.minsize(1220, 820)

        self.client = HttpClient(self)
        self.ui_queue: queue.Queue = queue.Queue()
        self.last_response: Optional[Dict[str, Any]] = None

        self._init_vars()
        self._build_layout()
        self.after(100, self._drain_ui_queue)
        self._set_status("Готово")
        self._append_log("Упрощённая версия запущена")

    def _init_vars(self):
        self.base_url_var = ctk.StringVar(value="http://localhost:8000")
        self.timeout_var = ctk.StringVar(value="60")
        self.token_var = ctk.StringVar(value="")
        self.model_var = ctk.StringVar(value="")
        self.conversation_id_var = ctk.StringVar(value="")
        self.branch_id_var = ctk.StringVar(value="main")
        self.memory_strategy_var = ctk.StringVar(value="hybrid")
        self.use_memory_var = ctk.BooleanVar(value=True)
        self.history_limit_var = ctk.StringVar(value="20")
        self.temperature_var = ctk.StringVar(value="0.2")
        self.max_tokens_var = ctk.StringVar(value="500")

    def _build_layout(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self):
        sidebar = ctk.CTkFrame(self, width=330, corner_radius=0)
        sidebar.grid(row=0, column=0, sticky="nsew")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(99, weight=1)

        row = 0
        ctk.CTkLabel(
            sidebar,
            text="LLM Gateway Tester",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=16, pady=(16, 6))
        row += 1
        ctk.CTkLabel(
            sidebar,
            text="Только основные настройки",
            text_color=("gray35", "gray70"),
        ).grid(row=row, column=0, sticky="w", padx=16, pady=(0, 10))
        row += 1

        row = self._entry(sidebar, row, "Base URL", self.base_url_var)
        row = self._entry(sidebar, row, "Timeout (sec)", self.timeout_var)
        row = self._entry(sidebar, row, "Bearer token (optional)", self.token_var, show="*")
        row = self._entry(sidebar, row, "Model", self.model_var)
        row = self._entry(sidebar, row, "Conversation ID", self.conversation_id_var)
        row = self._entry(sidebar, row, "Branch ID", self.branch_id_var)

        ctk.CTkLabel(sidebar, text="Стратегия контекста").grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        ctk.CTkComboBox(sidebar, values=MEMORY_STRATEGIES, variable=self.memory_strategy_var).grid(
            row=row, column=0, sticky="ew", padx=16, pady=(0, 8)
        )
        row += 1

        ctk.CTkCheckBox(sidebar, text="Use memory", variable=self.use_memory_var).grid(
            row=row, column=0, sticky="w", padx=16, pady=(0, 8)
        )
        row += 1

        row = self._entry(sidebar, row, "History limit", self.history_limit_var)
        row = self._entry(sidebar, row, "Temperature", self.temperature_var)
        row = self._entry(sidebar, row, "Max tokens", self.max_tokens_var)

        actions = ctk.CTkFrame(sidebar)
        actions.grid(row=row, column=0, sticky="ew", padx=12, pady=8)
        actions.grid_columnconfigure((0, 1), weight=1)
        ctk.CTkButton(actions, text="Health", command=self.fetch_health).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(actions, text="Models", command=self.fetch_models).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(actions, text="New conversation", command=self.new_conversation).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(actions, text="Raw response", command=self.show_last_response).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        row += 1

        appearance = ctk.CTkOptionMenu(sidebar, values=["System", "Light", "Dark"], command=ctk.set_appearance_mode)
        appearance.set("System")
        ctk.CTkLabel(sidebar, text="Appearance").grid(row=row, column=0, sticky="w", padx=16, pady=(6, 0))
        row += 1
        appearance.grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))

        self.status_label = ctk.CTkLabel(sidebar, text="", justify="left", wraplength=290)
        self.status_label.grid(row=99, column=0, sticky="sw", padx=16, pady=16)

    def _build_main(self):
        main = ctk.CTkFrame(self)
        main.grid(row=0, column=1, sticky="nsew", padx=12, pady=12)
        main.grid_columnconfigure(0, weight=3)
        main.grid_columnconfigure(1, weight=2)
        main.grid_rowconfigure(0, weight=3)
        main.grid_rowconfigure(1, weight=2)

        self._build_chat(main)
        self._build_side_tabs(main)
        self._build_bottom(main)

    def _build_chat(self, parent):
        frame = ctk.CTkFrame(parent)
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))
        frame.grid_columnconfigure(0, weight=1)
        frame.grid_rowconfigure(1, weight=1)

        header = ctk.CTkFrame(frame, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=12, pady=(10, 6))
        header.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(header, text="Chat", font=ctk.CTkFont(size=22, weight="bold")).grid(row=0, column=0, sticky="w")
        self.chat_meta_label = ctk.CTkLabel(header, text="conversation: — | branch: main")
        self.chat_meta_label.grid(row=0, column=1, sticky="e")

        self.chat_box = ctk.CTkTextbox(frame, wrap="word")
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=12)
        self.chat_box.configure(state="disabled")

        composer = ctk.CTkFrame(frame)
        composer.grid(row=2, column=0, sticky="ew", padx=12, pady=10)
        composer.grid_columnconfigure(0, weight=1)
        self.prompt_box = ctk.CTkTextbox(composer, height=120, wrap="word")
        self.prompt_box.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        self.prompt_box.insert("1.0", "Напиши короткий тестовый ответ")

        buttons = ctk.CTkFrame(frame, fg_color="transparent")
        buttons.grid(row=3, column=0, sticky="ew", padx=12, pady=(0, 12))
        buttons.grid_columnconfigure((0, 1, 2, 3), weight=1)
        self.send_button = ctk.CTkButton(buttons, text="Send", height=40, command=self.generate)
        self.send_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(buttons, text="Load messages", command=self.fetch_messages).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(buttons, text="Summary", command=self.fetch_summary).grid(row=0, column=2, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(buttons, text="Facts", command=self.fetch_facts).grid(row=0, column=3, padx=4, pady=4, sticky="ew")

    def _build_side_tabs(self, parent):
        tabs = ctk.CTkTabview(parent)
        tabs.grid(row=0, column=1, sticky="nsew", pady=(0, 8))
        tabs.add("Response")
        tabs.add("Log")

        self.response_box = ctk.CTkTextbox(tabs.tab("Response"), wrap="word")
        self.response_box.pack(fill="both", expand=True, padx=10, pady=10)

        self.log_box = ctk.CTkTextbox(tabs.tab("Log"), wrap="word")
        self.log_box.pack(fill="both", expand=True, padx=10, pady=10)

    def _build_bottom(self, parent):
        bottom = ctk.CTkTabview(parent)
        bottom.grid(row=1, column=0, columnspan=2, sticky="nsew")
        bottom.add("Messages")
        bottom.add("Summary")
        bottom.add("Facts")

        self.messages_box = ctk.CTkTextbox(bottom.tab("Messages"), wrap="word")
        self.messages_box.pack(fill="both", expand=True, padx=10, pady=10)

        self.summary_box = ctk.CTkTextbox(bottom.tab("Summary"), wrap="word")
        self.summary_box.pack(fill="both", expand=True, padx=10, pady=10)

        self.facts_box = ctk.CTkTextbox(bottom.tab("Facts"), wrap="word")
        self.facts_box.pack(fill="both", expand=True, padx=10, pady=10)

    def _entry(self, parent, row: int, label: str, var: ctk.StringVar, show: Optional[str] = None) -> int:
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=16)
        row += 1
        ctk.CTkEntry(parent, textvariable=var, show=show).grid(row=row, column=0, sticky="ew", padx=16, pady=(0, 8))
        return row + 1

    def _append_log(self, text: str):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log_box.insert("end", f"[{stamp}] {text}\n")
        self.log_box.see("end")

    def _set_status(self, text: str):
        self.status_label.configure(text=text)

    def _drain_ui_queue(self):
        while True:
            try:
                fn = self.ui_queue.get_nowait()
            except queue.Empty:
                break
            fn()
        self.after(100, self._drain_ui_queue)

    def _run_async(self, label: str, func, on_success=None, on_error=None):
        self._set_status(f"Выполняется: {label}")
        self._append_log(f"Старт: {label}")

        def worker():
            try:
                response = func()
                self.ui_queue.put(lambda: self._handle_response(label, response, on_success))
            except Exception as exc:
                self.ui_queue.put(lambda: self._handle_exception(label, exc, on_error))

        threading.Thread(target=worker, daemon=True).start()

    def _handle_response(self, label: str, response: requests.Response, on_success=None):
        try:
            body = response.json()
        except Exception:
            body = {"raw_text": response.text}

        self.last_response = {
            "status_code": response.status_code,
            "headers": dict(response.headers),
            "body": body,
        }
        self.response_box.delete("1.0", "end")
        self.response_box.insert("1.0", json.dumps(self.last_response, ensure_ascii=False, indent=2))

        if response.ok:
            self._set_status(f"Готово: {label} ({response.status_code})")
            self._append_log(f"Успех: {label} ({response.status_code})")
            if on_success:
                on_success(body)
        else:
            self._set_status(f"Ошибка: {label} ({response.status_code})")
            self._append_log(f"Ошибка HTTP: {label} ({response.status_code})")
            messagebox.showerror("HTTP error", f"{label}: HTTP {response.status_code}")

    def _handle_exception(self, label: str, exc: Exception, on_error=None):
        self._set_status(f"Ошибка: {label}")
        self._append_log(f"Исключение: {label}: {exc}")
        if on_error:
            on_error(exc)
        else:
            messagebox.showerror("Exception", f"{label}: {exc}")

    def _headers(self) -> Dict[str, str]:
        headers: Dict[str, str] = {}
        token = self.token_var.get().strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def _conversation_id(self) -> str:
        value = self.conversation_id_var.get().strip()
        if not value:
            raise ValueError("Conversation ID is required")
        return value

    def _branch_id(self) -> str:
        return self.branch_id_var.get().strip() or "main"

    def _update_chat_header(self):
        conv = self.conversation_id_var.get().strip() or "—"
        branch = self._branch_id()
        self.chat_meta_label.configure(text=f"conversation: {conv} | branch: {branch}")

    def _chat_append(self, role: str, content: str):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"\n[{role.upper()}]\n{content.strip()}\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def new_conversation(self):
        conversation_id = f"conv-{uuid.uuid4().hex[:12]}"
        self.conversation_id_var.set(conversation_id)
        self.branch_id_var.set("main")
        self._update_chat_header()
        self._append_log(f"Создан conversation_id: {conversation_id}")
        self._set_status(f"Новый conversation_id: {conversation_id}")

    def _build_payload(self, prompt: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model_var.get().strip() or None,
            "messages": [{"role": "user", "content": prompt}],
            "conversation_id": self.conversation_id_var.get().strip() or None,
            "branch_id": self._branch_id(),
            "use_memory": self.use_memory_var.get(),
            "memory_strategy": self.memory_strategy_var.get(),
            "history_limit": int(self.history_limit_var.get()),
            "temperature": float(self.temperature_var.get()),
            "max_tokens": int(self.max_tokens_var.get()),
        }
        return {k: v for k, v in payload.items() if v is not None}

    def generate(self):
        prompt = self.prompt_box.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Empty prompt", "Введите текст сообщения")
            return

        if not self.conversation_id_var.get().strip():
            self.new_conversation()

        try:
            payload = self._build_payload(prompt)
            headers = self._headers()
        except Exception as exc:
            messagebox.showerror("Payload error", str(exc))
            return

        self.send_button.configure(state="disabled")
        self._chat_append("user", prompt)
        self._update_chat_header()

        def done(data):
            self.send_button.configure(state="normal")
            conversation_id = data.get("conversation_id")
            branch_id = data.get("branch_id")
            if conversation_id:
                self.conversation_id_var.set(conversation_id)
            if branch_id:
                self.branch_id_var.set(branch_id)
            self._update_chat_header()
            self._chat_append("assistant", data.get("content", ""))
            self.prompt_box.delete("1.0", "end")
            self.fetch_summary(silent=True)
            self.fetch_facts(silent=True)

        def fail(exc):
            self.send_button.configure(state="normal")
            messagebox.showerror("Generate error", str(exc))

        self._run_async("generate", lambda: self.client.request("POST", "/generate", json=payload, headers=headers), done, fail)

    def fetch_health(self):
        self._run_async("health", lambda: self.client.request("GET", "/health", headers=self._headers()))

    def fetch_models(self):
        def done(data):
            models = [item.get("id") for item in data.get("data", []) if item.get("id")]
            if models and not self.model_var.get().strip():
                self.model_var.set(models[0])
            self._append_log(f"Загружено моделей: {len(models)}")

        self._run_async("models", lambda: self.client.request("GET", "/models", headers=self._headers()), done)

    def fetch_messages(self):
        try:
            conversation_id = self._conversation_id()
            branch_id = self._branch_id()
        except Exception as exc:
            messagebox.showerror("Input error", str(exc))
            return

        def done(data):
            parts = []
            for item in data.get("messages", []):
                parts.append(
                    f"seq={item.get('seq_no')} | role={item.get('role')}\n"
                    f"uuid={item.get('message_uuid')}\n"
                    f"content:\n{item.get('content', '')}\n{'=' * 80}"
                )
            self.messages_box.delete("1.0", "end")
            self.messages_box.insert("1.0", "\n".join(parts) if parts else "Нет сообщений")

        self._run_async(
            "messages",
            lambda: self.client.request(
                "GET",
                f"/conversations/{conversation_id}/messages",
                params={"branch_id": branch_id, "limit": 50},
                headers=self._headers(),
            ),
            done,
        )

    def fetch_summary(self, silent: bool = False):
        try:
            conversation_id = self._conversation_id()
            branch_id = self._branch_id()
        except Exception as exc:
            if not silent:
                messagebox.showerror("Input error", str(exc))
            return

        def done(data):
            self.summary_box.delete("1.0", "end")
            self.summary_box.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

        self._run_async(
            "summary",
            lambda: self.client.request(
                "GET",
                f"/conversations/{conversation_id}/summary",
                params={"branch_id": branch_id},
                headers=self._headers(),
            ),
            done,
        )

    def fetch_facts(self, silent: bool = False):
        try:
            conversation_id = self._conversation_id()
            branch_id = self._branch_id()
        except Exception as exc:
            if not silent:
                messagebox.showerror("Input error", str(exc))
            return

        def done(data):
            self.facts_box.delete("1.0", "end")
            self.facts_box.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

        self._run_async(
            "facts",
            lambda: self.client.request(
                "GET",
                f"/conversations/{conversation_id}/facts",
                params={"branch_id": branch_id},
                headers=self._headers(),
            ),
            done,
        )

    def show_last_response(self):
        if not self.last_response:
            messagebox.showinfo("Raw response", "Пока нет ответа сервера")
            return
        JsonViewer(self, "Raw response", self.last_response)


if __name__ == "__main__":
    app = GatewayApp()
    app.mainloop()
