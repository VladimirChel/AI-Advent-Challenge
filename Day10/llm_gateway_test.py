import json
import queue
import re
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import customtkinter as ctk
import requests
from tkinter import filedialog, messagebox


DEFAULT_EXPECTED_FACTS = {
    "order_id": ["12345"],
    "shipping": ["вчера", "три дня", "3 дня"],
    "address": ["ленина", "10"],
    "item": ["блокнот"],
    "price_delta": ["200"],
    "total": ["1200"],
}

PROBES = [
    {
        "name": "order_snapshot",
        "question": (
            "Кратко перечисли актуальные детали заказа: номер заказа, статус доставки, "
            "адрес доставки, добавленный товар и итоговую сумму."
        ),
        "checks": {
            "order_id": ["12345"],
            "shipping": ["три дня", "3 дня", "отправлен вчера"],
            "address": ["ленина", "10"],
            "item": ["блокнот"],
            "total": ["1200"],
        },
    },
    {
        "name": "price_delta",
        "question": "На сколько увеличилась сумма заказа после изменений и почему?",
        "checks": {
            "price_delta": ["200"],
            "item": ["блокнот"],
        },
    },
    {
        "name": "address_check",
        "question": "Какой адрес доставки был в итоге подтвержден? Ответь одной строкой.",
        "checks": {
            "address": ["ленина", "10"],
        },
    },
]


@dataclass
class StrategyResult:
    name: str
    conversation_id: Optional[str] = None
    branch_id: str = "main"
    total_prompt_tokens: int = 0
    total_completion_tokens: int = 0
    total_tokens: int = 0
    stability_score: float = 0.0
    convenience_score: float = 0.0
    notes: List[str] = field(default_factory=list)
    probe_results: List[Dict[str, Any]] = field(default_factory=list)
    replay_log: List[Dict[str, Any]] = field(default_factory=list)
    debug: Dict[str, Any] = field(default_factory=dict)


class GatewayClient:
    def __init__(self, base_url: str, timeout: int = 60):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.session = requests.Session()

    def health(self) -> Dict[str, Any]:
        resp = self.session.get(f"{self.base_url}/health", timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def generate(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        resp = self.session.post(f"{self.base_url}/generate", json=payload, timeout=self.timeout)
        resp.raise_for_status()
        return resp.json()

    def get_messages(self, conversation_id: str, branch_id: str = "main", limit: int = 200) -> Dict[str, Any]:
        resp = self.session.get(
            f"{self.base_url}/conversations/{conversation_id}/messages",
            params={"branch_id": branch_id, "limit": limit},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def get_facts(self, conversation_id: str, branch_id: str = "main") -> Dict[str, Any]:
        resp = self.session.get(
            f"{self.base_url}/conversations/{conversation_id}/facts",
            params={"branch_id": branch_id},
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()

    def create_branch(
        self,
        conversation_id: str,
        branch_id: str,
        fork_from_message_uuid: str,
        source_branch_id: str = "main",
    ) -> Dict[str, Any]:
        resp = self.session.post(
            f"{self.base_url}/conversations/{conversation_id}/branches",
            params={
                "branch_id": branch_id,
                "fork_from_message_uuid": fork_from_message_uuid,
                "source_branch_id": source_branch_id,
            },
            timeout=self.timeout,
        )
        resp.raise_for_status()
        return resp.json()


class GatewayTester:
    def __init__(self, client: GatewayClient, model: str, max_tokens: int, history_limit: int, temperature: float):
        self.client = client
        self.model = model
        self.max_tokens = max_tokens
        self.history_limit = history_limit
        self.temperature = temperature

    @staticmethod
    def _extract_dialog(payload: Dict[str, Any]) -> List[Dict[str, str]]:
        if isinstance(payload.get("response"), dict) and isinstance(payload["response"].get("dialog"), list):
            return payload["response"]["dialog"]
        if isinstance(payload.get("dialog"), list):
            return payload["dialog"]
        raise ValueError("Не найден массив dialog в JSON.")

    @staticmethod
    def _normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", text.lower()).strip()

    def _score_response(self, text: str, checks: Dict[str, List[str]]) -> Tuple[float, List[str]]:
        normalized = self._normalize_text(text)
        hits = 0
        total = len(checks)
        misses: List[str] = []
        for key, variants in checks.items():
            ok = any(v.lower() in normalized for v in variants)
            if ok:
                hits += 1
            else:
                misses.append(key)
        score = (hits / total) * 100 if total else 100.0
        return score, misses

    def _append_usage(self, result: StrategyResult, response: Dict[str, Any]):
        usage = response.get("usage") or {}
        result.total_prompt_tokens += int(usage.get("prompt_tokens") or 0)
        result.total_completion_tokens += int(usage.get("completion_tokens") or 0)
        result.total_tokens += int(usage.get("total_tokens") or 0)

    def _make_payload(
        self,
        messages: List[Dict[str, str]],
        conversation_id: Optional[str],
        branch_id: str,
        memory_strategy: str,
        use_memory: bool = True,
        sticky_facts_enabled: bool = True,
        fork_from_branch_id: Optional[str] = None,
        fork_from_message_uuid: Optional[str] = None,
    ) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "conversation_id": conversation_id,
            "branch_id": branch_id,
            "use_memory": use_memory,
            "memory_strategy": memory_strategy,
            "history_limit": self.history_limit,
            "retrieval_enabled": False,
            "retrieval_limit": 0,
            "sticky_facts_enabled": sticky_facts_enabled,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
        }
        if fork_from_branch_id:
            payload["fork_from_branch_id"] = fork_from_branch_id
        if fork_from_message_uuid:
            payload["fork_from_message_uuid"] = fork_from_message_uuid
        return payload

    def replay_dialog(
        self,
        dialog_payload: Dict[str, Any],
        strategy_name: str,
        memory_strategy: str,
        sticky_facts_enabled: bool,
        use_branching: bool = False,
    ) -> StrategyResult:
        dialog = self._extract_dialog(dialog_payload)
        result = StrategyResult(name=strategy_name)

        branch_id = "main"
        conversation_id: Optional[str] = None
        system_prompt = {
            "role": "system",
            "content": (
                "Ты менеджер интернет-магазина. Отвечай кратко, по делу и согласованно с уже известным контекстом. "
                f"Не превышай разумный объём и учитывай ограничение max_tokens={self.max_tokens}."
            ),
        }

        speaker_to_role = {
            "клиент": "user",
            "менеджер": "assistant",
        }

        for i, item in enumerate(dialog):
            speaker = str(item.get("speaker", "")).strip().lower()
            text = str(item.get("text", "")).strip()
            if not text:
                continue
            role = speaker_to_role.get(speaker)
            if role != "user":
                # assistant turns are reproduced as assistant messages to keep the same history
                if conversation_id is None:
                    continue
                payload = self._make_payload(
                    messages=[{"role": "assistant", "content": text}],
                    conversation_id=conversation_id,
                    branch_id=branch_id,
                    memory_strategy=memory_strategy,
                    sticky_facts_enabled=sticky_facts_enabled,
                )
            else:
                payload = self._make_payload(
                    messages=[system_prompt, {"role": "user", "content": text}] if conversation_id is None else [{"role": "user", "content": text}],
                    conversation_id=conversation_id,
                    branch_id=branch_id,
                    memory_strategy=memory_strategy,
                    sticky_facts_enabled=sticky_facts_enabled,
                )

            response = self.client.generate(payload)
            conversation_id = response.get("conversation_id", conversation_id)
            branch_id = response.get("branch_id", branch_id)
            result.conversation_id = conversation_id
            result.branch_id = branch_id
            self._append_usage(result, response)
            result.replay_log.append(
                {
                    "seq": i + 1,
                    "speaker": item.get("speaker"),
                    "text": text,
                    "gateway_answer": response.get("content", ""),
                    "usage": response.get("usage", {}),
                    "context_messages_used": response.get("context_messages_used"),
                    "summary_used": response.get("summary_used"),
                    "sticky_facts_used": response.get("sticky_facts_used"),
                    "sticky_facts_count": response.get("sticky_facts_count"),
                }
            )

        if not conversation_id:
            raise RuntimeError("Не удалось создать conversation_id во время проигрывания диалога.")

        if use_branching:
            messages_data = self.client.get_messages(conversation_id, branch_id="main", limit=200)
            msgs = messages_data.get("messages", [])
            if len(msgs) < 4:
                raise RuntimeError("Недостаточно сообщений для теста ветвления.")
            fork_from = msgs[min(len(msgs) - 1, max(2, len(msgs) // 2))]["message_uuid"]
            new_branch_id = f"branch-{uuid.uuid4().hex[:8]}"
            self.client.create_branch(
                conversation_id=conversation_id,
                branch_id=new_branch_id,
                fork_from_message_uuid=fork_from,
                source_branch_id="main",
            )
            branch_id = new_branch_id
            result.branch_id = branch_id
            result.notes.append(f"Создана ветка {branch_id} от сообщения {fork_from}.")

            fork_probe = (
                "Это альтернативная ветка. Представь, что клиент в этой ветке НЕ добавлял блокнот. "
                "Скажи, какая тогда была бы итоговая сумма и сохранился бы адрес доставки?"
            )
            payload = self._make_payload(
                messages=[{"role": "user", "content": fork_probe}],
                conversation_id=conversation_id,
                branch_id=branch_id,
                memory_strategy=memory_strategy,
                sticky_facts_enabled=sticky_facts_enabled,
            )
            branch_response = self.client.generate(payload)
            self._append_usage(result, branch_response)
            result.debug["branch_probe"] = branch_response

        stability_scores = []
        for probe in PROBES:
            payload = self._make_payload(
                messages=[{"role": "user", "content": probe["question"]}],
                conversation_id=conversation_id,
                branch_id=branch_id,
                memory_strategy=memory_strategy,
                sticky_facts_enabled=sticky_facts_enabled,
            )
            response = self.client.generate(payload)
            self._append_usage(result, response)
            answer = response.get("content", "")
            score, misses = self._score_response(answer, probe["checks"])
            stability_scores.append(score)
            result.probe_results.append(
                {
                    "probe": probe["name"],
                    "question": probe["question"],
                    "answer": answer,
                    "score": score,
                    "misses": misses,
                    "usage": response.get("usage", {}),
                }
            )

        result.stability_score = round(sum(stability_scores) / len(stability_scores), 2) if stability_scores else 0.0
        result.convenience_score = self._estimate_convenience(strategy_name)

        if sticky_facts_enabled:
            try:
                facts = self.client.get_facts(conversation_id, branch_id=result.branch_id)
                result.debug["facts"] = facts
                result.notes.append(f"Sticky facts: {facts.get('count', 0)}")
            except Exception as exc:
                result.notes.append(f"Не удалось получить facts: {exc}")

        if result.total_completion_tokens >= self.max_tokens * len(result.probe_results):
            result.notes.append("В некоторых запросах completion_tokens близки к max_tokens; возможна усечённость ответа.")
        return result

    @staticmethod
    def _estimate_convenience(strategy_name: str) -> float:
        presets = {
            "Window": 9.0,
            "Facts": 8.0,
            "Window (Branching)": 7.0,
        }
        return presets.get(strategy_name, 7.0)

    @staticmethod
    def build_summary(results: List[StrategyResult]) -> Dict[str, Any]:
        def brief_notes(item: StrategyResult) -> str:
            notes = []
            if item.stability_score >= 85:
                notes.append("контекст держится стабильно")
            elif item.stability_score >= 60:
                notes.append("есть частичные потери деталей")
            else:
                notes.append("контекст заметно деградирует")

            if item.total_tokens <= 2500:
                notes.append("низкий расход токенов")
            elif item.total_tokens <= 5000:
                notes.append("средний расход токенов")
            else:
                notes.append("высокий расход токенов")
            return ", ".join(notes)

        ordered_by_stability = sorted(results, key=lambda x: x.stability_score, reverse=True)
        ordered_by_tokens = sorted(results, key=lambda x: x.total_tokens)
        ordered_by_convenience = sorted(results, key=lambda x: x.convenience_score, reverse=True)

        return {
            "best_stability": ordered_by_stability[0].name if results else None,
            "best_token_efficiency": ordered_by_tokens[0].name if results else None,
            "best_user_convenience": ordered_by_convenience[0].name if results else None,
            "recommendation": (
                f"Для сохранения контекста лучше всего показала себя стратегия {ordered_by_stability[0].name}. "
                f"По расходу токенов лидирует {ordered_by_tokens[0].name}. "
                f"По удобству для пользователя лидирует {ordered_by_convenience[0].name}."
            ) if results else "",
            "strategy_notes": {item.name: brief_notes(item) for item in results},
        }


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("llm_gateway_test")
        self.geometry("1380x900")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        self.dialog_payload: Optional[Dict[str, Any]] = None
        self.worker_queue: queue.Queue = queue.Queue()

        self.base_url_var = ctk.StringVar(value="http://127.0.0.1:8000")
        self.model_var = ctk.StringVar(value="openai/gpt-4o-mini")
        self.max_tokens_var = ctk.IntVar(value=256)
        self.history_limit_var = ctk.IntVar(value=6)
        self.temperature_var = ctk.DoubleVar(value=0.2)

        self._build_ui()
        self.after(150, self._poll_queue)

    def _build_ui(self):
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)

        left = ctk.CTkFrame(self)
        left.grid(row=0, column=0, sticky="nsw", padx=(12, 6), pady=12)
        left.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(left, text="Настройки", font=ctk.CTkFont(size=18, weight="bold")).grid(
            row=0, column=0, sticky="w", padx=12, pady=(12, 8)
        )

        self._labeled_entry(left, "Base URL", self.base_url_var, 1)
        self._labeled_entry(left, "Model", self.model_var, 2)
        self._labeled_entry(left, "max_tokens", self.max_tokens_var, 3)
        self._labeled_entry(left, "history_limit", self.history_limit_var, 4)
        self._labeled_entry(left, "temperature", self.temperature_var, 5)

        ctk.CTkButton(left, text="Проверить /health", command=self.check_health).grid(
            row=6, column=0, sticky="ew", padx=12, pady=(12, 6)
        )
        ctk.CTkButton(left, text="Загрузить JSON диалога", command=self.load_dialog).grid(
            row=7, column=0, sticky="ew", padx=12, pady=6
        )
        ctk.CTkButton(left, text="Запустить тест", command=self.run_tests).grid(
            row=8, column=0, sticky="ew", padx=12, pady=6
        )
        ctk.CTkButton(left, text="Экспорт отчёта", command=self.export_report).grid(
            row=9, column=0, sticky="ew", padx=12, pady=(6, 12)
        )

        self.status_box = ctk.CTkTextbox(left, width=340, height=520)
        self.status_box.grid(row=10, column=0, sticky="nsew", padx=12, pady=(0, 12))
        left.grid_rowconfigure(10, weight=1)
        self._log("Приложение готово. Загрузите диалог и запустите тест.")

        right = ctk.CTkTabview(self)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 12), pady=12)
        right.add("Диалог")
        right.add("Результаты")
        right.add("Сырые ответы")

        self.dialog_text = ctk.CTkTextbox(right.tab("Диалог"))
        self.dialog_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.results_text = ctk.CTkTextbox(right.tab("Результаты"))
        self.results_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.raw_text = ctk.CTkTextbox(right.tab("Сырые ответы"))
        self.raw_text.pack(fill="both", expand=True, padx=10, pady=10)

        self.last_report: Optional[Dict[str, Any]] = None

    def _labeled_entry(self, parent, label: str, var, row: int):
        ctk.CTkLabel(parent, text=label).grid(row=row, column=0, sticky="w", padx=12, pady=(6, 0))
        entry = ctk.CTkEntry(parent, textvariable=var, width=320)
        entry.grid(row=row + 1, column=0, sticky="ew", padx=12, pady=(0, 6))

    def _log(self, message: str):
        ts = time.strftime("%H:%M:%S")
        self.status_box.insert("end", f"[{ts}] {message}\n")
        self.status_box.see("end")

    def check_health(self):
        def worker():
            try:
                client = GatewayClient(self.base_url_var.get())
                health = client.health()
                self.worker_queue.put(("health_ok", health))
            except Exception as exc:
                self.worker_queue.put(("error", f"/health ошибка: {exc}"))

        threading.Thread(target=worker, daemon=True).start()

    def load_dialog(self):
        path = filedialog.askopenfilename(filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                self.dialog_payload = json.load(f)
            self.dialog_text.delete("1.0", "end")
            self.dialog_text.insert("end", json.dumps(self.dialog_payload, ensure_ascii=False, indent=2))
            self._log(f"Загружен файл: {path}")
        except Exception as exc:
            messagebox.showerror("Ошибка", f"Не удалось загрузить файл:\n{exc}")

    def run_tests(self):
        if not self.dialog_payload:
            messagebox.showwarning("Нет диалога", "Сначала загрузите JSON диалога.")
            return

        self.results_text.delete("1.0", "end")
        self.raw_text.delete("1.0", "end")
        self._log("Старт тестов...")

        def worker():
            try:
                client = GatewayClient(self.base_url_var.get())
                tester = GatewayTester(
                    client=client,
                    model=self.model_var.get(),
                    max_tokens=int(self.max_tokens_var.get()),
                    history_limit=int(self.history_limit_var.get()),
                    temperature=float(self.temperature_var.get()),
                )

                strategies = [
                    ("Window", "window", False, False),
                    ("Facts", "facts", True, False),
                    ("Window (Branching)", "window", False, True),
                ]
                results: List[StrategyResult] = []
                for name, mem, facts, branching in strategies:
                    self.worker_queue.put(("log", f"Запуск стратегии {name}..."))
                    result = tester.replay_dialog(
                        dialog_payload=self.dialog_payload,
                        strategy_name=name,
                        memory_strategy=mem,
                        sticky_facts_enabled=facts,
                        use_branching=branching,
                    )
                    results.append(result)

                summary = tester.build_summary(results)
                report = {
                    "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                    "config": {
                        "base_url": self.base_url_var.get(),
                        "model": self.model_var.get(),
                        "max_tokens": int(self.max_tokens_var.get()),
                        "history_limit": int(self.history_limit_var.get()),
                        "temperature": float(self.temperature_var.get()),
                    },
                    "summary": summary,
                    "results": [result.__dict__ for result in results],
                }
                self.worker_queue.put(("tests_done", report))
            except Exception as exc:
                self.worker_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()

    def export_report(self):
        if not self.last_report:
            messagebox.showinfo("Нет отчёта", "Сначала запустите тест.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
            initialfile="llm_gateway_test_report.json",
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.last_report, f, ensure_ascii=False, indent=2)
        self._log(f"Отчёт сохранён: {path}")

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.worker_queue.get_nowait()
                if kind == "health_ok":
                    self._log(f"/health OK: {json.dumps(payload, ensure_ascii=False)}")
                elif kind == "tests_done":
                    self.last_report = payload
                    self._render_report(payload)
                    self._log("Тест завершён.")
                elif kind == "log":
                    self._log(str(payload))
                elif kind == "error":
                    self._log(f"Ошибка: {payload}")
                    messagebox.showerror("Ошибка", str(payload))
        except queue.Empty:
            pass
        self.after(150, self._poll_queue)

    def _render_report(self, report: Dict[str, Any]):
        self.results_text.delete("1.0", "end")
        self.raw_text.delete("1.0", "end")

        summary = report["summary"]
        lines = [
            f"Отчёт: {report['created_at']}",
            "",
            "Итоги сравнения:",
            f"- Лучшая стабильность: {summary['best_stability']}",
            f"- Лучший расход токенов: {summary['best_token_efficiency']}",
            f"- Лучшее удобство: {summary['best_user_convenience']}",
            f"- Рекомендация: {summary['recommendation']}",
            "",
        ]
        for item in report["results"]:
            lines.extend(
                [
                    f"Стратегия: {item['name']}",
                    f"  conversation_id: {item['conversation_id']}",
                    f"  branch_id: {item['branch_id']}",
                    f"  stability_score: {item['stability_score']}",
                    f"  convenience_score: {item['convenience_score']}",
                    f"  total_tokens: {item['total_tokens']} (prompt={item['total_prompt_tokens']}, completion={item['total_completion_tokens']})",
                    f"  notes: {', '.join(item['notes']) if item['notes'] else '-'}",
                    "  Пробы:",
                ]
            )
            for probe in item["probe_results"]:
                lines.extend(
                    [
                        f"    - {probe['probe']}: score={probe['score']} misses={probe['misses']}",
                        f"      answer: {probe['answer']}",
                    ]
                )
            lines.append("")
        self.results_text.insert("end", "\n".join(lines))
        self.raw_text.insert("end", json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    app = App()
    app.mainloop()
