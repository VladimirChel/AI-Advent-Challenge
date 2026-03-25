import json
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext

try:
    import requests
except ImportError:
    raise SystemExit("Install requests first: pip install requests")


class ChatClientGUI:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LLM Gateway Test Client")
        self.root.geometry("900x700")

        self.conversation_id = tk.StringVar()
        self.base_url = tk.StringVar(value="http://localhost:8000")
        self.api_key = tk.StringVar(value="YOUR_API_KEY")
        self.model = tk.StringVar(value="openai/gpt-4o-mini")

        self._build_ui()

    def _build_ui(self):
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill="x")

        ttk.Label(top, text="Base URL").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.base_url, width=40).grid(row=0, column=1, sticky="ew", padx=5)
        
        ttk.Label(top, text="Model").grid(row=1, column=0, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.model, width=40).grid(row=1, column=1, sticky="ew", padx=5, pady=(8, 0))

        ttk.Label(top, text="Conversation ID").grid(row=1, column=2, sticky="w", pady=(8, 0))
        ttk.Entry(top, textvariable=self.conversation_id, width=25).grid(row=1, column=3, sticky="ew", padx=5, pady=(8, 0))

        for i in range(4):
            top.columnconfigure(i, weight=1)

        buttons = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        buttons.pack(fill="x")

        ttk.Button(buttons, text="New Conversation", command=self.new_conversation).pack(side="left")
        ttk.Button(buttons, text="Send", command=self.send_message).pack(side="left", padx=8)
        ttk.Button(buttons, text="Load History", command=self.load_history).pack(side="left")

        self.chat = scrolledtext.ScrolledText(self.root, wrap="word", height=25)
        self.chat.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.chat.configure(state="disabled")

        input_frame = ttk.Frame(self.root, padding=10)
        input_frame.pack(fill="both")

        ttk.Label(input_frame, text="Message").pack(anchor="w")
        self.input_box = scrolledtext.ScrolledText(input_frame, wrap="word", height=8)
        self.input_box.pack(fill="both", expand=True, pady=(5, 10))

        bottom = ttk.Frame(self.root, padding=(10, 0, 10, 10))
        bottom.pack(fill="both")

        ttk.Label(bottom, text="Last raw response").pack(anchor="w")
        self.raw_output = scrolledtext.ScrolledText(bottom, wrap="word", height=12)
        self.raw_output.pack(fill="both", expand=True)
        self.raw_output.configure(state="normal")

    def _headers(self):
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {self.api_key.get().strip()}",
        }

    def _append_chat(self, role: str, content: str):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{role}: {content}\n\n")
        self.chat.see("end")
        self.chat.configure(state="disabled")

    def _set_raw_output(self, data):
        self.raw_output.delete("1.0", "end")
        if isinstance(data, str):
            self.raw_output.insert("1.0", data)
        else:
            self.raw_output.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

    def new_conversation(self):
        self.conversation_id.set("")
        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")
        self.chat.configure(state="disabled")
        self._set_raw_output({"status": "new conversation started locally"})

    def send_message(self):
        message = self.input_box.get("1.0", "end").strip()
        if not message:
            messagebox.showwarning("Empty message", "Enter a message first.")
            return

        payload = {
            "model": self.model.get().strip(),
            "messages": [
                {"role": "user", "content": message}
            ]
        }
        if self.conversation_id.get().strip():
            payload["conversation_id"] = self.conversation_id.get().strip()

        url = self.base_url.get().rstrip("/") + "/generate"

        try:
            response = requests.post(url, headers=self._headers(), json=payload, timeout=120)
            data = response.json()
        except requests.RequestException as e:
            messagebox.showerror("Request error", str(e))
            return
        except ValueError:
            messagebox.showerror("Invalid response", response.text if 'response' in locals() else "No response")
            return

        self._set_raw_output(data)

        if response.status_code >= 400:
            messagebox.showerror("Server error", json.dumps(data, ensure_ascii=False, indent=2))
            return

        new_conversation_id = data.get("conversation_id")
        if new_conversation_id:
            self.conversation_id.set(new_conversation_id)

        self._append_chat("user", message)
        assistant_text = data.get("content") or data.get("message") or "(empty response)"
        self._append_chat("assistant", assistant_text)
        self.input_box.delete("1.0", "end")

    def load_history(self):
        conversation_id = self.conversation_id.get().strip()
        if not conversation_id:
            messagebox.showwarning("No conversation", "Conversation ID is empty.")
            return

        url = self.base_url.get().rstrip("/") + f"/conversations/{conversation_id}/messages"

        try:
            response = requests.get(url, headers=self._headers(), timeout=60)
            data = response.json()
        except requests.RequestException as e:
            messagebox.showerror("Request error", str(e))
            return
        except ValueError:
            messagebox.showerror("Invalid response", response.text if 'response' in locals() else "No response")
            return

        self._set_raw_output(data)

        if response.status_code >= 400:
            messagebox.showerror("Server error", json.dumps(data, ensure_ascii=False, indent=2))
            return

        self.chat.configure(state="normal")
        self.chat.delete("1.0", "end")

        messages = data if isinstance(data, list) else data.get("messages", [])
        for item in messages:
            role = item.get("role", "unknown")
            content = item.get("content", "")
            self.chat.insert("end", f"{role}: {content}\n\n")

        self.chat.see("end")
        self.chat.configure(state="disabled")


if __name__ == "__main__":
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except Exception:
        pass
    app = ChatClientGUI(root)
    root.mainloop()
