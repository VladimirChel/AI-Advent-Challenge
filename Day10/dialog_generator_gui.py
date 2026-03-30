import json
import threading
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
import requests


class LLMClient:
    def __init__(self, base_url: str, timeout: int = 180):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def healthcheck(self):
        resp = requests.get(f"{self.base_url}/health", timeout=10)
        resp.raise_for_status()
        return resp.json() if resp.content else {"status": "ok"}

    def generate(self, model: str, messages: list, max_tokens: int, use_memory: bool = False, memory_strategy: str = "none"):
        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": max_tokens,
            "use_memory": use_memory,
            "memory_strategy": memory_strategy,
        }
        resp = requests.post(
            f"{self.base_url}/generate",
            json=payload,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


class DialogGeneratorApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("Dialog Generator")
        self.geometry("1200x820")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.client = None
        self.generated_dialog_data = None
        self.last_raw_response = None

        self._build_ui()

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # Sidebar
        self.sidebar = ctk.CTkFrame(self, width=340, corner_radius=0)
        self.sidebar.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=0)
        self.sidebar.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            self.sidebar,
            text="Генератор диалогов",
            font=ctk.CTkFont(size=24, weight="bold"),
        ).grid(row=0, column=0, padx=16, pady=(16, 10), sticky="w")

        ctk.CTkLabel(self.sidebar, text="URL шлюза").grid(row=1, column=0, padx=16, pady=(6, 0), sticky="w")
        self.base_url_entry = ctk.CTkEntry(self.sidebar, placeholder_text="http://127.0.0.1:8000")
        self.base_url_entry.grid(row=2, column=0, padx=16, pady=6, sticky="ew")
        self.base_url_entry.insert(0, "http://127.0.0.1:8000")

        ctk.CTkLabel(self.sidebar, text="Модель").grid(row=3, column=0, padx=16, pady=(6, 0), sticky="w")
        self.model_entry = ctk.CTkEntry(self.sidebar, placeholder_text="openai/gpt-4o-mini")
        self.model_entry.grid(row=4, column=0, padx=16, pady=6, sticky="ew")
        self.model_entry.insert(0, "openai/gpt-4o-mini")

        ctk.CTkLabel(self.sidebar, text="Тема / задача").grid(row=5, column=0, padx=16, pady=(10, 0), sticky="w")
        self.topic_box = ctk.CTkTextbox(self.sidebar, height=90)
        self.topic_box.grid(row=6, column=0, padx=16, pady=6, sticky="ew")
        self.topic_box.insert("1.0", "Сделай живой диалог между клиентом и менеджером о выборе ноутбука.")

        ctk.CTkLabel(self.sidebar, text="Участники").grid(row=7, column=0, padx=16, pady=(10, 0), sticky="w")
        self.participants_box = ctk.CTkTextbox(self.sidebar, height=80)
        self.participants_box.grid(row=8, column=0, padx=16, pady=6, sticky="ew")
        self.participants_box.insert("1.0", "Клиент\nМенеджер")

        controls = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        controls.grid(row=9, column=0, padx=16, pady=(8, 6), sticky="ew")
        controls.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkLabel(controls, text="Реплик").grid(row=0, column=0, sticky="w")
        self.turns_entry = ctk.CTkEntry(controls, width=120)
        self.turns_entry.grid(row=1, column=0, padx=(0, 8), pady=4, sticky="ew")
        self.turns_entry.insert(0, "10")

        ctk.CTkLabel(controls, text="Стиль").grid(row=0, column=1, sticky="w")
        self.style_entry = ctk.CTkEntry(controls)
        self.style_entry.grid(row=1, column=1, pady=4, sticky="ew")
        self.style_entry.insert(0, "естественный, реалистичный")

        ctk.CTkLabel(self.sidebar, text="Доп. инструкции").grid(row=10, column=0, padx=16, pady=(10, 0), sticky="w")
        self.instructions_box = ctk.CTkTextbox(self.sidebar, height=140)
        self.instructions_box.grid(row=11, column=0, padx=16, pady=6, sticky="nsew")
        self.instructions_box.insert(
            "1.0",
            "Сгенерируй законченный диалог. Верни строго JSON формата:\n"
            "{\n"
            '  "title": "Название",\n'
            '  "summary": "Краткое описание",\n'
            '  "dialog": [\n'
            '    {"speaker": "Имя", "text": "Реплика"}\n'
            "  ]\n"
            "}\n"
            "Без markdown и без пояснений вне JSON."
        )
        self.sidebar.grid_rowconfigure(11, weight=1)

        buttons = ctk.CTkFrame(self.sidebar, fg_color="transparent")
        buttons.grid(row=12, column=0, padx=16, pady=(10, 10), sticky="ew")
        buttons.grid_columnconfigure((0, 1), weight=1)

        self.check_button = ctk.CTkButton(buttons, text="Проверить API", command=self.check_connection)
        self.check_button.grid(row=0, column=0, padx=(0, 6), pady=4, sticky="ew")

        self.generate_button = ctk.CTkButton(buttons, text="Сгенерировать", command=self.generate_dialog)
        self.generate_button.grid(row=0, column=1, padx=(6, 0), pady=4, sticky="ew")

        self.clear_button = ctk.CTkButton(buttons, text="Очистить", command=self.clear_result)
        self.clear_button.grid(row=1, column=0, padx=(0, 6), pady=4, sticky="ew")

        self.save_button = ctk.CTkButton(buttons, text="Сохранить JSON", command=self.save_json)
        self.save_button.grid(row=1, column=1, padx=(6, 0), pady=4, sticky="ew")

        self.status_label = ctk.CTkLabel(self.sidebar, text="Статус: готов", anchor="w")
        self.status_label.grid(row=13, column=0, padx=16, pady=(0, 16), sticky="ew")

        # Main area
        self.main_frame = ctk.CTkFrame(self)
        self.main_frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=8)
        self.main_frame.grid_columnconfigure(0, weight=1)
        self.main_frame.grid_rowconfigure(1, weight=1)

        self.meta_label = ctk.CTkLabel(
            self.main_frame,
            text="Здесь появится сгенерированный диалог",
            anchor="w",
            font=ctk.CTkFont(size=16, weight="bold"),
        )
        self.meta_label.grid(row=0, column=0, padx=10, pady=(10, 4), sticky="ew")

        self.result_box = ctk.CTkTextbox(self.main_frame, wrap="word")
        self.result_box.grid(row=1, column=0, padx=10, pady=(4, 10), sticky="nsew")

    def set_status(self, text: str):
        self.status_label.configure(text=f"Статус: {text}")

    def get_client(self):
        base_url = self.base_url_entry.get().strip()
        if not base_url:
            raise ValueError("Укажите URL шлюза.")
        self.client = LLMClient(base_url=base_url)
        return self.client

    def check_connection(self):
        def worker():
            try:
                data = self.get_client().healthcheck()
                self.after(0, lambda: self.set_status(f"API доступен ({data})"))
            except Exception as e:
                self.after(0, lambda: self.set_status(f"ошибка подключения: {e}"))
                self.after(0, lambda: messagebox.showerror("Ошибка подключения", str(e)))

        threading.Thread(target=worker, daemon=True).start()

    def build_prompt_messages(self):
        topic = self.topic_box.get("1.0", "end").strip()
        participants_raw = self.participants_box.get("1.0", "end").strip()
        participants = [x.strip() for x in participants_raw.splitlines() if x.strip()]
        turns = self.turns_entry.get().strip() or "10"
        style = self.style_entry.get().strip() or "естественный"
        extra = self.instructions_box.get("1.0", "end").strip()

        if not topic:
            raise ValueError("Заполните поле 'Тема / задача'.")

        participants_text = ", ".join(participants) if participants else "не указаны"

        system_message = {
            "role": "system",
            "content": (
                "Ты создаёшь законченные диалоги по заданию пользователя. "
                "Нужно вернуть только валидный JSON без markdown, комментариев и пояснений."
            ),
        }

        user_message = {
            "role": "user",
            "content": (
                f"Тема: {topic}\n"
                f"Участники: {participants_text}\n"
                f"Количество реплик: {turns}\n"
                f"Стиль: {style}\n\n"
                f"{extra}"
            ),
        }
        return [system_message, user_message]

    def extract_dialog_json(self, content: str):
        content = content.strip()

        # попытка прямого JSON
        try:
            return json.loads(content)
        except Exception:
            pass

        # попытка вытащить JSON из текста
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = content[start:end + 1]
            return json.loads(candidate)

        raise ValueError("LLM не вернула корректный JSON.")

    def render_dialog(self, data: dict):
        title = data.get("title", "Без названия")
        summary = data.get("summary", "")
        dialog = data.get("dialog", [])

        self.result_box.delete("1.0", "end")
        self.result_box.insert("end", f"{title}\n")
        self.result_box.insert("end", "=" * len(title) + "\n\n")

        if summary:
            self.result_box.insert("end", f"{summary}\n\n")

        for item in dialog:
            speaker = item.get("speaker", "Unknown")
            text = item.get("text", "")
            self.result_box.insert("end", f"{speaker}: {text}\n\n")

        self.meta_label.configure(
            text=f"{title} | реплик: {len(dialog)}"
        )

    def generate_dialog(self):
        self.generate_button.configure(state="disabled")
        self.set_status("генерация...")

        def worker():
            try:
                client = self.get_client()
                messages = self.build_prompt_messages()

                response = client.generate(
                    model=self.model_entry.get().strip() or "openai/gpt-4o-mini",
                    messages=messages,
                    use_memory=False,
                    max_tokens = 2000,
                    memory_strategy="none",
                )

                raw_content = response.get("content", "").strip()
                if not raw_content:
                    raise ValueError("Пустой ответ от LLM.")

                parsed = self.extract_dialog_json(raw_content)

                self.generated_dialog_data = {
                    "saved_at": None,
                    "base_url": self.base_url_entry.get().strip(),
                    "model": self.model_entry.get().strip(),
                    "request": {
                        "topic": self.topic_box.get("1.0", "end").strip(),
                        "participants": [x.strip() for x in self.participants_box.get("1.0", "end").splitlines() if x.strip()],
                        "turns": self.turns_entry.get().strip(),
                        "style": self.style_entry.get().strip(),
                        "instructions": self.instructions_box.get("1.0", "end").strip(),
                    },
                    "response": parsed,
                    "meta": {
                        "conversation_id": response.get("conversation_id"),
                        "latency_ms": response.get("latency_ms"),
                        "usage": response.get("usage", {}),
                    },
                }
                self.last_raw_response = response

                def update_ui():
                    self.render_dialog(parsed)
                    self.set_status(
                        f"готово | latency={response.get('latency_ms')} ms | usage={response.get('usage', {})}"
                    )
                    self.generate_button.configure(state="normal")

                self.after(0, update_ui)

            except Exception as e:
                def show_error():
                    self.set_status(f"ошибка: {e}")
                    self.generate_button.configure(state="normal")
                    messagebox.showerror("Ошибка генерации", str(e))

                self.after(0, show_error)

        threading.Thread(target=worker, daemon=True).start()

    def clear_result(self):
        self.generated_dialog_data = None
        self.last_raw_response = None
        self.result_box.delete("1.0", "end")
        self.meta_label.configure(text="Здесь появится сгенерированный диалог")
        self.set_status("очищено")

    def save_json(self):
        if not self.generated_dialog_data:
            messagebox.showinfo("Сохранение", "Сначала сгенерируйте диалог.")
            return

        payload = dict(self.generated_dialog_data)
        payload["saved_at"] = datetime.now().isoformat()

        title = payload.get("response", {}).get("title", "dialog")
        safe_title = "".join(ch if ch.isalnum() or ch in ("_", "-") else "_" for ch in title).strip("_") or "dialog"

        file_path = filedialog.asksaveasfilename(
            title="Сохранить диалог в JSON",
            defaultextension=".json",
            initialfile=f"{safe_title}.json",
            filetypes=[("JSON files", "*.json")],
        )
        if not file_path:
            return

        Path(file_path).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.set_status(f"сохранено: {file_path}")
        messagebox.showinfo("Сохранение", "Диалог сохранён в JSON.")

if __name__ == "__main__":
    app = DialogGeneratorApp()
    app.mainloop()
