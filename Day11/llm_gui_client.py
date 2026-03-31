
import json
import queue
import threading
import uuid
from datetime import datetime

import customtkinter as ctk
import requests


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


class LLMTesterApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("LLM Assistant Tester")
        self.geometry("1280x800")
        self.minsize(1100, 720)

        self.result_queue: queue.Queue = queue.Queue()
        self.request_thread: threading.Thread | None = None

        self.base_url_var = ctk.StringVar(value="http://127.0.0.1:8000")
        self.generate_path_var = ctk.StringVar(value="/generate")
        self.health_path_var = ctk.StringVar(value="/health")
        self.model_var = ctk.StringVar(value="openai/gpt-4o-mini")
        self.user_id_var = ctk.StringVar(value="test-user")
        self.conversation_id_var = ctk.StringVar(value=str(uuid.uuid4()))
        self.timeout_var = ctk.StringVar(value="60")
        self.include_history_var = ctk.BooleanVar(value=True)
        self.include_memory_var = ctk.BooleanVar(value=True)
        self.theme_var = ctk.StringVar(value="System")

        self.history: list[dict] = []
        self.last_raw_response: dict | list | str | None = None

        self._build_layout()
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

        title = ctk.CTkLabel(
            header,
            text="LLM Assistant Tester",
            font=ctk.CTkFont(size=24, weight="bold"),
            anchor="w",
        )
        title.grid(row=0, column=0, padx=14, pady=(14, 4), sticky="ew")

        subtitle = ctk.CTkLabel(
            header,
            text="Клиент для тестирования chat-completions API и памяти ассистента",
            justify="left",
            wraplength=300,
            anchor="w",
        )
        subtitle.grid(row=1, column=0, padx=14, pady=(0, 14), sticky="ew")

        content = ctk.CTkScrollableFrame(self.sidebar)
        content.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 16))
        content.grid_columnconfigure(0, weight=1)

        row = 0
        row = self._add_entry(content, "Base URL", self.base_url_var, row)
        row = self._add_entry(content, "Generate path", self.generate_path_var, row)
        row = self._add_entry(content, "Health path", self.health_path_var, row)
        row = self._add_entry(content, "Model", self.model_var, row)
        row = self._add_entry(content, "User ID", self.user_id_var, row)
        row = self._add_entry(content, "Conversation ID", self.conversation_id_var, row)
        row = self._add_entry(content, "Timeout (sec)", self.timeout_var, row)

        theme_label = ctk.CTkLabel(content, text="Тема", anchor="w")
        theme_label.grid(row=row, column=0, padx=8, pady=(10, 6), sticky="ew")
        row += 1

        theme_menu = ctk.CTkOptionMenu(
            content,
            variable=self.theme_var,
            values=["System", "Light", "Dark"],
            command=self._change_theme,
        )
        theme_menu.grid(row=row, column=0, padx=8, pady=(0, 10), sticky="ew")
        row += 1

        options_frame = ctk.CTkFrame(content)
        options_frame.grid(row=row, column=0, padx=8, pady=(4, 10), sticky="ew")
        options_frame.grid_columnconfigure(0, weight=1)
        row += 1

        history_switch = ctk.CTkSwitch(
            options_frame,
            text="Передавать history в messages",
            variable=self.include_history_var,
        )
        history_switch.grid(row=0, column=0, padx=12, pady=(12, 8), sticky="w")

        memory_switch = ctk.CTkSwitch(
            options_frame,
            text="Подключать memory",
            variable=self.include_memory_var,
        )
        memory_switch.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

        buttons1 = ctk.CTkFrame(content)
        buttons1.grid(row=row, column=0, padx=8, pady=(0, 8), sticky="ew")
        buttons1.grid_columnconfigure((0, 1), weight=1)
        row += 1

        self.health_button = ctk.CTkButton(
            buttons1, text="Health check", command=self.check_health
        )
        self.health_button.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.new_conv_button = ctk.CTkButton(
            buttons1, text="Новый диалог", command=self.new_conversation
        )
        self.new_conv_button.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        buttons2 = ctk.CTkFrame(content)
        buttons2.grid(row=row, column=0, padx=8, pady=(0, 8), sticky="ew")
        buttons2.grid_columnconfigure((0, 1), weight=1)
        row += 1

        self.clear_chat_button = ctk.CTkButton(
            buttons2, text="Очистить чат", command=self.clear_chat
        )
        self.clear_chat_button.grid(row=0, column=0, padx=8, pady=8, sticky="ew")

        self.copy_payload_button = ctk.CTkButton(
            buttons2, text="Скопировать payload", command=self.copy_payload
        )
        self.copy_payload_button.grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        status_frame = ctk.CTkFrame(content)
        status_frame.grid(row=row, column=0, padx=8, pady=(2, 10), sticky="ew")
        status_frame.grid_columnconfigure(0, weight=1)
        row += 1

        self.status_label = ctk.CTkLabel(
            status_frame,
            text="Статус: готов",
            anchor="w",
            justify="left",
            wraplength=300,
        )
        self.status_label.grid(row=0, column=0, padx=12, pady=12, sticky="ew")

        hint_frame = ctk.CTkFrame(content)
        hint_frame.grid(row=row, column=0, padx=8, pady=(0, 8), sticky="nsew")
        hint_frame.grid_columnconfigure(0, weight=1)
        row += 1

        hint_title = ctk.CTkLabel(
            hint_frame,
            text="Подсказки",
            font=ctk.CTkFont(weight="bold"),
            anchor="w",
        )
        hint_title.grid(row=0, column=0, padx=12, pady=(12, 6), sticky="ew")

        hint = ctk.CTkTextbox(hint_frame, height=180)
        hint.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="nsew")
        hint.insert(
            "1.0",
            "• По умолчанию используется chat-completions payload.\n"
            "• История добавляется в поле messages.\n"
            "• Memory передаётся отдельным объектом memory.\n"
            "• Для нового сценария создай новый conversation_id.\n"
            "• Если backend ожидает другую схему, поправь build_payload().\n",
        )
        hint.configure(state="disabled")

    def _build_main(self) -> None:
        header = ctk.CTkFrame(self.main)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=16)
        header.grid_columnconfigure(0, weight=1)

        header_label = ctk.CTkLabel(
            header,
            text="Чат / лог запросов",
            font=ctk.CTkFont(size=22, weight="bold"),
        )
        header_label.grid(row=0, column=0, padx=16, pady=12, sticky="w")

        self.chat_box = ctk.CTkTextbox(self.main, wrap="word")
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 8))
        self.chat_box.configure(state="disabled")

        bottom = ctk.CTkFrame(self.main)
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        bottom.grid_columnconfigure(0, weight=1)

        self.message_input = ctk.CTkTextbox(bottom, height=120, wrap="word")
        self.message_input.grid(row=0, column=0, columnspan=3, sticky="ew", padx=12, pady=(12, 8))
        self.message_input.bind("<Control-Return>", self._send_hotkey)
        self.message_input.bind("<Command-Return>", self._send_hotkey)

        self.send_button = ctk.CTkButton(
            bottom, text="Отправить", height=40, command=self.send_message
        )
        self.send_button.grid(row=1, column=2, padx=(8, 12), pady=(0, 12), sticky="e")

        self.raw_button = ctk.CTkButton(
            bottom, text="Показать raw response", height=40, command=self.show_last_raw
        )
        self.raw_button.grid(row=1, column=1, padx=(8, 0), pady=(0, 12), sticky="e")

        self.info_label = ctk.CTkLabel(
            bottom,
            text="Ctrl+Enter — отправить сообщение",
            anchor="w",
        )
        self.info_label.grid(row=1, column=0, padx=12, pady=(0, 12), sticky="w")

    def _add_entry(self, parent, label_text: str, variable: ctk.StringVar, row: int) -> int:
        label = ctk.CTkLabel(parent, text=label_text, anchor="w")
        label.grid(row=row, column=0, padx=8, pady=(8, 4), sticky="ew")
        row += 1
        entry = ctk.CTkEntry(parent, textvariable=variable)
        entry.grid(row=row, column=0, padx=8, pady=(0, 4), sticky="ew")
        row += 1
        return row

    def _change_theme(self, value: str) -> None:
        ctk.set_appearance_mode(value)

    def _send_hotkey(self, event) -> str:
        self.send_message()
        return "break"

    def set_status(self, text: str) -> None:
        self.status_label.configure(text=f"Статус: {text}")

    def append_chat(self, role: str, text: str) -> None:
        ts = datetime.now().strftime("%H:%M:%S")
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"[{ts}] {role}\n{text}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def new_conversation(self) -> None:
        self.conversation_id_var.set(str(uuid.uuid4()))
        self.history.clear()
        self.append_chat("system", f"Создан новый conversation_id: {self.conversation_id_var.get()}")
        self.set_status("новый диалог создан")

    def clear_chat(self) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.configure(state="disabled")
        self.history.clear()
        self.last_raw_response = None
        self.set_status("чат очищен")

    def build_payload(self, user_message: str) -> dict:
        messages: list[dict] = []

        if self.include_history_var.get() and self.history:
            messages.extend(self.history)

        messages.append({
            "role": "user",
            "content": user_message
        })

        payload = {
            "model": self.model_var.get().strip() or "openai/gpt-4o-mini",
            "messages": messages,
        }

        if self.include_memory_var.get():
            payload["memory"] = {
                "conversation_id": self.conversation_id_var.get().strip(),
                "user_id": self.user_id_var.get().strip(),
                "enabled": True,
            }

        return payload

    def copy_payload(self) -> None:
        message = self.message_input.get("1.0", "end").strip()
        payload = self.build_payload(message or "test message")
        self.clipboard_clear()
        self.clipboard_append(json.dumps(payload, ensure_ascii=False, indent=2))
        self.set_status("payload скопирован в буфер обмена")

    def check_health(self) -> None:
        url = self._join_url(self.base_url_var.get(), self.health_path_var.get())
        self._run_request(
            name="health",
            method="GET",
            url=url,
            json_payload=None,
        )

    def send_message(self) -> None:
        if self.request_thread and self.request_thread.is_alive():
            self.set_status("дождись завершения текущего запроса")
            return

        user_message = self.message_input.get("1.0", "end").strip()
        if not user_message:
            self.set_status("введи сообщение")
            return

        payload = self.build_payload(user_message)
        url = self._join_url(self.base_url_var.get(), self.generate_path_var.get())

        self.append_chat("user", user_message)
        self.message_input.delete("1.0", "end")
        self.set_status("отправка запроса...")

        self._run_request(
            name="generate",
            method="POST",
            url=url,
            json_payload=payload,
            user_message=user_message,
        )

    def show_last_raw(self) -> None:
        if self.last_raw_response is None:
            self.set_status("raw response пока нет")
            return

        popup = ctk.CTkToplevel(self)
        popup.title("Raw response")
        popup.geometry("820x620")

        textbox = ctk.CTkTextbox(popup, wrap="word")
        textbox.pack(fill="both", expand=True, padx=12, pady=12)
        textbox.insert(
            "1.0",
            json.dumps(self.last_raw_response, ensure_ascii=False, indent=2)
            if isinstance(self.last_raw_response, (dict, list))
            else str(self.last_raw_response),
        )
        textbox.configure(state="disabled")

    def _join_url(self, base: str, path: str) -> str:
        return base.rstrip("/") + "/" + path.lstrip("/")

    def _run_request(
        self,
        *,
        name: str,
        method: str,
        url: str,
        json_payload: dict | None,
        user_message: str | None = None,
    ) -> None:
        self.send_button.configure(state="disabled")
        self.health_button.configure(state="disabled")
        self.request_thread = threading.Thread(
            target=self._request_worker,
            kwargs={
                "name": name,
                "method": method,
                "url": url,
                "json_payload": json_payload,
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
        json_payload: dict | None,
        user_message: str | None,
    ) -> None:
        try:
            timeout = float(self.timeout_var.get().strip())
        except ValueError:
            timeout = 60.0

        try:
            if method == "GET":
                response = requests.get(url, timeout=timeout)
            else:
                response = requests.post(url, json=json_payload, timeout=timeout)

            content_type = response.headers.get("content-type", "")
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
                    "payload": json_payload,
                    "url": url,
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
                    "payload": json_payload,
                    "url": url,
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

    def _handle_result(self, result: dict) -> None:
        self.send_button.configure(state="normal")
        self.health_button.configure(state="normal")
        self.last_raw_response = result["body"]

        if result["name"] == "health":
            if result["ok"]:
                self.append_chat("system", f"Health OK ({result['status_code']}): {self._format_body(result['body'])}")
                self.set_status("healthcheck успешен")
            else:
                self.append_chat("error", f"Health error: {self._format_body(result['body'])}")
                self.set_status("healthcheck завершился с ошибкой")
            return

        if result["ok"]:
            assistant_text = self._extract_assistant_text(result["body"])
            self.append_chat("assistant", assistant_text)
            if result["user_message"]:
                self.history.append({"role": "user", "content": result["user_message"]})
            self.history.append({"role": "assistant", "content": assistant_text})
            self.set_status(f"ответ получен ({result['status_code']})")
        else:
            self.append_chat(
                "error",
                f"Ошибка запроса ({result['status_code']}):\n{self._format_body(result['body'])}",
            )
            self.set_status("запрос завершился с ошибкой")

    def _extract_assistant_text(self, body) -> str:
        if isinstance(body, dict):
            if "choices" in body:
                try:
                    return body["choices"][0]["message"]["content"]
                except Exception:
                    pass

            for key in ("response", "answer", "content", "text", "message"):
                value = body.get(key)
                if isinstance(value, str) and value.strip():
                    return value

            if isinstance(body.get("data"), dict):
                for key in ("response", "answer", "content", "text", "message"):
                    value = body["data"].get(key)
                    if isinstance(value, str) and value.strip():
                        return value

            return json.dumps(body, ensure_ascii=False, indent=2)

        return str(body)

    def _format_body(self, body) -> str:
        if isinstance(body, (dict, list)):
            return json.dumps(body, ensure_ascii=False, indent=2)
        return str(body)


if __name__ == "__main__":
    app = LLMTesterApp()
    app.mainloop()
