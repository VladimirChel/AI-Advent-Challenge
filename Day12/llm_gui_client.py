import json
import queue
import threading
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
        self.geometry("1360x860")
        self.minsize(1180, 760)

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
        self.branch_id_var = ctk.StringVar(value="main")
        self.task_id_var = ctk.StringVar()
        self.conversation_id_var = ctk.StringVar(value=str(uuid.uuid4()))
        self.token_preview_var = ctk.StringVar(value="not authenticated")
        self.include_history_var = ctk.BooleanVar(value=True)
        self.require_json_var = ctk.BooleanVar(value=False)
        self.show_task_transition_in_chat_var = ctk.BooleanVar(value=True)

        self.access_token: str | None = None
        self.current_user: dict[str, Any] | None = None
        self.history: list[dict[str, str]] = []
        self.last_raw_response: Any = None

        self._build_layout()
        self.after(150, self._poll_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=380, corner_radius=0)
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
            text="CustomTkinter client for register, login and testing protected LLM endpoints.",
            justify="left",
            wraplength=320,
            anchor="w",
        ).grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")

        content = ctk.CTkScrollableFrame(self.sidebar)
        content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        content.grid_columnconfigure(0, weight=1)

        row = 0
        row = self._add_entry(content, "Base URL", self.base_url_var, row)
        row = self._add_entry(content, "Timeout (sec)", self.timeout_var, row)

        ctk.CTkLabel(content, text="Theme", anchor="w").grid(
            row=row, column=0, padx=8, pady=(8, 4), sticky="ew"
        )
        row += 1

        ctk.CTkOptionMenu(
            content,
            variable=self.theme_var,
            values=["System", "Light", "Dark"],
            command=self._change_theme,
        ).grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        row += 1

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

        request_box = ctk.CTkFrame(content)
        request_box.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        request_box.grid_columnconfigure(0, weight=1)
        row += 1

        ctk.CTkLabel(
            request_box,
            text="Chat Request",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        subrow = 1
        subrow = self._add_entry(request_box, "Model", self.model_var, subrow)
        subrow = self._add_entry(request_box, "Conversation ID", self.conversation_id_var, subrow)
        subrow = self._add_entry(request_box, "Branch ID", self.branch_id_var, subrow)
        subrow = self._add_entry(request_box, "Task ID (optional)", self.task_id_var, subrow)

        ctk.CTkSwitch(
            request_box,
            text="Include history",
            variable=self.include_history_var,
        ).grid(row=subrow, column=0, padx=12, pady=(2, 6), sticky="w")
        subrow += 1

        ctk.CTkSwitch(
            request_box,
            text="Require JSON response",
            variable=self.require_json_var,
        ).grid(row=subrow, column=0, padx=12, pady=(0, 10), sticky="w")
        subrow += 1

        ctk.CTkSwitch(
            request_box,
            text="Show task transitions in chat",
            variable=self.show_task_transition_in_chat_var,
        ).grid(row=subrow, column=0, padx=12, pady=(0, 10), sticky="w")
        subrow += 1

        request_buttons = ctk.CTkFrame(request_box, fg_color="transparent")
        request_buttons.grid(row=subrow, column=0, padx=8, pady=(0, 8), sticky="ew")
        request_buttons.grid_columnconfigure((0, 1), weight=1)

        self.new_conv_button = ctk.CTkButton(request_buttons, text="New conversation", command=self.new_conversation)
        self.new_conv_button.grid(row=0, column=0, padx=4, pady=4, sticky="ew")

        self.copy_payload_button = ctk.CTkButton(request_buttons, text="Copy payload", command=self.copy_payload)
        self.copy_payload_button.grid(row=0, column=1, padx=4, pady=4, sticky="ew")

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
            text="Chat / Request Log",
            font=ctk.CTkFont(size=22, weight="bold"),
            anchor="w",
        ).grid(row=0, column=0, padx=16, pady=12, sticky="w")

        self.chat_box = ctk.CTkTextbox(self.main, wrap="word")
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        self.chat_box.configure(state="disabled")

        bottom = ctk.CTkFrame(self.main)
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        bottom.grid_columnconfigure(0, weight=1)

        self.message_input = ctk.CTkTextbox(bottom, height=140, wrap="word")
        self.message_input.grid(row=0, column=0, columnspan=4, sticky="ew", padx=12, pady=(12, 8))
        self.message_input.bind("<Control-Return>", self._send_hotkey)
        self.message_input.bind("<Command-Return>", self._send_hotkey)

        self.send_button = ctk.CTkButton(bottom, text="Send", height=40, command=self.send_message)
        self.send_button.grid(row=1, column=3, padx=(8, 12), pady=(0, 12), sticky="e")

        self.raw_button = ctk.CTkButton(bottom, text="Show raw", height=40, command=self.show_last_raw)
        self.raw_button.grid(row=1, column=2, padx=(8, 0), pady=(0, 12), sticky="e")

        self.clear_chat_button = ctk.CTkButton(bottom, text="Clear chat", height=40, command=self.clear_chat)
        self.clear_chat_button.grid(row=1, column=1, padx=(8, 0), pady=(0, 12), sticky="e")

        ctk.CTkLabel(
            bottom,
            text="Ctrl+Enter to send",
            anchor="w",
        ).grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

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

    def _change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value)

    def _send_hotkey(self, _event: Any) -> str:
        self.send_message()
        return "break"

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=f"Status: {text}")

    def append_chat(self, role: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"[{ts}] {role}\n{text}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

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

    def _reset_request_context(self) -> None:
        self.session.close()
        self.session = requests.Session()
        self.history.clear()
        self.last_raw_response = None
        self.conversation_id_var.set(str(uuid.uuid4()))

    def new_conversation(self) -> None:
        self.conversation_id_var.set(str(uuid.uuid4()))
        self.history.clear()
        self.append_chat("system", f"New conversation: {self.conversation_id_var.get()}")
        self.set_status("new conversation created")

    def clear_chat(self) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.configure(state="disabled")
        self.history.clear()
        self.last_raw_response = None
        self.set_status("chat cleared")

    def logout(self) -> None:
        self._reset_request_context()
        self._set_auth_state(None, None)
        self.set_status("logged out")

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
                    return

            self.append_chat("error", self._format_error(result))
            self.set_status(f"{name} failed")
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
            return

        if name == "generate":
            if result["ok"]:
                assistant_text = self._extract_assistant_text(result["body"])
                self.append_chat("assistant", assistant_text)
                task_meta_text = self._extract_task_meta_text(result["body"])
                if task_meta_text:
                    self.append_chat("task", task_meta_text)
                if result["user_message"]:
                    self.history.append({"role": "user", "content": str(result["user_message"])})
                self.history.append({"role": "assistant", "content": assistant_text})
                self.set_status(f"response received ({result['status_code']})")
            else:
                self.append_chat("error", self._format_error(result))
                self.set_status("request failed")

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


if __name__ == "__main__":
    app = LLMTesterApp()
    app.mainloop()
