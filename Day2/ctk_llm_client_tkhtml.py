import json
import threading
from datetime import datetime

import customtkinter as ctk
import markdown
import requests
from tkhtmlview import HTMLScrolledText
from tkinter import messagebox


MODEL_OPTIONS = [
    "openai/gpt-5-mini",
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-3-5-sonnet-20241022",
    "google/gemini-2.0-flash",
    "google/gemini-1.5-pro",
]


class LLMClientApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("LLM Gateway Client")
        self.geometry("1280x840")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.show_hints_var = ctk.BooleanVar(value=False)

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0)
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.sidebar = ctk.CTkScrollableFrame(self, width=335, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew")
        self.sidebar.grid_columnconfigure(0, weight=1)

        self.main = ctk.CTkFrame(self, corner_radius=0)
        self.main.grid(row=0, column=1, sticky="nsew", padx=10, pady=10)
        self.main.grid_columnconfigure(0, weight=1)
        self.main.grid_rowconfigure(4, weight=1)

        row = 0

        ctk.CTkLabel(
            self.sidebar,
            text="Параметры запроса",
            font=ctk.CTkFont(size=20, weight="bold")
        ).grid(row=row, column=0, sticky="w", padx=12, pady=(10, 4))
        row += 1

        self.hints_checkbox = ctk.CTkCheckBox(
            self.sidebar,
            text="Показывать подсказки",
            variable=self.show_hints_var,
            command=self.refresh_hints_visibility
        )
        self.hints_checkbox.grid(row=row, column=0, sticky="w", padx=12, pady=(0, 6))
        row += 1

        self.endpoint_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Адрес API (/generate)",
            "Пример: http://127.0.0.1:8000/generate",
            "http://127.0.0.1:8000/generate"
        )
        row += 1

        self.model_combo = self._labeled_combobox(
            self.sidebar,
            row,
            "Модель",
            "Формат provider/model",
            MODEL_OPTIONS,
            "openai/gpt-5-mini"
        )
        row += 1

        self.temperature_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Temperature",
            "0.0–0.3 для точности, 0.7+ для креатива",
            "0.2"
        )
        row += 1

        self.max_tokens_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Max tokens",
            "Максимальная длина ответа",
            "2000"
        )
        row += 1

        self.top_p_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Top P",
            "Обычно оставляют 1.0",
            "1.0"
        )
        row += 1

        self.presence_penalty_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Presence penalty",
            "Штраф за повтор тем",
            "0.0"
        )
        row += 1

        self.frequency_penalty_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Frequency penalty",
            "Штраф за повторы слов",
            "0.0"
        )
        row += 1

        self.user_id_entry = self._labeled_entry(
            self.sidebar,
            row,
            "User ID",
            "Идентификатор пользователя или сессии",
            ""
        )
        row += 1

        ctk.CTkLabel(
            self.sidebar,
            text="Проверка ответа",
            font=ctk.CTkFont(size=17, weight="bold")
        ).grid(row=row, column=0, sticky="w", padx=12, pady=(10, 4))
        row += 1

        self.min_length_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Мин. длина ответа",
            "Минимум символов",
            ""
        )
        row += 1

        self.must_contain_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Обязательные фразы",
            "Разделяйте через ;",
            ""
        )
        row += 1

        self.forbid_phrases_entry = self._labeled_entry(
            self.sidebar,
            row,
            "Запрещённые фразы",
            "Разделяйте через ;",
            ""
        )
        row += 1

        self.require_json_var = ctk.BooleanVar(value=False)
        self.require_json_checkbox = ctk.CTkCheckBox(
            self.sidebar,
            text="Ответ должен быть валидным JSON",
            variable=self.require_json_var
        )
        self.require_json_checkbox.grid(row=row, column=0, sticky="w", padx=12, pady=(4, 8))
        row += 1

        ctk.CTkLabel(
            self.main,
            text="Сообщения для модели",
            font=ctk.CTkFont(size=22, weight="bold")
        ).grid(row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self.prompts_frame = ctk.CTkFrame(self.main)
        self.prompts_frame.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.prompts_frame.grid_columnconfigure(0, weight=1)
        self.prompts_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            self.prompts_frame,
            text="System prompt — системная инструкция"
        ).grid(row=0, column=0, sticky="w", padx=12, pady=(8, 3))

        ctk.CTkLabel(
            self.prompts_frame,
            text="User prompt — запрос пользователя"
        ).grid(row=0, column=1, sticky="w", padx=12, pady=(8, 3))

        self.system_text = ctk.CTkTextbox(self.prompts_frame, height=170, wrap="word")
        self.system_text.grid(row=1, column=0, sticky="nsew", padx=(12, 6), pady=(0, 10))
        self.system_text.insert("1.0", "Отвечай кратко и по делу.")

        self.user_text = ctk.CTkTextbox(self.prompts_frame, height=170, wrap="word")
        self.user_text.grid(row=1, column=1, sticky="nsew", padx=(6, 12), pady=(0, 10))
        self.user_text.insert("1.0", "Объясни, что такое FastAPI.")

        self.actions_frame = ctk.CTkFrame(self.main)
        self.actions_frame.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 10))
        self.actions_frame.grid_columnconfigure((0, 1, 2), weight=1)

        self.check_health_button = ctk.CTkButton(
            self.actions_frame,
            text="Проверить /health",
            command=self.check_health
        )
        self.check_health_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=8)

        self.send_button = ctk.CTkButton(
            self.actions_frame,
            text="Отправить запрос",
            height=40,
            command=self.send_request
        )
        self.send_button.grid(row=0, column=1, sticky="ew", padx=6, pady=8)

        self.clear_button = ctk.CTkButton(
            self.actions_frame,
            text="Очистить ответ",
            fg_color="gray30",
            hover_color="gray20",
            command=self.clear_output
        )
        self.clear_button.grid(row=0, column=2, sticky="ew", padx=(6, 0), pady=8)

        self.status_var = ctk.StringVar(value="Готово")
        self.status_label = ctk.CTkLabel(self.main, textvariable=self.status_var)
        self.status_label.grid(row=3, column=0, sticky="w", padx=16, pady=(0, 8))

        self.tabs = ctk.CTkTabview(self.main)
        self.tabs.grid(row=4, column=0, sticky="nsew", padx=16, pady=(0, 16))

        self.tabs.add("Ответ")
        self.tabs.add("Метаданные")
        self.tabs.add("JSON запроса")

        self.response_html = HTMLScrolledText(self.tabs.tab("Ответ"), html="<p>Здесь появится ответ модели.</p>")
        self.response_html.pack(fill="both", expand=True, padx=10, pady=10)

        self.meta_text = ctk.CTkTextbox(self.tabs.tab("Метаданные"), wrap="word")
        self.meta_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.request_json_text = ctk.CTkTextbox(self.tabs.tab("JSON запроса"), wrap="word")
        self.request_json_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.refresh_hints_visibility()
        self.bind_all("<MouseWheel>", self._on_mousewheel_windows)

    def _on_mousewheel_windows(self, event):
        try:
            widget = self.winfo_containing(event.x_root, event.y_root)
            if widget and str(widget).startswith(str(self.sidebar)):
                self.sidebar._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        except Exception:
            pass

    def _labeled_entry(self, parent, row, label, hint, default_value):
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.grid(row=row, column=0, sticky="ew", padx=12, pady=(2, 3))
        wrapper.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrapper,
            text=label,
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        hint_label = ctk.CTkLabel(
            wrapper,
            text=hint,
            justify="left",
            wraplength=250,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70")
        )
        hint_label.grid(row=1, column=0, sticky="w", pady=(0, 2))
        wrapper.hint_label = hint_label

        entry = ctk.CTkEntry(wrapper, height=28)
        entry.grid(row=2, column=0, sticky="ew")
        if default_value:
            entry.insert(0, default_value)
        return entry

    def _labeled_combobox(self, parent, row, label, hint, values, default_value):
        wrapper = ctk.CTkFrame(parent, fg_color="transparent")
        wrapper.grid(row=row, column=0, sticky="ew", padx=12, pady=(2, 3))
        wrapper.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            wrapper,
            text=label,
            font=ctk.CTkFont(size=12, weight="bold")
        ).grid(row=0, column=0, sticky="w")

        hint_label = ctk.CTkLabel(
            wrapper,
            text=hint,
            justify="left",
            wraplength=250,
            font=ctk.CTkFont(size=11),
            text_color=("gray35", "gray70")
        )
        hint_label.grid(row=1, column=0, sticky="w", pady=(0, 2))
        wrapper.hint_label = hint_label

        combo = ctk.CTkComboBox(wrapper, values=values, height=28)
        combo.grid(row=2, column=0, sticky="ew")
        combo.set(default_value)
        return combo

    def refresh_hints_visibility(self):
        show = self.show_hints_var.get()
        for child in self.sidebar.winfo_children():
            hint_label = getattr(child, "hint_label", None)
            if hint_label is not None:
                if show:
                    hint_label.grid()
                else:
                    hint_label.grid_remove()

    def clear_output(self):
        self.meta_text.delete("1.0", "end")
        self.request_json_text.delete("1.0", "end")
        self.response_html.set_html("<p>Поле ответа очищено.</p>")
        self.status_var.set("Поля ответа очищены")

    def set_busy(self, busy: bool, text: str):
        state = "disabled" if busy else "normal"
        self.send_button.configure(state=state)
        self.check_health_button.configure(state=state)
        self.clear_button.configure(state=state)
        self.status_var.set(text)

    def build_payload(self):
        system_prompt = self.system_text.get("1.0", "end").strip()
        user_prompt = self.user_text.get("1.0", "end").strip()

        if not user_prompt:
            raise ValueError("Поле 'User prompt' не должно быть пустым")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_prompt})

        payload = {
            "model": self.model_combo.get().strip(),
            "messages": messages,
            "temperature": float(self.temperature_entry.get().strip() or "0.2"),
            "max_tokens": int(self.max_tokens_entry.get().strip() or "300"),
            "top_p": float(self.top_p_entry.get().strip() or "1.0"),
            "presence_penalty": float(self.presence_penalty_entry.get().strip() or "0.0"),
            "frequency_penalty": float(self.frequency_penalty_entry.get().strip() or "0.0"),
        }

        user_id = self.user_id_entry.get().strip()
        if user_id:
            payload["user_id"] = user_id

        validation = {
            "must_contain": [
                item.strip()
                for item in self.must_contain_entry.get().split(";")
                if item.strip()
            ],
            "forbid_phrases": [
                item.strip()
                for item in self.forbid_phrases_entry.get().split(";")
                if item.strip()
            ],
            "require_json": self.require_json_var.get(),
        }

        min_length = self.min_length_entry.get().strip()
        if min_length:
            validation["min_output_length"] = int(min_length)

        if (
            validation.get("must_contain")
            or validation.get("forbid_phrases")
            or validation.get("require_json")
            or validation.get("min_output_length")
        ):
            payload["validation"] = validation

        return payload

    def render_response(self, content: str):
        text = content or "<пустой ответ>"
        html = markdown.markdown(
            text,
            extensions=["fenced_code", "tables", "nl2br", "sane_lists"]
        )
        html = f"""
        <html>
          <body style="font-family: Segoe UI, Arial, sans-serif; padding: 8px;">
            {html}
          </body>
        </html>
        """
        self.response_html.set_html(html)

    def check_health(self):
        def worker():
            try:
                self.after(0, lambda: self.set_busy(True, "Проверка /health..."))
                generate_url = self.endpoint_entry.get().strip()
                if not generate_url:
                    raise ValueError("Не указан адрес API")

                if generate_url.endswith("/generate"):
                    health_url = generate_url[:-len("/generate")] + "/health"
                else:
                    health_url = generate_url + "/health"

                response = requests.get(health_url, timeout=15)
                response.raise_for_status()
                data = response.json()

                pretty = json.dumps(data, ensure_ascii=False, indent=2)
                self.after(0, lambda: self.meta_text.delete("1.0", "end"))
                self.after(0, lambda: self.meta_text.insert("1.0", pretty))
                self.after(0, lambda: self.tabs.set("Метаданные"))
                self.after(0, lambda: self.set_busy(False, "Сервер доступен"))
            except Exception as exc:
                self.after(0, lambda: self.set_busy(False, f"Ошибка проверки: {exc}"))
                self.after(0, lambda: messagebox.showerror("Ошибка", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def send_request(self):
        try:
            payload = self.build_payload()
        except Exception as exc:
            messagebox.showerror("Ошибка в параметрах", str(exc))
            return

        self.request_json_text.delete("1.0", "end")
        self.request_json_text.insert("1.0", json.dumps(payload, ensure_ascii=False, indent=2))
        self.tabs.set("JSON запроса")

        def worker():
            try:
                self.after(0, lambda: self.set_busy(True, "Отправка запроса..."))
                url = self.endpoint_entry.get().strip()
                if not url:
                    raise ValueError("Не указан адрес API")

                started = datetime.now()
                response = requests.post(url, json=payload, timeout=120)
                elapsed = (datetime.now() - started).total_seconds()

                response.raise_for_status()
                data = response.json()

                content = data.get("content", "")
                meta = {
                    "http_status": response.status_code,
                    "request_id": data.get("request_id"),
                    "model": data.get("model"),
                    "finish_reason": data.get("finish_reason"),
                    "latency_ms": data.get("latency_ms"),
                    "usage": data.get("usage"),
                    "validation": data.get("validation"),
                    "raw_response_id": data.get("raw_response_id"),
                    "client_elapsed_seconds": round(elapsed, 3),
                    "headers": dict(response.headers),
                }

                self.after(0, lambda: self.render_response(content))
                self.after(0, lambda: self.meta_text.delete("1.0", "end"))
                self.after(0, lambda: self.meta_text.insert("1.0", json.dumps(meta, ensure_ascii=False, indent=2)))
                self.after(0, lambda: self.tabs.set("Ответ"))
                self.after(0, lambda: self.set_busy(False, "Запрос выполнен"))
            except requests.HTTPError as exc:
                body = ""
                try:
                    body = exc.response.text
                except Exception:
                    pass
                err = f"{exc}\n\n{body}" if body else str(exc)
                self.after(0, lambda: self.set_busy(False, "HTTP ошибка"))
                self.after(0, lambda: messagebox.showerror("HTTP ошибка", err))
            except Exception as exc:
                self.after(0, lambda: self.set_busy(False, f"Ошибка: {exc}"))
                self.after(0, lambda: messagebox.showerror("Ошибка", str(exc)))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = LLMClientApp()
    app.mainloop()
