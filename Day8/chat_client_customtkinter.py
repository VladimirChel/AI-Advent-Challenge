import json
import queue
import threading
import uuid
from dataclasses import dataclass
from typing import Optional

import customtkinter as ctk
import requests
from requests import Response
from tkinter import messagebox


ctk.set_appearance_mode("System")
ctk.set_default_color_theme("blue")


@dataclass
class TokenUsage:
    prompt_tokens: int = 0
    completion_tokens: int = 0
    total_tokens: int = 0


class LLMChatClient(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()

        self.title("LLM Gateway Chat Client")
        self.geometry("1100x760")
        self.minsize(900, 650)

        self.response_queue: queue.Queue = queue.Queue()
        self.conversation_id = str(uuid.uuid4())
        self.dialog_total_tokens = 0
        self.request_total_tokens = 0
        self.request_count = 0

        self._build_layout()
        self.after(100, self._poll_response_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=310, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)
        
        for i in range(17):
            self.sidebar.grid_rowconfigure(i, weight=0)
        self.sidebar.grid_rowconfigure(16, weight=1)
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.main = ctk.CTkFrame(self, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew")
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(1, weight=1)

        title = ctk.CTkLabel(
            self.sidebar,
            text="LLM Gateway",
            font=ctk.CTkFont(size=24, weight="bold"),
        )
        title.grid(row=0, column=0, padx=20, pady=(20, 10), sticky="w")

        subtitle = ctk.CTkLabel(
            self.sidebar,
            text="Чат-клиент на customtkinter",
            font=ctk.CTkFont(size=13),
        )
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 20), sticky="w")

        self.base_url_entry = self._add_labeled_entry(
            row=2,
            label="Base URL",
            default_value="http://127.0.0.1:8000",
        )
        self.model_entry = self._add_labeled_entry(
            row=4,
            label="Model",
            default_value="openai/gpt-4o-mini",
        )
        self.user_id_entry = self._add_labeled_entry(
            row=6,
            label="User ID",
            default_value="desktop-user",
        )
        self.temperature_entry = self._add_labeled_entry(
            row=8,
            label="Temperature",
            default_value="0.2",
        )
        self.max_tokens_entry = self._add_labeled_entry(
            row=10,
            label="Max tokens",
            default_value="500",
        )
        self.history_limit_entry = self._add_labeled_entry(
        row=12,
        label="History limit",
        default_value="20",
        )

        self.memory_switch = ctk.CTkSwitch(self.sidebar, text="Использовать Memory API")
        self.memory_switch.select()
        self.memory_switch.grid(row=14, column=0, padx=20, pady=(10, 8), sticky="w")

        self.new_chat_button = ctk.CTkButton(
        self.sidebar,
        text="Новый диалог",
        command=self.start_new_dialog,
        )
        self.new_chat_button.grid(row=15, column=0, padx=20, pady=(12, 8), sticky="ew")

        self.clear_button = ctk.CTkButton(
        self.sidebar,
        text="Очистить окно",
        fg_color="transparent",
        border_width=1,
        command=self.clear_chat_view,
)
        self.clear_button.grid(row=16, column=0, padx=20, pady=(0, 20), sticky="sew")
        header = ctk.CTkFrame(self.main)
        header.grid(row=0, column=0, padx=16, pady=16, sticky="ew")
        header.grid_columnconfigure((0, 1, 2, 3), weight=1)

        self.conversation_label = ctk.CTkLabel(
            header,
            text=f"Диалог: {self.conversation_id}",
            anchor="w",
            justify="left",
            font=ctk.CTkFont(size=14, weight="bold"),
        )
        self.conversation_label.grid(row=0, column=0, columnspan=4, padx=12, pady=(10, 6), sticky="ew")

        self.req_tokens_label = self._metric_label(header, 1, 0, "Токены за запрос", "0")
        self.prompt_tokens_label = self._metric_label(header, 1, 1, "Prompt", "0")
        self.completion_tokens_label = self._metric_label(header, 1, 2, "Completion", "0")
        self.dialog_tokens_label = self._metric_label(header, 1, 3, "Всего за диалог", "0")

        self.chat_box = ctk.CTkTextbox(self.main, wrap="word", font=("Consolas", 14))
        self.chat_box.grid(row=1, column=0, padx=16, pady=(0, 12), sticky="nsew")
        self.chat_box.insert("end", "Система: клиент готов к работе.\n")
        self.chat_box.configure(state="disabled")

        composer = ctk.CTkFrame(self.main)
        composer.grid(row=2, column=0, padx=16, pady=(0, 16), sticky="ew")
        composer.grid_columnconfigure(0, weight=1)
        composer.grid_rowconfigure(0, weight=1)

        self.input_box = ctk.CTkTextbox(composer, height=110, wrap="word", font=("Consolas", 14))
        self.input_box.grid(row=0, column=0, padx=(12, 8), pady=12, sticky="ew")
        self.input_box.bind("<Control-Return>", self._send_hotkey)

        buttons = ctk.CTkFrame(composer, fg_color="transparent")
        buttons.grid(row=0, column=1, padx=(0, 12), pady=12, sticky="ns")

        self.send_button = ctk.CTkButton(buttons, text="Отправить", width=120, command=self.send_message)
        self.send_button.grid(row=0, column=0, pady=(0, 8), sticky="ew")

        self.status_label = ctk.CTkLabel(buttons, text="Готов", justify="left")
        self.status_label.grid(row=1, column=0, sticky="w")

        hint = ctk.CTkLabel(
            composer,
            text="Ctrl+Enter — отправить сообщение",
            font=ctk.CTkFont(size=12),
        )
        hint.grid(row=1, column=0, padx=12, pady=(0, 10), sticky="w")

    def _add_labeled_entry(self, row: int, label: str, default_value: str) -> ctk.CTkEntry:
        lbl = ctk.CTkLabel(self.sidebar, text=label)
        lbl.grid(row=row, column=0, padx=20, pady=(4, 4), sticky="w")
        entry = ctk.CTkEntry(self.sidebar)
        entry.grid(row=row + 1, column=0, padx=20, pady=(0, 8), sticky="ew")
        entry.insert(0, default_value)
        return entry

    def _metric_label(self, parent: ctk.CTkFrame, row: int, column: int, title: str, value: str) -> ctk.CTkLabel:
        card = ctk.CTkFrame(parent)
        card.grid(row=row, column=column, padx=8, pady=(0, 10), sticky="ew")
        label_title = ctk.CTkLabel(card, text=title, font=ctk.CTkFont(size=12))
        label_title.pack(anchor="w", padx=10, pady=(8, 0))
        label_value = ctk.CTkLabel(card, text=value, font=ctk.CTkFont(size=20, weight="bold"))
        label_value.pack(anchor="w", padx=10, pady=(2, 8))
        return label_value

    def _send_hotkey(self, event) -> str:
        self.send_message()
        return "break"

    def start_new_dialog(self) -> None:
        self.conversation_id = str(uuid.uuid4())
        self.dialog_total_tokens = 0
        self.request_total_tokens = 0
        self.request_count = 0
        self._update_usage_labels(TokenUsage())
        self._append_chat("Система", f"Начат новый диалог: {self.conversation_id}")
        self.conversation_label.configure(text=f"Диалог: {self.conversation_id}")

    def clear_chat_view(self) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.insert("end", "Система: окно чата очищено.\n")
        self.chat_box.configure(state="disabled")

    def send_message(self) -> None:
        text = self.input_box.get("1.0", "end").strip()
        if not text:
            return

        try:
            temperature = float(self.temperature_entry.get().strip())
            max_tokens = int(self.max_tokens_entry.get().strip())
            history_limit = int(self.history_limit_entry.get().strip())
        except ValueError:
            messagebox.showerror("Ошибка", "Temperature, Max tokens и History limit должны быть числами.")
            return

        payload = {
            "model": self.model_entry.get().strip(),
            "messages": [{"role": "user", "content": text}],
            "conversation_id": self.conversation_id,
            "use_memory": bool(self.memory_switch.get()),
            "history_limit": history_limit,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "user_id": self.user_id_entry.get().strip() or None,
        }

        self.input_box.delete("1.0", "end")
        self._append_chat("Вы", text)
        self._set_busy(True, "Отправка запроса...")

        worker = threading.Thread(
            target=self._request_worker,
            args=(self.base_url_entry.get().strip(), payload),
            daemon=True,
        )
        worker.start()

    def _request_worker(self, base_url: str, payload: dict) -> None:
        try:
            response = requests.post(
                f"{base_url.rstrip('/')}/generate",
                json=payload,
                timeout=180,
            )
            self.response_queue.put(("ok", self._parse_response(response)))
        except Exception as exc:
            self.response_queue.put(("error", str(exc)))

    def _parse_response(self, response: Response) -> dict:
        try:
            data = response.json()
        except Exception:
            response.raise_for_status()
            raise RuntimeError("Сервер вернул не-JSON ответ.")

        if response.status_code >= 400:
            detail = data.get("detail", data)
            if isinstance(detail, dict):
                message = detail.get("message") or json.dumps(detail, ensure_ascii=False, indent=2)
            else:
                message = str(detail)
            raise RuntimeError(f"HTTP {response.status_code}: {message}")

        return data

    def _poll_response_queue(self) -> None:
        try:
            while True:
                status, payload = self.response_queue.get_nowait()
                if status == "ok":
                    self._handle_success(payload)
                else:
                    self._handle_error(payload)
        except queue.Empty:
            pass
        finally:
            self.after(100, self._poll_response_queue)

    def _handle_success(self, data: dict) -> None:
        content = data.get("content", "")
        usage = data.get("usage") or {}
        token_usage = TokenUsage(
            prompt_tokens=int(usage.get("prompt_tokens") or 0),
            completion_tokens=int(usage.get("completion_tokens") or 0),
            total_tokens=int(usage.get("total_tokens") or 0),
        )

        self.request_count += 1
        self.request_total_tokens = token_usage.total_tokens
        self.dialog_total_tokens += token_usage.total_tokens

        returned_conversation_id = data.get("conversation_id")
        if returned_conversation_id:
            self.conversation_id = returned_conversation_id
            self.conversation_label.configure(text=f"Диалог: {self.conversation_id}")

        finish_reason = data.get("finish_reason") or "unknown"
        latency_ms = data.get("latency_ms", "?")
        self._append_chat(
            "Ассистент",
            content or "<пустой ответ>",
            meta=(
                f"finish_reason={finish_reason} | latency_ms={latency_ms} | "
                f"prompt={token_usage.prompt_tokens}, completion={token_usage.completion_tokens}, total={token_usage.total_tokens}"
            ),
        )
        self._update_usage_labels(token_usage)
        self._set_busy(False, f"Готов · запросов: {self.request_count}")

    def _handle_error(self, error_text: str) -> None:
        self._append_chat("Ошибка", error_text)
        self._set_busy(False, "Ошибка")
        messagebox.showerror("Ошибка запроса", error_text)

    def _append_chat(self, role: str, text: str, meta: Optional[str] = None) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{role}:\n{text.strip()}\n")
        if meta:
            self.chat_box.insert("end", f"[{meta}]\n")
        self.chat_box.insert("end", "\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def _update_usage_labels(self, usage: TokenUsage) -> None:
        self.req_tokens_label.configure(text=str(usage.total_tokens))
        self.prompt_tokens_label.configure(text=str(usage.prompt_tokens))
        self.completion_tokens_label.configure(text=str(usage.completion_tokens))
        self.dialog_tokens_label.configure(text=str(self.dialog_total_tokens))

    def _set_busy(self, busy: bool, status: str) -> None:
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.status_label.configure(text=status)


if __name__ == "__main__":
    app = LLMChatClient()
    app.mainloop()
