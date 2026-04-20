import json
from pathlib import Path
import queue
import threading
import tkinter as tk
import uuid
from datetime import datetime
from typing import Any

import customtkinter as ctk
import requests


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class LLMTesterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM Assistant Tester")
        self.geometry("1480x900")
        self.minsize(1280, 780)

        self.result_queue: queue.Queue[dict[str, Any]] = queue.Queue()
        self.request_thread: threading.Thread | None = None
        self.session = requests.Session()

        self.base_url_var = ctk.StringVar(value="http://127.0.0.1:8000")
        self.theme_var = ctk.StringVar(value="System")
        self.timeout_var = ctk.StringVar(value="60")
        self.email_var = ctk.StringVar()
        self.password_var = ctk.StringVar()
        self.register_email_var = ctk.StringVar()
        self.register_password_var = ctk.StringVar()
        self.confirm_password_var = ctk.StringVar()
        self.model_var = ctk.StringVar(value="openai/gpt-4o-mini")
        self.model_values: list[str] = ["openai/gpt-4o-mini"]
        self.branch_id_var = ctk.StringVar(value="main")
        self.task_id_var = ctk.StringVar()
        self.conversation_id_var = ctk.StringVar(value=str(uuid.uuid4()))
        self.token_preview_var = ctk.StringVar(value="not authenticated")
        self.include_history_var = ctk.BooleanVar(value=True)
        self.require_json_var = ctk.BooleanVar(value=False)
        self.show_task_transition_in_chat_var = ctk.BooleanVar(value=True)
        self.enable_mcp_var = ctk.BooleanVar(value=False)
        self.enable_rag_var = ctk.BooleanVar(value=False)

        self.access_token: str | None = None
        self.current_user: dict[str, Any] | None = None
        self.history: list[dict[str, str]] = []
        self.chat_transcript: list[dict[str, str]] = []
        self.last_raw_response: Any = None
        self.default_mcp_server_scripts = self._load_default_mcp_server_scripts()
        self.session_state_path = Path(__file__).resolve().with_name("llm_gui_client_session.json")
        self._session_restore_in_progress = False
        self._session_save_after_id: str | None = None

        self._build_layout()
        self._bind_session_persistence_hooks()
        self._load_session_state()
        self.protocol("WM_DELETE_WINDOW", self._on_close)
        self.after(150, self._poll_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=360, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        self.sidebar.grid_columnconfigure(0, weight=1)
        self.sidebar.grid_rowconfigure(1, weight=1)

        self.main = ctk.CTkFrame(self, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        self._build_sidebar()
        self._build_main()

    def _build_sidebar(self) -> None:
        header = ctk.CTkFrame(self.sidebar)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="LLM Assistant Tester",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=14, pady=(14, 4), sticky="ew")

        ctk.CTkLabel(
            header,
            text="GUI client for auth, chat requests, and MCP visibility.",
            justify="left",
            wraplength=300,
            anchor="w",
        ).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")

        content = ctk.CTkScrollableFrame(self.sidebar)
        content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        content.grid_columnconfigure(0, weight=1)

        row = 0
        connection_box = ctk.CTkFrame(content)
        connection_box.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        connection_box.grid_columnconfigure((0, 1), weight=1)
        row += 1

        self.health_button = ctk.CTkButton(connection_box, text="Health", command=self.check_health)
        self.health_button.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.me_button = ctk.CTkButton(connection_box, text="Me", command=self.fetch_me)
        self.me_button.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        auth_tabs = ctk.CTkTabview(content)
        auth_tabs.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        auth_tabs.add("Login")
        auth_tabs.add("Register")
        row += 1

        login_tab = auth_tabs.tab("Login")
        login_tab.grid_columnconfigure(0, weight=1)
        self._add_entry(login_tab, "Email", self.email_var, 0)
        self._add_entry(login_tab, "Password", self.password_var, 2, show="*")
        self.login_button = ctk.CTkButton(login_tab, text="Login", command=self.login)
        self.login_button.grid(row=4, column=0, padx=8, pady=(4, 10), sticky="ew")

        register_tab = auth_tabs.tab("Register")
        register_tab.grid_columnconfigure(0, weight=1)
        self._add_entry(register_tab, "Email", self.register_email_var, 0)
        self._add_entry(register_tab, "Password", self.register_password_var, 2, show="*")
        self._add_entry(register_tab, "Confirm password", self.confirm_password_var, 4, show="*")
        self.register_button = ctk.CTkButton(register_tab, text="Create account", command=self.register)
        self.register_button.grid(row=6, column=0, padx=8, pady=(4, 10), sticky="ew")

        token_frame = ctk.CTkFrame(content)
        token_frame.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        token_frame.grid_columnconfigure(0, weight=1)
        row += 1

        ctk.CTkLabel(
            token_frame,
            text="Auth State",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        self.token_label = ctk.CTkLabel(
            token_frame,
            textvariable=self.token_preview_var,
            justify="left",
            wraplength=300,
            anchor="w",
        )
        self.token_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        token_buttons = ctk.CTkFrame(token_frame, fg_color="transparent")
        token_buttons.grid(row=2, column=0, padx=8, pady=(0, 8), sticky="ew")
        token_buttons.grid_columnconfigure((0, 1), weight=1)

        self.copy_token_button = ctk.CTkButton(token_buttons, text="Copy token", command=self.copy_token)
        self.copy_token_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.logout_button = ctk.CTkButton(token_buttons, text="Logout", command=self.logout)
        self.logout_button.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        context_box = ctk.CTkFrame(content)
        context_box.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        context_box.grid_columnconfigure(0, weight=1)
        row += 1

        ctk.CTkLabel(
            context_box,
            text="Conversation Context",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        subrow = 1
        subrow = self._add_entry(context_box, "Conversation ID", self.conversation_id_var, subrow)
        subrow = self._add_entry(context_box, "Branch ID", self.branch_id_var, subrow)
        subrow = self._add_entry(context_box, "Task ID (optional)", self.task_id_var, subrow)

        context_buttons = ctk.CTkFrame(context_box, fg_color="transparent")
        context_buttons.grid(row=subrow, column=0, padx=8, pady=(0, 8), sticky="ew")
        context_buttons.grid_columnconfigure((0, 1), weight=1)

        self.new_conv_button = ctk.CTkButton(context_buttons, text="New conversation", command=self.new_conversation)
        self.new_conv_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.clear_chat_button = ctk.CTkButton(context_buttons, text="Clear chat", command=self.clear_chat)
        self.clear_chat_button.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

        status_box = ctk.CTkFrame(content)
        status_box.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        status_box.grid_columnconfigure(0, weight=1)

        self.status_label = ctk.CTkLabel(
            status_box,
            text="Status: ready",
            justify="left",
            wraplength=300,
            anchor="w",
        )
        self.status_label.grid(row=0, column=0, padx=12, pady=12, sticky="ew")

    def _build_main(self) -> None:
        header = ctk.CTkFrame(self.main)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        header.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            header,
            text="Chat / MCP Inspector",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")
        self.tabs = ctk.CTkTabview(self.main)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        self.tabs.add("Chat")
        self.tabs.add("Settings")

        self._build_chat_tab()
        self._build_settings_tab()

    def _add_entry(
        self,
        parent: Any,
        label_text: str,
        variable: ctk.StringVar,
        row: int,
        *,
        show: str | None = None,
    ) -> int:
        ctk.CTkLabel(parent, text=label_text, anchor="w").grid(
            row=row, column=0, padx=8, pady=(8, 4), sticky="ew"
        )
        row += 1
        entry = ctk.CTkEntry(parent, textvariable=variable, show=show or "")
        entry.grid(row=row, column=0, padx=8, pady=(0, 4), sticky="ew")
        row += 1
        return row

    def _build_chat_tab(self) -> None:
        chat_tab = self.tabs.tab("Chat")
        chat_tab.grid_columnconfigure(0, weight=3)
        chat_tab.grid_columnconfigure(1, weight=2)
        chat_tab.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(chat_tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        left.grid_columnconfigure(0, weight=1)
        left.grid_rowconfigure(0, weight=1)

        self.chat_box = ctk.CTkTextbox(left, wrap="word")
        self.chat_box.grid(row=0, column=0, sticky="nsew", padx=12, pady=(12, 8))
        self.chat_box.configure(state="disabled")

        bottom = ctk.CTkFrame(left)
        bottom.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 12))
        bottom.grid_columnconfigure(0, weight=1)

        self.message_input = ctk.CTkTextbox(bottom, height=150, wrap="word")
        self.message_input.grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(12, 8))
        self.message_input.bind("<Control-Return>", self._send_hotkey)
        self.message_input.bind("<Command-Return>", self._send_hotkey)

        ctk.CTkLabel(bottom, text="Ctrl+Enter to send", anchor="w").grid(
            row=1, column=0, padx=12, pady=(0, 12), sticky="w"
        )

        self.copy_payload_button = ctk.CTkButton(bottom, text="Copy payload", height=40, command=self.copy_payload)
        self.copy_payload_button.grid(row=1, column=1, padx=(8, 0), pady=(0, 12), sticky="e")

        self.raw_button = ctk.CTkButton(bottom, text="Show raw", height=40, command=self.show_last_raw)
        self.raw_button.grid(row=1, column=2, padx=(8, 0), pady=(0, 12), sticky="e")

        self.send_button = ctk.CTkButton(bottom, text="Send", height=40, command=self.send_message)
        self.send_button.grid(row=1, column=3, padx=(8, 12), pady=(0, 12), sticky="e")

        right = ctk.CTkFrame(chat_tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(3, weight=1)
        right.grid_rowconfigure(5, weight=2)

        ctk.CTkLabel(
            right,
            text="MCP Runtime",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        self.mcp_summary_label = ctk.CTkLabel(
            right,
            text="MCP is idle. Send a request with MCP enabled to inspect connected servers and tools.",
            justify="left",
            wraplength=420,
            anchor="w",
        )
        self.mcp_summary_label.grid(row=1, column=0, padx=12, pady=(0, 8), sticky="ew")

        ctk.CTkLabel(right, text="Connected Servers", anchor="w").grid(
            row=2, column=0, padx=12, pady=(0, 4), sticky="ew"
        )

        self.mcp_servers_box = ctk.CTkTextbox(right, height=140, wrap="word")
        self.mcp_servers_box.grid(row=3, column=0, padx=12, pady=(0, 8), sticky="nsew")
        self.mcp_servers_box.configure(state="disabled")

        ctk.CTkLabel(right, text="Available Tools", anchor="w").grid(
            row=4, column=0, padx=12, pady=(0, 4), sticky="ew"
        )

        self.mcp_tools_box = ctk.CTkTextbox(right, wrap="word")
        self.mcp_tools_box.grid(row=5, column=0, padx=12, pady=(0, 12), sticky="nsew")
        self.mcp_tools_box.configure(state="disabled")

    def _build_settings_tab(self) -> None:
        settings_tab = self.tabs.tab("Settings")
        settings_tab.grid_columnconfigure((0, 1), weight=1)

        left = ctk.CTkFrame(settings_tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        left.grid_columnconfigure(0, weight=1)

        row = 0
        ctk.CTkLabel(
            left,
            text="Connection Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, padx=12, pady=(12, 6), sticky="ew")
        row += 1

        row = self._add_entry(left, "Base URL", self.base_url_var, row)
        row = self._add_entry(left, "Timeout (sec)", self.timeout_var, row)

        ctk.CTkLabel(left, text="Theme", anchor="w").grid(row=row, column=0, padx=8, pady=(8, 4), sticky="ew")
        row += 1

        ctk.CTkOptionMenu(
            left,
            variable=self.theme_var,
            values=["System", "Light", "Dark"],
            command=self._change_theme,
        ).grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")

        right = ctk.CTkFrame(settings_tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=0)
        right.grid_columnconfigure(0, weight=1)

        row = 0
        ctk.CTkLabel(
            right,
            text="Request Settings",
            font=ctk.CTkFont(size=18, weight="bold"),
            anchor="w",
        ).grid(row=row, column=0, padx=12, pady=(12, 6), sticky="ew")
        row += 1

        ctk.CTkLabel(right, text="Model", anchor="w").grid(
            row=row, column=0, padx=8, pady=(8, 4), sticky="ew"
        )
        row += 1

        model_row = ctk.CTkFrame(right, fg_color="transparent")
        model_row.grid(row=row, column=0, padx=8, pady=(0, 4), sticky="ew")
        model_row.grid_columnconfigure(0, weight=1)
        row += 1

        self.model_value_entry = ctk.CTkEntry(model_row, textvariable=self.model_var)
        self.model_value_entry.grid(row=0, column=0, padx=(0, 8), pady=0, sticky="ew")

        self.refresh_models_button = ctk.CTkButton(
            model_row,
            text="Refresh models",
            width=130,
            command=self.fetch_models,
        )
        self.refresh_models_button.grid(row=0, column=1, padx=0, pady=0, sticky="e")

        self.choose_model_button = ctk.CTkButton(
            right,
            text="Choose model",
            command=self.open_model_picker,
        )
        self.choose_model_button.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        row += 1

        ctk.CTkSwitch(right, text="Include history", variable=self.include_history_var).grid(
            row=row, column=0, padx=12, pady=(2, 6), sticky="w"
        )
        row += 1

        ctk.CTkSwitch(right, text="Require JSON response", variable=self.require_json_var).grid(
            row=row, column=0, padx=12, pady=(0, 6), sticky="w"
        )
        row += 1

        ctk.CTkSwitch(
            right,
            text="Show task transitions in chat",
            variable=self.show_task_transition_in_chat_var,
        ).grid(row=row, column=0, padx=12, pady=(0, 6), sticky="w")
        row += 1

        ctk.CTkSwitch(right, text="Enable MCP tools", variable=self.enable_mcp_var).grid(
            row=row, column=0, padx=12, pady=(0, 6), sticky="w"
        )
        row += 1

        ctk.CTkSwitch(right, text="Enable Day22 RAG", variable=self.enable_rag_var).grid(
            row=row, column=0, padx=12, pady=(0, 6), sticky="w"
        )
        row += 1

        ctk.CTkLabel(right, text="MCP servers (one script per line)", anchor="w").grid(
            row=row, column=0, padx=8, pady=(8, 4), sticky="ew"
        )
        row += 1

        self.mcp_servers_input = ctk.CTkTextbox(right, height=140, wrap="word")
        self.mcp_servers_input.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        self.mcp_servers_input.insert("1.0", "\n".join(self.default_mcp_server_scripts))

    def _change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value)
        self._schedule_session_save()

    def _send_hotkey(self, _event: Any) -> str:
        self.send_message()
        return "break"

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=f"Status: {text}")

    def append_chat(self, role: str, text: str) -> None:
        self.chat_transcript.append({"role": role, "content": text})
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"[{ts}] {role}\n{text}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")
        self._schedule_session_save()

    def _set_textbox(self, widget: ctk.CTkTextbox, text: str) -> None:
        widget.configure(state="normal")
        widget.delete("1.0", "end")
        widget.insert("1.0", text)
        widget.configure(state="disabled")

    def _load_default_mcp_server_scripts(self) -> list[str]:
        env_path = Path(__file__).resolve().with_name(".env")
        if not env_path.exists():
            return ["../Day16/server.py"]

        values: dict[str, str] = {}
        for raw_line in env_path.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()

        scripts_raw = values.get("MCP_SERVER_SCRIPTS", "")
        if scripts_raw:
            try:
                parsed = json.loads(scripts_raw)
            except json.JSONDecodeError:
                parsed = [item.strip() for item in scripts_raw.split(";") if item.strip()]
            if isinstance(parsed, list):
                scripts = [str(item).strip() for item in parsed if str(item).strip()]
                if scripts:
                    return scripts

        single_script = values.get("MCP_SERVER_SCRIPT", "").strip()
        if single_script:
            return [single_script]

        return ["../Day16/server.py"]

    def _collect_mcp_servers(self) -> list[dict[str, Any]]:
        if not hasattr(self, "mcp_servers_input"):
            return []

        lines = self.mcp_servers_input.get("1.0", "end").splitlines()
        result: list[dict[str, Any]] = []
        for index, line in enumerate(lines, start=1):
            script = line.strip()
            if not script:
                continue
            result.append(
                {
                    "id": f"server_{index}",
                    "server_script": script,
                }
            )
        return result

    def _join_url(self, path: str) -> str:
        return self.base_url_var.get().rstrip("/") + "/" + path.lstrip("/")

    def _auth_headers(self) -> dict[str, str]:
        headers: dict[str, str] = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return headers

    def _set_auth_state(self, token: str | None, user: dict[str, Any] | None) -> None:
        self.access_token = token
        self.current_user = user
        if token and user:
            preview = token[:16] + "..." if len(token) > 16 else token
            self.token_preview_var.set(f"{user.get('email')} | {preview}")
        else:
            self.token_preview_var.set("not authenticated")
        self._schedule_session_save()

    def _update_model_values(self, values: list[str]) -> None:
        cleaned = [value for value in values if value]
        if not cleaned:
            cleaned = ["openai/gpt-4o-mini"]
        self.model_values = cleaned
        if self.model_var.get() not in self.model_values:
            self.model_var.set(self.model_values[0])
        self._schedule_session_save()

    def _reset_request_context(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.history.clear()
        self.chat_transcript.clear()
        self.last_raw_response = None
        self.conversation_id_var.set(str(uuid.uuid4()))
        self._update_mcp_panels(None)
        self._render_chat_transcript()
        self._schedule_session_save()

    def new_conversation(self) -> None:
        self.conversation_id_var.set(str(uuid.uuid4()))
        self.history.clear()
        self._update_mcp_panels(None)
        self.chat_transcript.clear()
        self._render_chat_transcript()
        self.append_chat("system", f"New conversation: {self.conversation_id_var.get()}")
        self.set_status("new conversation created")
        self._schedule_session_save()

    def clear_chat(self) -> None:
        self.history.clear()
        self.chat_transcript.clear()
        self.last_raw_response = None
        self._update_mcp_panels(None)
        self._render_chat_transcript()
        self.set_status("chat cleared")
        self._schedule_session_save()

    def logout(self) -> None:
        self._reset_request_context()
        self._set_auth_state(None, None)
        self.set_status("logged out")
        self._schedule_session_save()

    def copy_token(self) -> None:
        if not self.access_token:
            self.set_status("no token to copy")
            return
        self.clipboard_clear()
        self.clipboard_append(self.access_token)
        self.set_status("token copied")

    def build_payload(self, user_message: str) -> dict[str, Any]:
        messages: list[dict[str, str]] = []
        if self.include_history_var.get():
            messages.extend(self.history)
        messages.append({"role": "user", "content": user_message})
        mcp_servers = self._collect_mcp_servers()

        payload: dict[str, Any] = {
            "conversation_id": self.conversation_id_var.get().strip() or str(uuid.uuid4()),
            "branch_id": self.branch_id_var.get().strip() or "main",
            "task_id": self.task_id_var.get().strip() or None,
            "model": self.model_var.get().strip() or "openai/gpt-4o-mini",
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": 800,
            "top_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
            "show_task_transition_in_chat": self.show_task_transition_in_chat_var.get(),
        }

        if self.require_json_var.get():
            payload["validation"] = {"require_json": True}

        payload["mcp"] = {
            "enabled": self.enable_mcp_var.get(),
            "servers": mcp_servers,
        }
        payload["rag"] = {
            "enabled": self.enable_rag_var.get(),
        }

        return payload

    def copy_payload(self) -> None:
        message = self.message_input.get("1.0", "end").strip() or "test message"
        payload = self.build_payload(message)
        self.clipboard_clear()
        self.clipboard_append(json.dumps(payload, ensure_ascii=False, indent=2))
        self.set_status("payload copied")

    def check_health(self) -> None:
        self._run_request(
            name="health",
            method="GET",
            url=self._join_url("/health"),
            json_payload=None,
            headers={},
        )

    def fetch_me(self) -> None:
        self._run_request(
            name="me",
            method="GET",
            url=self._join_url("/auth/me"),
            json_payload=None,
            headers=self._auth_headers(),
        )

    def fetch_models(self) -> None:
        if not self.access_token:
            self.set_status("login first")
            return

        self._run_request(
            name="models",
            method="GET",
            url=self._join_url("/models"),
            json_payload=None,
            headers=self._auth_headers(),
        )

    def open_model_picker(self) -> None:
        popup = ctk.CTkToplevel(self)
        popup.title("Choose model")
        popup.geometry("720x520")
        popup.grid_columnconfigure(0, weight=1)
        popup.grid_rowconfigure(1, weight=1)

        search_var = ctk.StringVar(value="")
        search_entry = ctk.CTkEntry(popup, textvariable=search_var, placeholder_text="Filter models")
        search_entry.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="ew")

        list_frame = ctk.CTkFrame(popup)
        list_frame.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        list_frame.grid_columnconfigure(0, weight=1)
        list_frame.grid_rowconfigure(0, weight=1)

        scrollbar = tk.Scrollbar(list_frame, orient="vertical")
        listbox = tk.Listbox(list_frame, yscrollcommand=scrollbar.set, activestyle="dotbox")
        scrollbar.config(command=listbox.yview)
        listbox.grid(row=0, column=0, sticky="nsew")
        scrollbar.grid(row=0, column=1, sticky="ns")

        def refresh_list(*_args: Any) -> None:
            query = search_var.get().strip().lower()
            listbox.delete(0, "end")
            for item in self.model_values:
                if not query or query in item.lower():
                    listbox.insert("end", item)

        def choose_selected(_event: Any = None) -> None:
            selection = listbox.curselection()
            if not selection:
                return
            self.model_var.set(str(listbox.get(selection[0])))
            popup.destroy()

        search_var.trace_add("write", refresh_list)
        listbox.bind("<Double-Button-1>", choose_selected)
        listbox.bind("<Return>", choose_selected)

        refresh_list()
        search_entry.focus()

    def login(self) -> None:
        email = self.email_var.get().strip()
        password = self.password_var.get()
        if not email or not password:
            self.set_status("enter email and password")
            return

        self._run_request(
            name="login",
            method="POST",
            url=self._join_url("/auth/login"),
            json_payload={"email": email, "password": password},
            headers={},
        )

    def register(self) -> None:
        email = self.register_email_var.get().strip()
        password = self.register_password_var.get()
        confirm = self.confirm_password_var.get()

        if not email or not password:
            self.set_status("fill email and password")
            return
        if password != confirm:
            self.set_status("passwords do not match")
            return

        self._run_request(
            name="register",
            method="POST",
            url=self._join_url("/auth/register"),
            json_payload={"email": email, "password": password},
            headers={},
        )

    def send_message(self) -> None:
        if not self.access_token:
            self.set_status("login first")
            return

        if self.request_thread and self.request_thread.is_alive():
            self.set_status("wait for the current request")
            return

        user_message = self.message_input.get("1.0", "end").strip()
        if not user_message:
            self.set_status("enter a message")
            return

        payload = self.build_payload(user_message)
        self.conversation_id_var.set(str(payload["conversation_id"]))

        self.append_chat("user", user_message)
        self.message_input.delete("1.0", "end")
        self.set_status("sending request")
        self._schedule_session_save()

        self._run_request(
            name="generate",
            method="POST",
            url=self._join_url("/generate"),
            json_payload=payload,
            headers=self._auth_headers(),
            user_message=user_message,
        )

    def show_last_raw(self) -> None:
        if self.last_raw_response is None:
            self.set_status("raw response is empty")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Raw response")
        popup.geometry("860x640")

        textbox = ctk.CTkTextbox(popup, wrap="word")
        textbox.pack(fill="both", expand=True, padx=12, pady=12)
        if isinstance(self.last_raw_response, (dict, list)):
            textbox.insert("1.0", json.dumps(self.last_raw_response, ensure_ascii=False, indent=2))
        else:
            textbox.insert("1.0", str(self.last_raw_response))
        textbox.configure(state="disabled")

    def _run_request(
        self,
        *,
        name: str,
        method: str,
        url: str,
        json_payload: dict[str, Any] | None,
        headers: dict[str, str],
        user_message: str | None = None,
    ) -> None:
        if self.request_thread and self.request_thread.is_alive():
            self.set_status("wait for the current request")
            return

        self._set_controls_enabled(False)
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
            timeout = float(self.timeout_var.get().strip())
        except ValueError:
            timeout = 60.0

        try:
            if method == "GET":
                response = self.session.get(url, headers=headers, timeout=timeout)
            else:
                response = self.session.post(url, json=json_payload, headers=headers, timeout=timeout)

            content_type = response.headers.get("content-type", "")
            body: Any
            if "application/json" in content_type.lower():
                body = response.json()
            else:
                body = response.text

            self.result_queue.put(
                {
                    "ok": response.ok,
                    "status_code": response.status_code,
                    "body": body,
                    "name": name,
                    "user_message": user_message,
                }
            )
        except Exception as exc:
            self.result_queue.put(
                {
                    "ok": False,
                    "status_code": None,
                    "body": str(exc),
                    "name": name,
                    "user_message": user_message,
                }
            )

    def _poll_queue(self) -> None:
        try:
            while True:
                result = self.result_queue.get_nowait()
                self._handle_result(result)
        except queue.Empty:
            pass
        finally:
            self.after(150, self._poll_queue)

    def _set_controls_enabled(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        for widget in (
            self.send_button,
            self.health_button,
            self.me_button,
            self.login_button,
            self.register_button,
            self.choose_model_button,
            self.refresh_models_button,
            self.copy_payload_button,
            self.copy_token_button,
            self.logout_button,
            self.new_conv_button,
            self.clear_chat_button,
        ):
            widget.configure(state=state)

    def _handle_result(self, result: dict[str, Any]) -> None:
        self._set_controls_enabled(True)
        self.last_raw_response = result["body"]

        name = result["name"]
        if name == "health":
            if result["ok"]:
                self.append_chat("system", f"Health OK ({result['status_code']})\n{self._format_body(result['body'])}")
                self.set_status("health ok")
            else:
                self.append_chat("error", self._format_error(result))
                self.set_status("health failed")
            self._schedule_session_save()
            return

        if name in {"login", "register"}:
            if result["ok"] and isinstance(result["body"], dict):
                token = result["body"].get("access_token")
                user = result["body"].get("user")
                if isinstance(token, str) and isinstance(user, dict):
                    self._reset_request_context()
                    self._set_auth_state(token, user)
                    self.append_chat(
                        "system",
                        f"Authenticated as {user.get('email')}\n"
                        f"New conversation: {self.conversation_id_var.get()}",
                    )
                    self.set_status(f"{name} successful")
                    self._schedule_session_save()
                    self.fetch_models()
                    return

            self.append_chat("error", self._format_error(result))
            self.set_status(f"{name} failed")
            self._schedule_session_save()
            return

        if name == "me":
            if result["ok"]:
                if isinstance(result["body"], dict):
                    self.current_user = result["body"]
                self.append_chat("system", self._format_body(result["body"]))
                self.set_status("user loaded")
            else:
                self.append_chat("error", self._format_error(result))
                self.set_status("failed to load user")
            self._schedule_session_save()
            return

        if name == "models":
            if result["ok"] and isinstance(result["body"], dict):
                data = result["body"].get("data")
                if isinstance(data, list):
                    models = [
                        str(item.get("id"))
                        for item in data
                        if isinstance(item, dict) and item.get("id")
                    ]
                    self._update_model_values(models)
                    self.set_status(f"models loaded: {len(self.model_values)}")
                    self._schedule_session_save()
                    return

            self.append_chat("error", self._format_error(result))
            self.set_status("failed to load models")
            self._schedule_session_save()
            return

        if name == "generate":
            if result["ok"]:
                assistant_text = self._extract_assistant_text(result["body"])
                self.append_chat("assistant", assistant_text)
                task_meta_text = self._extract_task_meta_text(result["body"])
                if task_meta_text:
                    self.append_chat("task", task_meta_text)
                self._update_mcp_panels(result["body"])
                if result["user_message"]:
                    self.history.append({"role": "user", "content": str(result["user_message"])})
                self.history.append({"role": "assistant", "content": assistant_text})
                self.set_status(f"response received ({result['status_code']})")
            else:
                self.append_chat("error", self._format_error(result))
                self.set_status("request failed")
            self._schedule_session_save()

    def _update_mcp_panels(self, body: Any) -> None:
        if not isinstance(body, dict) or not body.get("mcp_used"):
            self.mcp_summary_label.configure(
                text="MCP is idle. Send a request with MCP enabled to inspect connected servers and tools."
            )
            self._set_textbox(self.mcp_servers_box, "No active MCP servers in the last response.")
            self._set_textbox(self.mcp_tools_box, "No MCP tools discovered yet.")
            return

        servers = body.get("mcp_servers") or []
        available_tools = body.get("mcp_available_tools") or []
        tool_calls = body.get("mcp_tool_calls") or []

        self.mcp_summary_label.configure(
            text=(
                f"MCP active. Servers: {len(servers)} | "
                f"tools discovered: {body.get('mcp_tools_offered', 0)} | "
                f"tool calls executed: {len(tool_calls)}"
            )
        )

        server_lines = [f"{index}. {server}" for index, server in enumerate(servers, start=1)]
        if tool_calls:
            server_lines.append("")
            server_lines.append("Executed calls:")
            server_lines.extend(f"- {call}" for call in tool_calls)
        self._set_textbox(self.mcp_servers_box, "\n".join(server_lines) or "No servers reported.")

        grouped: dict[str, list[dict[str, Any]]] = {}
        for item in available_tools:
            server_id = str(item.get("server_id") or "unknown")
            grouped.setdefault(server_id, []).append(item)

        tool_lines: list[str] = []
        if grouped:
            for server_id, items in grouped.items():
                tool_lines.append(f"[{server_id}]")
                for item in items:
                    tool_lines.append(f"- {item.get('tool_alias')} ({item.get('tool_name')})")
                    description = str(item.get("description") or "").strip()
                    if description:
                        tool_lines.append(f"  {description}")
                tool_lines.append("")
        else:
            for item in body.get("mcp_tool_trace") or []:
                tool_lines.append(
                    f"- {item.get('tool_alias') or item.get('tool_name')} | server={item.get('server_id')}"
                )

        self._set_textbox(self.mcp_tools_box, "\n".join(tool_lines).strip() or "No tools reported.")

    def _extract_assistant_text(self, body: Any) -> str:
        if isinstance(body, dict):
            for key in ("content", "response", "answer", "text", "message"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            return json.dumps(body, ensure_ascii=False, indent=2)
        return str(body)

    def _extract_task_meta_text(self, body: Any) -> str:
        if not isinstance(body, dict):
            return ""

        lines: list[str] = []
        task_state = body.get("task_state")
        task_transition = body.get("task_transition")
        task_error = body.get("task_transition_error")

        if isinstance(task_state, dict):
            lines.append(
                "State: "
                f"task_id={task_state.get('task_id')} | "
                f"status={task_state.get('status')} | "
                f"stage={task_state.get('stage')} | "
                f"expected_action={task_state.get('expected_action')}"
            )
            allowed_events = task_state.get("allowed_events")
            if allowed_events:
                lines.append(f"Allowed events: {', '.join(str(item) for item in allowed_events)}")
            current_step = task_state.get("current_step")
            if current_step:
                lines.append(f"Current step: {current_step}")
            blocked_reason = task_state.get("blocked_reason")
            if blocked_reason:
                lines.append(f"Blocked reason: {blocked_reason}")

        if isinstance(task_transition, dict):
            if task_transition.get("applied"):
                lines.append(
                    "Transition: "
                    f"{task_transition.get('from_stage')} -> {task_transition.get('to_stage')} "
                    f"(event={task_transition.get('event')})"
                )
            elif task_transition.get("event"):
                lines.append(
                    "Transition not applied: "
                    f"event={task_transition.get('event')}"
                )

        if isinstance(task_error, dict) and task_error.get("message"):
            lines.append(f"Transition error: {task_error.get('message')}")

        return "\n".join(lines)

    def _format_error(self, result: dict[str, Any]) -> str:
        return f"Request error ({result['status_code']}):\n{self._format_body(result['body'])}"

    def _format_body(self, body: Any) -> str:
        if isinstance(body, (dict, list)):
            return json.dumps(body, ensure_ascii=False, indent=2)
        return str(body)

    def _bind_session_persistence_hooks(self) -> None:
        tracked_vars = (
            self.base_url_var,
            self.theme_var,
            self.timeout_var,
            self.email_var,
            self.register_email_var,
            self.model_var,
            self.branch_id_var,
            self.task_id_var,
            self.conversation_id_var,
            self.include_history_var,
            self.require_json_var,
            self.show_task_transition_in_chat_var,
            self.enable_mcp_var,
            self.enable_rag_var,
        )
        for variable in tracked_vars:
            variable.trace_add("write", self._on_session_var_changed)

        self.message_input.bind("<KeyRelease>", self._on_session_widget_changed, add="+")
        self.mcp_servers_input.bind("<KeyRelease>", self._on_session_widget_changed, add="+")

    def _on_session_var_changed(self, *_args: Any) -> None:
        self._schedule_session_save()

    def _on_session_widget_changed(self, _event: Any) -> None:
        self._schedule_session_save()

    def _schedule_session_save(self) -> None:
        if self._session_restore_in_progress:
            return
        if self._session_save_after_id is not None:
            self.after_cancel(self._session_save_after_id)
        self._session_save_after_id = self.after(250, self._save_session_state)

    def _collect_session_state(self) -> dict[str, Any]:
        return {
            "base_url": self.base_url_var.get(),
            "theme": self.theme_var.get(),
            "timeout": self.timeout_var.get(),
            "email": self.email_var.get(),
            "register_email": self.register_email_var.get(),
            "model": self.model_var.get(),
            "model_values": self.model_values,
            "branch_id": self.branch_id_var.get(),
            "task_id": self.task_id_var.get(),
            "conversation_id": self.conversation_id_var.get(),
            "include_history": self.include_history_var.get(),
            "require_json": self.require_json_var.get(),
            "show_task_transition_in_chat": self.show_task_transition_in_chat_var.get(),
            "enable_mcp": self.enable_mcp_var.get(),
            "enable_rag": self.enable_rag_var.get(),
            "access_token": self.access_token,
            "current_user": self.current_user,
            "history": self.history,
            "chat_transcript": self.chat_transcript,
            "message_draft": self.message_input.get("1.0", "end").strip(),
            "mcp_server_scripts": [item.get("server_script") for item in self._collect_mcp_servers()],
        }

    def _save_session_state(self) -> None:
        self._session_save_after_id = None
        if self._session_restore_in_progress:
            return
        try:
            self.session_state_path.write_text(
                json.dumps(self._collect_session_state(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
        except OSError:
            return

    def _load_session_state(self) -> None:
        if not self.session_state_path.exists():
            return

        try:
            raw_state = json.loads(self.session_state_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(raw_state, dict):
            return

        self._session_restore_in_progress = True
        try:
            self.base_url_var.set(str(raw_state.get("base_url") or self.base_url_var.get()))
            self.theme_var.set(str(raw_state.get("theme") or self.theme_var.get()))
            ctk.set_appearance_mode(self.theme_var.get())
            self.timeout_var.set(str(raw_state.get("timeout") or self.timeout_var.get()))
            self.email_var.set(str(raw_state.get("email") or ""))
            self.register_email_var.set(str(raw_state.get("register_email") or ""))
            self.model_var.set(str(raw_state.get("model") or self.model_var.get()))

            model_values = raw_state.get("model_values")
            if isinstance(model_values, list):
                self._update_model_values([str(item) for item in model_values if str(item).strip()])

            self.branch_id_var.set(str(raw_state.get("branch_id") or self.branch_id_var.get()))
            self.task_id_var.set(str(raw_state.get("task_id") or ""))
            self.conversation_id_var.set(
                str(raw_state.get("conversation_id") or self.conversation_id_var.get())
            )
            self.include_history_var.set(bool(raw_state.get("include_history", self.include_history_var.get())))
            self.require_json_var.set(bool(raw_state.get("require_json", self.require_json_var.get())))
            self.show_task_transition_in_chat_var.set(
                bool(
                    raw_state.get(
                        "show_task_transition_in_chat",
                        self.show_task_transition_in_chat_var.get(),
                    )
                )
            )
            self.enable_mcp_var.set(bool(raw_state.get("enable_mcp", self.enable_mcp_var.get())))
            self.enable_rag_var.set(bool(raw_state.get("enable_rag", self.enable_rag_var.get())))

            token = raw_state.get("access_token")
            user = raw_state.get("current_user")
            if isinstance(token, str) and isinstance(user, dict):
                self._set_auth_state(token, user)

            history = raw_state.get("history")
            if isinstance(history, list):
                self.history = [
                    {"role": str(item.get("role") or "system"), "content": str(item.get("content") or "")}
                    for item in history
                    if isinstance(item, dict)
                ]
            else:
                self.history = []

            transcript = raw_state.get("chat_transcript")
            if isinstance(transcript, list):
                self.chat_transcript = [
                    {"role": str(item.get("role") or "system"), "content": str(item.get("content") or "")}
                    for item in transcript
                    if isinstance(item, dict)
                ]
            else:
                self.chat_transcript = [
                    {"role": item["role"], "content": item["content"]}
                    for item in self.history
                    if isinstance(item, dict)
                    and isinstance(item.get("role"), str)
                    and isinstance(item.get("content"), str)
                ]
            self._render_chat_transcript()

            scripts = raw_state.get("mcp_server_scripts")
            if isinstance(scripts, list):
                cleaned_scripts = [str(item).strip() for item in scripts if str(item).strip()]
                self.mcp_servers_input.delete("1.0", "end")
                self.mcp_servers_input.insert(
                    "1.0",
                    "\n".join(cleaned_scripts or self.default_mcp_server_scripts),
                )

            message_draft = str(raw_state.get("message_draft") or "")
            if message_draft:
                self.message_input.delete("1.0", "end")
                self.message_input.insert("1.0", message_draft)
        finally:
            self._session_restore_in_progress = False

    def _render_chat_transcript(self) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        for item in self.chat_transcript:
            role = str(item.get("role") or "system")
            content = str(item.get("content") or "")
            self.chat_box.insert("end", f"{role}\n{content}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _on_close(self) -> None:
        if self._session_save_after_id is not None:
            self.after_cancel(self._session_save_after_id)
            self._session_save_after_id = None
        self._save_session_state()
        self.destroy()


if __name__ == "__main__":
    app = LLMTesterApp()
    app.mainloop()
