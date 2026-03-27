import json
import queue
import threading
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import customtkinter as ctk
import requests
from requests import Response
from tkinter import filedialog, messagebox


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
        self.geometry("1180x780")
        self.minsize(980, 680)

        self.response_queue: queue.Queue = queue.Queue()
        self.conversation_id = str(uuid.uuid4())
        self.dialog_total_tokens = 0
        self.request_total_tokens = 0
        self.request_count = 0
        self.loaded_history_messages: list[dict[str, str]] = []
        self.history_file_path: Optional[Path] = None
        self.session_messages: list[dict[str, str]] = []

        self._build_layout()
        self.after(100, self._poll_response_queue)

    def _build_layout(self) -> None:
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkFrame(self, width=340, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_propagate(False)

        for i in range(22):
            self.sidebar.grid_rowconfigure(i, weight=0)
        self.sidebar.grid_rowconfigure(21, weight=1)
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
        subtitle.grid(row=1, column=0, padx=20, pady=(0, 16), sticky="w")

        self.base_url_entry = self._add_labeled_entry(2, "Base URL", "http://127.0.0.1:8000")
        self.model_entry = self._add_labeled_entry(4, "Model", "openai/gpt-4o-mini")
        self.user_id_entry = self._add_labeled_entry(6, "User ID", "desktop-user")
        self.temperature_entry = self._add_labeled_entry(8, "Temperature", "0.2")
        self.max_tokens_entry = self._add_labeled_entry(10, "Max tokens", "500")
        self.history_limit_entry = self._add_labeled_entry(12, "History limit", "20")
        self.conversation_id_entry = self._add_labeled_entry(14, "Conversation ID", self.conversation_id)

        self.apply_conversation_button = ctk.CTkButton(
            self.sidebar,
            text="Применить conversation_id",
            command=self.apply_conversation_id,
        )
        self.apply_conversation_button.grid(row=16, column=0, padx=20, pady=(2, 8), sticky="ew")

        self.memory_switch = ctk.CTkSwitch(self.sidebar, text="Использовать Memory API")
        self.memory_switch.select()
        self.memory_switch.grid(row=17, column=0, padx=20, pady=(8, 8), sticky="w")

        self.load_history_button = ctk.CTkButton(
            self.sidebar,
            text="Загрузить диалог из файла",
            command=self.load_dialog_from_file,
        )
        self.load_history_button.grid(row=18, column=0, padx=20, pady=(6, 8), sticky="ew")

        self.save_history_button = ctk.CTkButton(
            self.sidebar,
            text="Сохранить диалог",
            command=self.save_dialog_to_file,
        )
        self.save_history_button.grid(row=19, column=0, padx=20, pady=(6, 8), sticky="ew")

        self.new_chat_button = ctk.CTkButton(
            self.sidebar,
            text="Новый диалог",
            command=self.start_new_dialog,
        )
        self.new_chat_button.grid(row=20, column=0, padx=20, pady=(6, 8), sticky="ew")

        self.clear_button = ctk.CTkButton(
            self.sidebar,
            text="Очистить окно",
            fg_color="transparent",
            border_width=1,
            command=self.clear_chat_view,
        )
        self.clear_button.grid(row=21, column=0, padx=20, pady=(0, 20), sticky="sew")

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

    def _sync_conversation_widgets(self) -> None:
        self.conversation_label.configure(text=f"Диалог: {self.conversation_id}")
        self.conversation_id_entry.delete(0, "end")
        self.conversation_id_entry.insert(0, self.conversation_id)

    def apply_conversation_id(self) -> None:
        new_conversation_id = self.conversation_id_entry.get().strip()
        if not new_conversation_id:
            messagebox.showerror("Ошибка", "conversation_id не может быть пустым.")
            return

        self.conversation_id = new_conversation_id
        self._sync_conversation_widgets()
        self._append_chat("Система", f"Установлен conversation_id вручную: {self.conversation_id}")

    def start_new_dialog(self) -> None:
        self.conversation_id = str(uuid.uuid4())
        self.dialog_total_tokens = 0
        self.request_total_tokens = 0
        self.request_count = 0
        self.loaded_history_messages = []
        self.history_file_path = None
        self.session_messages = []
        self._update_usage_labels(TokenUsage())
        self._append_chat("Система", f"Начат новый диалог: {self.conversation_id}")
        self._sync_conversation_widgets()

    def clear_chat_view(self) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.insert("end", "Система: окно чата очищено.\n")
        self.chat_box.configure(state="disabled")

    def save_dialog_to_file(self) -> None:
        if not self.session_messages and not self.loaded_history_messages:
            messagebox.showinfo("Сохранение", "Нет диалога для сохранения.")
            return

        initial_name = f"dialog_{self.conversation_id}"
        file_path = filedialog.asksaveasfilename(
            title="Сохранить диалог",
            defaultextension=".json",
            initialfile=initial_name,
            filetypes=[
                ("JSON files", "*.json"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        target = Path(file_path)
        try:
            if target.suffix.lower() == ".txt":
                self._write_dialog_as_text(target)
            else:
                self._write_dialog_as_json(target)
        except Exception as exc:
            messagebox.showerror("Ошибка сохранения", str(exc))
            return

        self._append_chat("Система", f"Диалог сохранён в файл: {target.name}")
        self._set_busy(False, f"Сохранено: {target.name}")

    def load_dialog_from_file(self) -> None:
        file_path = filedialog.askopenfilename(
            title="Выберите файл с диалогом",
            filetypes=[
                ("JSON files", "*.json"),
                ("Text files", "*.txt"),
                ("All files", "*.*"),
            ],
        )
        if not file_path:
            return

        try:
            parsed = self._read_dialog_file(Path(file_path))
        except Exception as exc:
            messagebox.showerror("Ошибка загрузки", str(exc))
            return

        file_conversation_id = parsed.get("conversation_id")
        messages = parsed.get("messages") or []
        raw_text = parsed.get("raw_text")

        if file_conversation_id:
            self.conversation_id = file_conversation_id
            self._sync_conversation_widgets()

        self.history_file_path = Path(file_path)
        self.loaded_history_messages = messages

        self.clear_chat_view()
        if raw_text is not None:
            self._append_chat("Система", f"Загружен текстовый диалог из файла: {self.history_file_path.name}")
            self._append_raw_text(raw_text)
        else:
            self._append_chat(
                "Система",
                f"Загружен диалог из файла: {self.history_file_path.name}. Сообщений: {len(messages)}",
            )
            for item in messages:
                self._append_chat(self._display_role(item.get("role", "assistant")), item.get("content", ""))

        if messages:
            self._append_chat(
                "Система",
                "История из файла будет отправлена вместе со следующим сообщением, чтобы восстановить контекст на сервере.",
            )
        self._set_busy(False, f"Загружен файл: {self.history_file_path.name}")

    def _write_dialog_as_json(self, path: Path) -> None:
        payload = {
            "conversation_id": self.conversation_id,
            "messages": self._messages_for_save(),
            "stats": {
                "request_count": self.request_count,
                "dialog_total_tokens": self.dialog_total_tokens,
                "last_request_total_tokens": self.request_total_tokens,
            },
        }
        with path.open("w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)

    def _write_dialog_as_text(self, path: Path) -> None:
        lines = [f"Conversation ID: {self.conversation_id}", ""]
        for item in self._messages_for_save():
            role = self._display_role(item.get("role", "assistant"))
            content = item.get("content", "").strip()
            lines.append(f"{role}:\n{content}\n")
        with path.open("w", encoding="utf-8") as f:
            f.write("\n".join(lines).strip() + "\n")

    def _messages_for_save(self) -> list[dict[str, str]]:
        messages: list[dict[str, str]] = []
        if self.loaded_history_messages:
            messages.extend(self.loaded_history_messages)
        messages.extend(self.session_messages)
        return messages

    def _read_dialog_file(self, path: Path) -> dict[str, Any]:
        suffix = path.suffix.lower()
        if suffix == ".json":
            with path.open("r", encoding="utf-8") as f:
                data = json.load(f)
            return self._normalize_loaded_json(data)

        with path.open("r", encoding="utf-8") as f:
            raw_text = f.read().strip()
        return {"messages": [], "raw_text": raw_text, "conversation_id": None}

    def _normalize_loaded_json(self, data: Any) -> dict[str, Any]:
        if isinstance(data, list):
            return {
                "conversation_id": None,
                "messages": self._normalize_messages(data),
                "raw_text": None,
            }

        if not isinstance(data, dict):
            raise RuntimeError("JSON-файл должен содержать объект или список сообщений.")

        conversation_id = data.get("conversation_id") or data.get("id") or data.get("chat_id")

        message_candidates = [
            data.get("messages"),
            data.get("history"),
            data.get("dialog"),
            data.get("conversation"),
            data.get("items"),
        ]
        for candidate in message_candidates:
            if isinstance(candidate, list):
                return {
                    "conversation_id": conversation_id,
                    "messages": self._normalize_messages(candidate),
                    "raw_text": None,
                }

        if isinstance(data.get("content"), str):
            return {
                "conversation_id": conversation_id,
                "messages": [],
                "raw_text": data["content"],
            }

        raise RuntimeError(
            "Не удалось распознать формат JSON. Ожидается conversation_id и список messages/history/dialog."
        )

    def _normalize_messages(self, messages: list[Any]) -> list[dict[str, str]]:
        normalized: list[dict[str, str]] = []
        for item in messages:
            if isinstance(item, str):
                normalized.append({"role": "user", "content": item.strip()})
                continue
            if not isinstance(item, dict):
                continue

            role = str(item.get("role") or item.get("author") or item.get("speaker") or "assistant").strip().lower()
            content = self._extract_message_content(item)
            if not content:
                continue
            normalized.append({"role": role, "content": content})
        return normalized

    def _extract_message_content(self, item: dict[str, Any]) -> str:
        content = item.get("content")
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for part in content:
                if isinstance(part, str):
                    parts.append(part)
                elif isinstance(part, dict):
                    text = part.get("text") or part.get("content") or part.get("value")
                    if isinstance(text, str):
                        parts.append(text)
            return "\n".join(part.strip() for part in parts if part and part.strip())

        for key in ("text", "message", "value", "body"):
            value = item.get(key)
            if isinstance(value, str):
                return value.strip()
        return ""

    def _display_role(self, role: str) -> str:
        role_normalized = role.strip().lower()
        mapping = {
            "user": "Вы",
            "assistant": "Ассистент",
            "system": "Система",
            "tool": "Инструмент",
        }
        return mapping.get(role_normalized, role.title())

    def _append_raw_text(self, text: str) -> None:
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{text.strip()}\n\n")
        self.chat_box.see("end")
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

        self.apply_conversation_id()

        messages_payload = []
        if self.loaded_history_messages:
            messages_payload.extend(self.loaded_history_messages)
        messages_payload.append({"role": "user", "content": text})

        payload = {
            "model": self.model_entry.get().strip(),
            "messages": messages_payload,
            "conversation_id": self.conversation_id,
            "use_memory": bool(self.memory_switch.get()),
            "history_limit": history_limit,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "user_id": self.user_id_entry.get().strip() or None,
        }

        self.input_box.delete("1.0", "end")
        self.session_messages.append({"role": "user", "content": text})
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
        self.loaded_history_messages = []

        returned_conversation_id = data.get("conversation_id")
        if returned_conversation_id:
            self.conversation_id = returned_conversation_id
            self._sync_conversation_widgets()

        finish_reason = data.get("finish_reason") or "unknown"
        latency_ms = data.get("latency_ms", "?")
        assistant_text = content or "<пустой ответ>"
        self.session_messages.append({"role": "assistant", "content": assistant_text})
        self._append_chat(
            "Ассистент",
            assistant_text,
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
