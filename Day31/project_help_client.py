from __future__ import annotations

import json
import queue
import threading
import uuid
from pathlib import Path
from tkinter import END, BOTH, LEFT, RIGHT, TOP, X, Y, BooleanVar, StringVar, Tk, Toplevel
from tkinter import ttk
from tkinter.scrolledtext import ScrolledText
from typing import Any

import requests


class ProjectHelpClient(Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Day31 Project Help Client")
        self.geometry("1500x920")
        self.minsize(1200, 760)

        self.session = requests.Session()
        self.result_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.request_thread: threading.Thread | None = None
        self.history: list[dict[str, str]] = []
        self.last_raw_response: Any = None

        self.base_url_var = StringVar(value="http://127.0.0.1:8000")
        self.timeout_var = StringVar(value="60")
        self.token_var = StringVar()
        self.provider_id_var = StringVar()
        self.model_var = StringVar(value="gpt-4o-mini")
        self.conversation_id_var = StringVar(value=str(uuid.uuid4()))
        self.branch_id_var = StringVar(value="main")
        self.task_id_var = StringVar()
        self.project_id_var = StringVar(value="aspia")
        self.project_root_var = StringVar()
        self.index_dir_var = StringVar()
        self.include_history_var = BooleanVar(value=True)
        self.require_json_var = BooleanVar(value=False)
        self.show_task_transition_var = BooleanVar(value=True)

        self._build_layout()
        self.after(150, self._poll_queue)

    def _build_layout(self) -> None:
        root = ttk.Frame(self, padding=10)
        root.pack(fill=BOTH, expand=True)

        root.columnconfigure(0, weight=0)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(0, weight=1)

        sidebar = ttk.Frame(root, padding=(0, 0, 10, 0))
        sidebar.grid(row=0, column=0, sticky="ns")
        main = ttk.Frame(root)
        main.grid(row=0, column=1, sticky="nsew")
        main.columnconfigure(0, weight=1)
        main.rowconfigure(1, weight=1)

        self._build_sidebar(sidebar)
        self._build_main(main)

    def _build_sidebar(self, parent: ttk.Frame) -> None:
        sections = [
            ("Connection", [
                ("Base URL", self.base_url_var),
                ("Timeout (sec)", self.timeout_var),
                ("Bearer token", self.token_var),
                ("Provider ID", self.provider_id_var),
                ("Model", self.model_var),
            ]),
            ("Conversation", [
                ("Conversation ID", self.conversation_id_var),
                ("Branch ID", self.branch_id_var),
                ("Task ID", self.task_id_var),
            ]),
            ("Project", [
                ("Project ID", self.project_id_var),
                ("Project root", self.project_root_var),
                ("Index dir", self.index_dir_var),
            ]),
        ]

        row = 0
        for title, fields in sections:
            frame = ttk.LabelFrame(parent, text=title, padding=10)
            frame.grid(row=row, column=0, sticky="ew", pady=(0, 10))
            frame.columnconfigure(0, weight=1)
            inner_row = 0
            for label, variable in fields:
                ttk.Label(frame, text=label).grid(row=inner_row, column=0, sticky="w")
                inner_row += 1
                ttk.Entry(frame, textvariable=variable, width=42).grid(row=inner_row, column=0, sticky="ew", pady=(0, 8))
                inner_row += 1
            row += 1

        options = ttk.LabelFrame(parent, text="Options", padding=10)
        options.grid(row=row, column=0, sticky="ew", pady=(0, 10))
        ttk.Checkbutton(options, text="Include history", variable=self.include_history_var).pack(anchor="w")
        ttk.Checkbutton(options, text="Require JSON", variable=self.require_json_var).pack(anchor="w")
        ttk.Checkbutton(
            options,
            text="Show task transitions in chat",
            variable=self.show_task_transition_var,
        ).pack(anchor="w")
        row += 1

        buttons = ttk.LabelFrame(parent, text="Actions", padding=10)
        buttons.grid(row=row, column=0, sticky="ew")
        ttk.Button(buttons, text="Health", command=self.check_health).pack(fill=X, pady=2)
        ttk.Button(buttons, text="New conversation", command=self.new_conversation).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Clear chat", command=self.clear_chat).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Copy payload", command=self.copy_payload).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Show raw", command=self.show_raw).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Preset /help", command=lambda: self.set_message("/help")).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Preset /mode", command=lambda: self.set_message("/mode")).pack(fill=X, pady=2)
        ttk.Button(buttons, text="Preset /exit", command=lambda: self.set_message("/exit")).pack(fill=X, pady=2)

    def _build_main(self, parent: ttk.Frame) -> None:
        top = ttk.Frame(parent)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        top.columnconfigure(0, weight=1)

        self.status_label = ttk.Label(
            top,
            text="Status: ready",
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, sticky="ew")

        panes = ttk.Panedwindow(parent, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew")

        chat_frame = ttk.Frame(panes, padding=(0, 0, 10, 0))
        info_frame = ttk.Frame(panes)
        panes.add(chat_frame, weight=3)
        panes.add(info_frame, weight=2)

        chat_frame.columnconfigure(0, weight=1)
        chat_frame.rowconfigure(0, weight=1)

        self.chat_box = ScrolledText(chat_frame, wrap="word", height=30)
        self.chat_box.grid(row=0, column=0, sticky="nsew")
        self.chat_box.configure(state="disabled")

        composer = ttk.Frame(chat_frame, padding=(0, 10, 0, 0))
        composer.grid(row=1, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)

        self.message_input = ScrolledText(composer, wrap="word", height=10)
        self.message_input.grid(row=0, column=0, columnspan=2, sticky="ew")
        ttk.Button(composer, text="Send", command=self.send_message).grid(row=1, column=1, sticky="e", pady=(8, 0))

        info_frame.columnconfigure(0, weight=1)
        info_frame.rowconfigure(1, weight=1)

        ttk.Label(info_frame, text="Service Info").grid(row=0, column=0, sticky="w")
        self.info_box = ScrolledText(info_frame, wrap="word", height=30)
        self.info_box.grid(row=1, column=0, sticky="nsew")
        self.info_box.configure(state="normal")
        self.info_box.insert("1.0", "Send a request to inspect response metadata, sources, and MCP usage.")
        self.info_box.configure(state="disabled")

    def set_status(self, text: str) -> None:
        self.status_label.config(text=f"Status: {text}")

    def set_message(self, text: str) -> None:
        self.message_input.delete("1.0", END)
        self.message_input.insert("1.0", text)

    def append_chat(self, role: str, text: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert(END, f"{role}\n{text}\n\n")
        self.chat_box.see(END)
        self.chat_box.configure(state="disabled")

    def _set_info(self, text: str) -> None:
        self.info_box.configure(state="normal")
        self.info_box.delete("1.0", END)
        self.info_box.insert("1.0", text)
        self.info_box.configure(state="disabled")

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        token = self.token_var.get().strip()
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    def new_conversation(self) -> None:
        self.conversation_id_var.set(str(uuid.uuid4()))
        self.history.clear()
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", END)
        self.chat_box.configure(state="disabled")
        self._set_info("New conversation created.")
        self.set_status("new conversation created")

    def clear_chat(self) -> None:
        self.history.clear()
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", END)
        self.chat_box.configure(state="disabled")
        self.last_raw_response = None
        self._set_info("Chat cleared.")
        self.set_status("chat cleared")

    def build_payload(self, user_message: str) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if self.include_history_var.get():
            messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})

        payload: dict[str, Any] = {
            "conversation_id": self.conversation_id_var.get().strip() or str(uuid.uuid4()),
            "branch_id": self.branch_id_var.get().strip() or "main",
            "task_id": self.task_id_var.get().strip() or None,
            "model": self.model_var.get().strip(),
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 800,
            "top_p": 1.0,
            "show_task_transition_in_chat": self.show_task_transition_var.get(),
            "project": {
                "id": self.project_id_var.get().strip() or None,
                "root": self.project_root_var.get().strip() or None,
                "index_dir": self.index_dir_var.get().strip() or None,
            },
        }
        if self.provider_id_var.get().strip():
            payload["provider_id"] = self.provider_id_var.get().strip()
        if self.require_json_var.get():
            payload["validation"] = {"require_json": True}
        return payload

    def copy_payload(self) -> None:
        message = self.message_input.get("1.0", END).strip() or "/help Какая структура проекта?"
        payload = self.build_payload(message)
        self.clipboard_clear()
        self.clipboard_append(json.dumps(payload, ensure_ascii=False, indent=2))
        self.set_status("payload copied")

    def show_raw(self) -> None:
        if self.last_raw_response is None:
            self.set_status("raw response is empty")
            return
        popup = Toplevel(self)
        popup.title("Raw response")
        popup.geometry("900x640")
        box = ScrolledText(popup, wrap="word")
        box.pack(fill=BOTH, expand=True)
        if isinstance(self.last_raw_response, (dict, list)):
            box.insert("1.0", json.dumps(self.last_raw_response, ensure_ascii=False, indent=2))
        else:
            box.insert("1.0", str(self.last_raw_response))
        box.configure(state="disabled")

    def check_health(self) -> None:
        self._run_request(
            name="health",
            method="GET",
            url=self._join_url("/health"),
            json_payload=None,
            headers=self._auth_headers(),
            user_message=None,
        )

    def send_message(self) -> None:
        if self.request_thread and self.request_thread.is_alive():
            self.set_status("wait for the current request")
            return
        message = self.message_input.get("1.0", END).strip()
        if not message:
            self.set_status("enter a message")
            return
        if not self.model_var.get().strip():
            self.set_status("enter a model")
            return
        payload = self.build_payload(message)
        self.conversation_id_var.set(str(payload["conversation_id"]))
        self.append_chat("user", message)
        self.message_input.delete("1.0", END)
        self.set_status("sending request")
        self._run_request(
            name="generate",
            method="POST",
            url=self._join_url("/generate"),
            json_payload=payload,
            headers=self._auth_headers(),
            user_message=message,
        )

    def _run_request(
        self,
        *,
        name: str,
        method: str,
        url: str,
        json_payload: dict[str, Any] | None,
        headers: dict[str, str],
        user_message: str | None,
    ) -> None:
        self.request_thread = threading.Thread(
            target=self._request_worker,
            kwargs={
                "name": name,
                "method": method,
                "url": url,
                "json_payload": json_payload,
                "headers": headers,
                "user_message": user_message,
            },
            daemon=True,
        )
        self.request_thread.start()

    def _request_worker(
        self,
        *,
        name: str,
        method: str,
        url: str,
        json_payload: dict[str, Any] | None,
        headers: dict[str, str],
        user_message: str | None,
    ) -> None:
        try:
            timeout = float(self.timeout_var.get().strip() or "60")
        except ValueError:
            timeout = 60.0

        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, timeout=timeout)
            else:
                response = self.session.post(url, json=json_payload, headers=headers, timeout=timeout)

            content_type = response.headers.get("content-type", "")
            if "application/json" in content_type.lower():
                body: Any = response.json()
            else:
                body = response.text

            self.result_queue.put(
                {
                    "ok": response.ok,
                    "status_code": response.status_code,
                    "name": name,
                    "body": body,
                    "user_message": user_message,
                }
            )
        except Exception as exc:  # noqa: BLE001
            self.result_queue.put(
                {
                    "ok": False,
                    "status_code": None,
                    "name": name,
                    "body": str(exc),
                    "user_message": user_message,
                }
            )

    def _poll_queue(self) -> None:
        try:
            while True:
                result = self.result_queue.get_nowait()
                self._handle_request_result(result)
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _handle_request_result(self, result: dict[str, Any]) -> None:
        self.last_raw_response = result["body"]
        if result["name"] == "health":
            self._set_info(self._format_body(result["body"]))
            self.set_status("health loaded" if result["ok"] else "health failed")
            return

        if not result["ok"]:
            self.append_chat("error", self._format_error(result))
            self._set_info(self._format_body(result["body"]))
            self.set_status("request failed")
            return

        body = result["body"]
        if isinstance(body, dict):
            assistant_text = str(body.get("content") or "")
            if assistant_text:
                self.append_chat("assistant", assistant_text)
                if result["user_message"] is not None:
                    self.history.append({"role": "user", "content": str(result["user_message"])})
                    self.history.append({"role": "assistant", "content": assistant_text})
            self._set_info(self._summarize_response(body))
        else:
            self.append_chat("assistant", str(body))
            self._set_info(str(body))
        self.set_status(f"response received ({result['status_code']})")

    def _summarize_response(self, body: dict[str, Any]) -> str:
        usage = body.get("usage") if isinstance(body.get("usage"), dict) else {}
        lines = [
            f"request_id: {body.get('request_id')}",
            f"active_mode: {body.get('active_mode')}",
            f"project_id: {body.get('project_id')}",
            f"project_help_route: {body.get('project_help_route')}",
            f"latency_ms: {body.get('latency_ms')}",
            f"provider_id: {body.get('provider_id')}",
            f"model: {body.get('model')}",
            f"rag_used: {body.get('rag_used')}",
            f"rag_chunks_used: {body.get('rag_chunks_used')}",
            f"mcp_used: {body.get('mcp_used')}",
            f"mcp_tool_calls: {body.get('mcp_tool_calls')}",
            f"tokens_total: {usage.get('total_tokens')}",
            "",
            "sources:",
        ]
        sources = body.get("sources") if isinstance(body.get("sources"), list) else []
        if sources:
            for source in sources:
                lines.append(
                    f"- {source.get('source')} | {source.get('section')} | {source.get('chunk_id')}"
                )
        else:
            lines.append("- none")
        return "\n".join(lines)

    def _format_error(self, result: dict[str, Any]) -> str:
        return f"HTTP {result.get('status_code')}\n{self._format_body(result.get('body'))}"

    def _format_body(self, body: Any) -> str:
        if isinstance(body, (dict, list)):
            return json.dumps(body, ensure_ascii=False, indent=2)
        return str(body)

    def _join_url(self, path: str) -> str:
        return self.base_url_var.get().rstrip("/") + path


if __name__ == "__main__":
    app = ProjectHelpClient()
    app.mainloop()
