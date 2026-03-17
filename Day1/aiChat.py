import json
import os
import threading
import requests
import customtkinter as ctk
from tkinter import messagebox

CONFIG_FILE = "config.json"

OPENAI_BASE_URL = "https://api.proxyapi.ru/openai/v1"
OPENROUTER_BASE_URL = "https://api.proxyapi.ru/openrouter/v1"

MODEL_GROUPS = {
    "OpenAI": [
        "gpt-4o",
        "gpt-4o-mini",
        "gpt-4.1",
        "gpt-4.1-mini",
        "gpt-4.1-nano",
        "gpt-3.5-turbo",
    ],
    "OpenRouter": [
        "mistralai/mistral-medium-3.1",
        "mistralai/mistral-small-3.1-24b-instruct",
        "meta-llama/llama-3.1-8b-instruct",
        "meta-llama/llama-3.1-70b-instruct",
        "qwen/qwen-2.5-72b-instruct",
    ],
}

DEFAULT_CONFIG = {
    "api_key": "",
    "provider": "OpenAI",
    "base_url": OPENAI_BASE_URL,
    "model": "gpt-4o-mini",
}


class ChatApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.title("AI Chat")
        self.geometry("1000x700")
        self.minsize(900, 650)

        self.messages = []
        self.config_data = self.load_config()

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.tabview = ctk.CTkTabview(self)
        self.tabview.grid(row=0, column=0, sticky="nsew", padx=12, pady=12)

        self.tab_chat = self.tabview.add("Чат")
        self.tab_settings = self.tabview.add("Настройки")

        self.build_chat_tab()
        self.build_settings_tab()

        self.current_model_label.configure(
            text=f"{self.config_data['provider']} / {self.config_data['model']}"
        )

        self.append_chat(
            "Система",
            "Приложение запущено. Введите сообщение или откройте вкладку «Настройки»."
        )

    def detect_provider_by_model(self, model: str) -> str:
        for provider, models in MODEL_GROUPS.items():
            if model in models:
                return provider
        return "OpenAI"

    def get_base_url_by_provider(self, provider: str) -> str:
        if provider == "OpenRouter":
            return OPENROUTER_BASE_URL
        return OPENAI_BASE_URL

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)

                model = data.get("model", DEFAULT_CONFIG["model"])
                provider = data.get("provider")

                if not provider:
                    provider = self.detect_provider_by_model(model)

                if provider not in MODEL_GROUPS:
                    provider = DEFAULT_CONFIG["provider"]

                provider_models = MODEL_GROUPS[provider]
                if model not in provider_models:
                    model = provider_models[0]

                base_url = data.get("base_url")
                expected_base_url = self.get_base_url_by_provider(provider)

                if not base_url:
                    base_url = expected_base_url

                return {
                    "api_key": data.get("api_key", DEFAULT_CONFIG["api_key"]),
                    "provider": provider,
                    "base_url": expected_base_url,
                    "model": model,
                }
            except Exception:
                return DEFAULT_CONFIG.copy()

        return DEFAULT_CONFIG.copy()

    def save_config(self):
        provider = self.provider_menu.get()
        model = self.model_menu.get()
        base_url = self.get_base_url_by_provider(provider)

        self.config_data["api_key"] = self.api_key_entry.get().strip()
        self.config_data["provider"] = provider
        self.config_data["model"] = model
        self.config_data["base_url"] = base_url

        try:
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(self.config_data, f, ensure_ascii=False, indent=2)

            self.update_base_url_entry(base_url)
            messagebox.showinfo("Успех", "Настройки сохранены")
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось сохранить настройки:\n{e}")

    def build_chat_tab(self):
        self.tab_chat.grid_columnconfigure(0, weight=1)
        self.tab_chat.grid_rowconfigure(1, weight=1)

        top_frame = ctk.CTkFrame(self.tab_chat)
        top_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 6))
        top_frame.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(
            top_frame,
            text="Текущая модель:",
            font=ctk.CTkFont(size=14, weight="bold")
        ).grid(row=0, column=0, padx=(10, 5), pady=10, sticky="w")

        self.current_model_label = ctk.CTkLabel(
            top_frame,
            text="",
            font=ctk.CTkFont(size=14),
        )
        self.current_model_label.grid(row=0, column=1, padx=5, pady=10, sticky="w")

        self.chat_box = ctk.CTkTextbox(self.tab_chat, wrap="word", font=("Arial", 15))
        self.chat_box.grid(row=1, column=0, sticky="nsew", padx=10, pady=6)
        self.chat_box.configure(state="disabled")

        bottom_frame = ctk.CTkFrame(self.tab_chat)
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=(6, 10))
        bottom_frame.grid_columnconfigure(0, weight=1)

        self.input_box = ctk.CTkTextbox(bottom_frame, height=110, wrap="word", font=("Arial", 15))
        self.input_box.grid(row=0, column=0, columnspan=3, sticky="ew", padx=10, pady=10)

        self.send_button = ctk.CTkButton(bottom_frame, text="Отправить", command=self.send_message)
        self.send_button.grid(row=1, column=1, padx=10, pady=(0, 10), sticky="e")

        self.clear_button = ctk.CTkButton(bottom_frame, text="Очистить чат", command=self.clear_chat)
        self.clear_button.grid(row=1, column=2, padx=(0, 10), pady=(0, 10), sticky="e")

    def build_settings_tab(self):
        self.tab_settings.grid_columnconfigure(1, weight=1)

        row = 0

        ctk.CTkLabel(self.tab_settings, text="API Key").grid(
            row=row, column=0, padx=15, pady=(20, 8), sticky="w"
        )
        self.api_key_entry = ctk.CTkEntry(self.tab_settings, show="*", width=500)
        self.api_key_entry.grid(row=row, column=1, padx=15, pady=(20, 8), sticky="ew")
        self.api_key_entry.insert(0, self.config_data["api_key"])

        row += 1
        ctk.CTkLabel(self.tab_settings, text="Base URL").grid(
            row=row, column=0, padx=15, pady=8, sticky="w"
        )
        self.base_url_entry = ctk.CTkEntry(self.tab_settings, width=500)
        self.base_url_entry.grid(row=row, column=1, padx=15, pady=8, sticky="ew")
        self.update_base_url_entry(self.config_data["base_url"])

        row += 1
        ctk.CTkLabel(self.tab_settings, text="Провайдер").grid(
            row=row, column=0, padx=15, pady=8, sticky="w"
        )
        self.provider_menu = ctk.CTkOptionMenu(
            self.tab_settings,
            values=list(MODEL_GROUPS.keys()),
            width=500,
            command=self.on_provider_changed
        )
        self.provider_menu.grid(row=row, column=1, padx=15, pady=8, sticky="w")
        self.provider_menu.set(self.config_data["provider"])

        row += 1
        ctk.CTkLabel(self.tab_settings, text="Модель").grid(
            row=row, column=0, padx=15, pady=8, sticky="w"
        )
        provider_models = MODEL_GROUPS[self.config_data["provider"]]
        self.model_menu = ctk.CTkOptionMenu(
            self.tab_settings,
            values=provider_models,
            width=500
        )
        self.model_menu.grid(row=row, column=1, padx=15, pady=8, sticky="w")

        if self.config_data["model"] in provider_models:
            self.model_menu.set(self.config_data["model"])
        else:
            self.model_menu.set(provider_models[0])

        row += 1
        button_frame = ctk.CTkFrame(self.tab_settings)
        button_frame.grid(row=row, column=0, columnspan=2, sticky="ew", padx=15, pady=20)
        button_frame.grid_columnconfigure((0, 1, 2), weight=1)

        save_btn = ctk.CTkButton(button_frame, text="Сохранить", command=self.on_save_clicked)
        save_btn.grid(row=0, column=0, padx=10, pady=10)

        test_btn = ctk.CTkButton(button_frame, text="Проверить подключение", command=self.test_connection)
        test_btn.grid(row=0, column=1, padx=10, pady=10)

        show_btn = ctk.CTkButton(
            button_frame,
            text="Показать / скрыть ключ",
            command=self.toggle_api_key_visibility
        )
        show_btn.grid(row=0, column=2, padx=10, pady=10)

        row += 1
        info_text = (
            "Base URL выбирается автоматически:\n"
            "• OpenAI → https://api.proxyapi.ru/openai/v1\n"
            "• OpenRouter → https://api.proxyapi.ru/openrouter/v1\n"
            "После смены провайдера список моделей обновляется автоматически."
        )

        self.info_label = ctk.CTkLabel(
            self.tab_settings,
            text=info_text,
            justify="left",
            anchor="w"
        )
        self.info_label.grid(row=row, column=0, columnspan=2, padx=15, pady=(5, 15), sticky="w")

    def update_base_url_entry(self, url: str):
        self.base_url_entry.configure(state="normal")
        self.base_url_entry.delete(0, "end")
        self.base_url_entry.insert(0, url)
        self.base_url_entry.configure(state="disabled")

    def on_provider_changed(self, selected_provider):
        models = MODEL_GROUPS[selected_provider]
        self.model_menu.configure(values=models)
        self.model_menu.set(models[0])

        base_url = self.get_base_url_by_provider(selected_provider)
        self.update_base_url_entry(base_url)

    def toggle_api_key_visibility(self):
        current = self.api_key_entry.cget("show")
        self.api_key_entry.configure(show="" if current == "*" else "*")

    def on_save_clicked(self):
        self.save_config()
        self.current_model_label.configure(
            text=f"{self.provider_menu.get()} / {self.model_menu.get()}"
        )

    def append_chat(self, role, text):
        self.chat_box.configure(state="normal")
        self.chat_box.insert("end", f"{role}:\n{text}\n\n")
        self.chat_box.see("end")
        self.chat_box.configure(state="disabled")

    def clear_chat(self):
        self.messages = []
        self.chat_box.configure(state="normal")
        self.chat_box.delete("1.0", "end")
        self.chat_box.configure(state="disabled")
        self.append_chat("Система", "История чата очищена.")

    def get_request_headers(self):
        return {
            "Authorization": f"Bearer {self.config_data['api_key']}",
            "Content-Type": "application/json",
        }

    def sync_config_from_ui(self):
        self.config_data["api_key"] = self.api_key_entry.get().strip()
        self.config_data["provider"] = self.provider_menu.get()
        self.config_data["model"] = self.model_menu.get()
        self.config_data["base_url"] = self.get_base_url_by_provider(self.config_data["provider"])

        self.update_base_url_entry(self.config_data["base_url"])
        self.current_model_label.configure(
            text=f"{self.config_data['provider']} / {self.config_data['model']}"
        )

    def send_message(self):
        user_text = self.input_box.get("1.0", "end").strip()

        if not user_text:
            return

        self.sync_config_from_ui()

        if not self.config_data["api_key"]:
            messagebox.showwarning("Нет API ключа", "Укажите API ключ во вкладке «Настройки».")
            return

        self.append_chat("Вы", user_text)
        self.input_box.delete("1.0", "end")

        self.messages.append({"role": "user", "content": user_text})

        self.send_button.configure(state="disabled", text="Отправка...")
        thread = threading.Thread(target=self._send_request_thread, daemon=True)
        thread.start()

    def _send_request_thread(self):
        url = f"{self.config_data['base_url']}/chat/completions"

        payload = {
            "model": self.config_data["model"],
            "messages": self.messages,
            "temperature": 0.7,
        }

        try:
            response = requests.post(
                url,
                headers=self.get_request_headers(),
                json=payload,
                timeout=120,
            )

            if response.status_code != 200:
                error_text = self.extract_error_text(response)
                self.after(
                    0,
                    lambda: self.append_chat("Ошибка", f"HTTP {response.status_code}\n{error_text}")
                )
                self.after(0, lambda: self.send_button.configure(state="normal", text="Отправить"))
                return

            data = response.json()
            assistant_text = self.extract_assistant_text(data)

            if not assistant_text:
                assistant_text = "Пустой ответ от сервера."

            self.messages.append({"role": "assistant", "content": assistant_text})
            self.after(0, lambda: self.append_chat("Нейросеть", assistant_text))

        except requests.exceptions.RequestException as e:
            self.after(0, lambda: self.append_chat("Ошибка", f"Ошибка сети:\n{e}"))
        except Exception as e:
            self.after(0, lambda: self.append_chat("Ошибка", f"Неожиданная ошибка:\n{e}"))
        finally:
            self.after(0, lambda: self.send_button.configure(state="normal", text="Отправить"))

    def extract_assistant_text(self, data):
        try:
            content = data["choices"][0]["message"]["content"]

            if isinstance(content, str):
                return content

            if isinstance(content, list):
                parts = []
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and "text" in item:
                            parts.append(item["text"])
                        elif "content" in item and isinstance(item["content"], str):
                            parts.append(item["content"])
                return "\n".join(parts).strip()

            return str(content)
        except Exception:
            return ""

    def extract_error_text(self, response):
        try:
            data = response.json()
            if isinstance(data, dict):
                if "error" in data:
                    if isinstance(data["error"], dict):
                        return data["error"].get("message", str(data["error"]))
                    return str(data["error"])
                return json.dumps(data, ensure_ascii=False, indent=2)
        except Exception:
            pass
        return response.text

    def test_connection(self):
        self.sync_config_from_ui()

        if not self.config_data["api_key"]:
            messagebox.showwarning("Ошибка", "Введите API ключ")
            return

        def worker():
            url = f"{self.config_data['base_url']}/chat/completions"
            payload = {
                "model": self.config_data["model"],
                "messages": [{"role": "user", "content": "Привет"}],
                "max_tokens": 20,
            }

            try:
                response = requests.post(
                    url,
                    headers=self.get_request_headers(),
                    json=payload,
                    timeout=60,
                )

                if response.status_code == 200:
                    self.after(0, lambda: messagebox.showinfo("Успех", "Подключение работает"))
                else:
                    error_text = self.extract_error_text(response)
                    self.after(
                        0,
                        lambda: messagebox.showerror(
                            "Ошибка подключения",
                            f"HTTP {response.status_code}\n\n{error_text}"
                        )
                    )
            except Exception as e:
                self.after(0, lambda: messagebox.showerror("Ошибка подключения", str(e)))

        threading.Thread(target=worker, daemon=True).start()


if __name__ == "__main__":
    app = ChatApp()
    app.mainloop()