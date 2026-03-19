import csv
import html
import json
import os
import textwrap
import time
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

import customtkinter as ctk
import requests
from dotenv import load_dotenv
from tkinter import filedialog, messagebox


load_dotenv()

APP_DIR = Path(__file__).resolve().parent
REPORTS_DIR = APP_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)


@dataclass
class GatewayResponse:
    mode: str
    content: str
    raw: Dict[str, Any]
    prompt_used: Optional[str] = None
    request_payload: Optional[Dict[str, Any]] = None
    technical: Optional[Dict[str, Any]] = None


class LLMGatewayClient:
    def __init__(self, request_url: str, timeout: int = 60):
        self.request_url = request_url.strip()
        self.timeout = timeout

    @property
    def headers(self) -> Dict[str, str]:
        return {"Content-Type": "application/json"}

    @property
    def base_url(self) -> str:
        parsed = urlparse(self.request_url)
        path = parsed.path or ""
        if path.endswith("/generate"):
            path = path[: -len("/generate")]
        return f"{parsed.scheme}://{parsed.netloc}{path}".rstrip("/")

    def health(self) -> Dict[str, Any]:
        response = requests.get(
            f"{self.base_url}/health",
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def models(self) -> Any:
        response = requests.get(
            f"{self.base_url}/models",
            headers=self.headers,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()

    def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 1200,
        top_p: float = 1.0,
        presence_penalty: float = 0.0,
        frequency_penalty: float = 0.0,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        payload = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
        }
        started = time.perf_counter()
        response = requests.post(
            self.request_url,
            headers=self.headers,
            json=payload,
            timeout=self.timeout,
        )
        elapsed_ms = round((time.perf_counter() - started) * 1000, 2)
        response.raise_for_status()
        raw = response.json()
        content = raw.get("content", "") or ""
        usage = raw.get("usage") or {}
        technical = {
            "request_url": self.request_url,
            "http_status": response.status_code,
            "model": payload.get("model"),
            "temperature": payload.get("temperature"),
            "max_tokens": payload.get("max_tokens"),
            "top_p": payload.get("top_p"),
            "presence_penalty": payload.get("presence_penalty"),
            "frequency_penalty": payload.get("frequency_penalty"),
            "response_time_ms": elapsed_ms,
            "response_chars": len(content),
            "response_words": len(content.split()),
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "total_tokens": usage.get("total_tokens"),
            "finish_reason": raw.get("finish_reason"),
            "request_id": raw.get("request_id"),
            "gateway_latency_ms": raw.get("latency_ms"),
            "validation": raw.get("validation"),
        }
        return raw, payload, technical


class FourModeRunner:
    def __init__(self, client: LLMGatewayClient, model: str, default_temperature: float = 0.3, default_max_tokens: int = 1200):
        self.client = client
        self.model = model
        self.default_temperature = default_temperature
        self.default_max_tokens = default_max_tokens

    def run_all(self, user_question: str) -> Dict[str, GatewayResponse]:
        direct = self._direct_answer(user_question)
        cot = self._step_by_step_answer(user_question)
        self_prompt = self._self_prompt_answer(user_question)
        experts = self._experts_answer(user_question)
        return {
            "direct": direct,
            "step_by_step": cot,
            "self_prompt": self_prompt,
            "experts": experts,
        }

    def _direct_answer(self, question: str) -> GatewayResponse:
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[{"role": "user", "content": question}],
            temperature=self.default_temperature,
            max_tokens=self.default_max_tokens,
        )
        return GatewayResponse(
            mode="1. Прямой ответ",
            content=raw.get("content", ""),
            raw=raw,
            request_payload=payload,
            technical=technical,
        )

    def _step_by_step_answer(self, question: str) -> GatewayResponse:
        system_prompt = (
            "Ты полезный ассистент. Решай задачу пошагово, явно выделяя этапы анализа, "
            "но финальный ответ делай практичным и понятным."
        )
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=self.default_temperature,
            max_tokens=self.default_max_tokens,
        )
        return GatewayResponse(
            mode="2. Решай пошагово",
            content=raw.get("content", ""),
            raw=raw,
            prompt_used=system_prompt,
            request_payload=payload,
            technical=technical,
        )

    def _self_prompt_answer(self, question: str) -> GatewayResponse:
        builder_raw, _, _ = self.client.generate(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Сгенерируй один сильный system prompt для другой нейросети, который поможет "
                        "лучше ответить на вопрос пользователя. Верни только текст промпта без пояснений."
                    ),
                },
                {"role": "user", "content": question},
            ],
            temperature=max(self.default_temperature, 0.4),
            max_tokens=min(self.default_max_tokens, 500),
        )
        generated_prompt = (builder_raw.get("content") or "").strip()
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": generated_prompt},
                {"role": "user", "content": question},
            ],
            temperature=self.default_temperature,
            max_tokens=self.default_max_tokens,
        )
        return GatewayResponse(
            mode="3. Через промпт, предложенный нейросетью",
            content=raw.get("content", ""),
            raw=raw,
            prompt_used=generated_prompt,
            request_payload=payload,
            technical=technical,
        )

    def _experts_answer(self, question: str) -> GatewayResponse:
        system_prompt = textwrap.dedent(
            """
            Ты симулируешь мини-дискуссию группы экспертов:
            1) Аналитик — структурирует задачу и риски.
            2) Инженер — предлагает практическое решение.
            3) Критик — указывает слабые места и ограничения.
            4) Модератор — собирает общий итог и рекомендацию.
            Ответ оформи по ролям, а в конце дай согласованный вывод.
            """
        ).strip()
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=max(self.default_temperature, 0.5),
            max_tokens=max(self.default_max_tokens, 1800),
        )
        return GatewayResponse(
            mode="4. Группа экспертов",
            content=raw.get("content", ""),
            raw=raw,
            prompt_used=system_prompt,
            request_payload=payload,
            technical=technical,
        )

    def compare_answers(self, question: str, results: Dict[str, GatewayResponse]) -> Tuple[str, Dict[str, Any], Dict[str, Any]]:
        comparison_payload = {
            key: {
                "mode": value.mode,
                "content": value.content,
                "technical": value.technical,
            }
            for key, value in results.items()
        }
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Сделай краткий, но содержательный анализ различий между четырьмя ответами. "
                        "Сравни глубину, точность, практичность, структуру и возможные ограничения. "
                        "Отдельно отметь различия по времени ответа и токенам, если они переданы. "
                        "Ответ дай на русском языке, в HTML-совместимом тексте с абзацами и маркированным списком."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Вопрос пользователя:\n{question}\n\n"
                        f"Ответы:\n{json.dumps(comparison_payload, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
            temperature=min(self.default_temperature, 0.2),
            max_tokens=min(max(self.default_max_tokens, 1000), 2000),
        )
        return raw.get("content", ""), payload, technical


def _safe_num(value: Any, default: int = 0) -> int:
    return int(value) if isinstance(value, (int, float)) and value is not None else default


def technical_table(technical: Optional[Dict[str, Any]]) -> str:
    if not technical:
        return "<p>Нет технических данных.</p>"
    rows = []
    for key, value in technical.items():
        rendered = html.escape(json.dumps(value, ensure_ascii=False)) if isinstance(value, (dict, list)) else html.escape(str(value))
        rows.append(f"<tr><td>{html.escape(str(key))}</td><td>{rendered}</td></tr>")
    return (
        '<table class="tech-table"><thead><tr><th>Параметр</th><th>Значение</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def build_chart_script(results: Dict[str, GatewayResponse]) -> str:
    labels = [value.mode for value in results.values()]
    response_time_ms = [_safe_num((value.technical or {}).get("response_time_ms")) for value in results.values()]
    total_tokens = [_safe_num((value.technical or {}).get("total_tokens")) for value in results.values()]
    prompt_tokens = [_safe_num((value.technical or {}).get("prompt_tokens")) for value in results.values()]
    completion_tokens = [_safe_num((value.technical or {}).get("completion_tokens")) for value in results.values()]

    return f"""
<script src=\"https://cdn.jsdelivr.net/npm/chart.js\"></script>
<script>
const labels = {json.dumps(labels, ensure_ascii=False)};
new Chart(document.getElementById('timeChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [{{ label: 'Время ответа, мс', data: {json.dumps(response_time_ms)} }}]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});
new Chart(document.getElementById('tokensChart'), {{
  type: 'bar',
  data: {{
    labels: labels,
    datasets: [
      {{ label: 'Prompt tokens', data: {json.dumps(prompt_tokens)} }},
      {{ label: 'Completion tokens', data: {json.dumps(completion_tokens)} }},
      {{ label: 'Total tokens', data: {json.dumps(total_tokens)} }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});
</script>
"""


def build_html_report(
    question: str,
    model: str,
    results: Dict[str, GatewayResponse],
    analysis_text: str,
    analysis_technical: Optional[Dict[str, Any]] = None,
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    def block(item: GatewayResponse) -> str:
        prompt_block = ""
        if item.prompt_used:
            prompt_block = (
                f'<details><summary>Использованный system prompt</summary>'
                f'<pre>{html.escape(item.prompt_used)}</pre></details>'
            )
        request_block = ""
        if item.request_payload:
            request_block = (
                f'<details><summary>Payload запроса</summary>'
                f'<pre>{html.escape(json.dumps(item.request_payload, ensure_ascii=False, indent=2))}</pre></details>'
            )
        raw_block = (
            f'<details><summary>Raw response</summary>'
            f'<pre>{html.escape(json.dumps(item.raw, ensure_ascii=False, indent=2))}</pre></details>'
        )
        return f"""
        <section class=\"card\">
            <h2>{html.escape(item.mode)}</h2>
            {prompt_block}
            <h3>Ответ</h3>
            <pre>{html.escape(item.content)}</pre>
            <h3>Технические параметры</h3>
            {technical_table(item.technical)}
            {request_block}
            {raw_block}
        </section>
        """

    sections = "\n".join(block(value) for value in results.values())
    chart_script = build_chart_script(results)

    return f"""<!DOCTYPE html>
<html lang=\"ru\">
<head>
    <meta charset=\"UTF-8\" />
    <meta name=\"viewport\" content=\"width=device-width, initial-scale=1.0\" />
    <title>LLM Report</title>
    <style>
        body {{ font-family: Arial, sans-serif; margin: 0; padding: 24px; background: #f6f7fb; color: #1d2433; }}
        h1, h2, h3 {{ margin-top: 0; }}
        .container {{ max-width: 1280px; margin: 0 auto; }}
        .card {{ background: white; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 30px rgba(0,0,0,0.08); }}
        .meta {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); gap: 12px; margin-bottom: 20px; }}
        .meta div {{ background: #eef2ff; padding: 12px; border-radius: 12px; }}
        pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 12px; overflow-x: auto; }}
        details {{ margin: 12px 0; }}
        .analysis {{ line-height: 1.6; }}
        .charts {{ display: grid; grid-template-columns: 1fr; gap: 20px; }}
        .chart-box {{ height: 360px; }}
        .tech-table {{ width: 100%; border-collapse: collapse; margin: 12px 0 16px; background: #fff; }}
        .tech-table th, .tech-table td {{ border: 1px solid #d8ddea; padding: 8px 10px; text-align: left; vertical-align: top; }}
        .tech-table th {{ background: #eef2ff; }}
    </style>
</head>
<body>
    <div class=\"container\">
        <section class=\"card\">
            <h1>Отчёт по 4 стратегиям запроса к LLM</h1>
            <div class=\"meta\">
                <div><strong>Время:</strong><br>{html.escape(timestamp)}</div>
                <div><strong>Модель:</strong><br>{html.escape(model)}</div>
                <div><strong>Количество сценариев:</strong><br>{len(results)}</div>
            </div>
            <h2>Исходный вопрос</h2>
            <pre>{html.escape(question)}</pre>
        </section>

        <section class=\"card\">
            <h2>Графики</h2>
            <div class=\"charts\">
                <div>
                    <h3>Время ответа</h3>
                    <div class=\"chart-box\"><canvas id=\"timeChart\"></canvas></div>
                </div>
                <div>
                    <h3>Токены</h3>
                    <div class=\"chart-box\"><canvas id=\"tokensChart\"></canvas></div>
                </div>
            </div>
        </section>

        {sections}

        <section class=\"card analysis\">
            <h2>Краткий анализ различий</h2>
            <div>{analysis_text}</div>
            <h3>Технические параметры анализа</h3>
            {technical_table(analysis_technical)}
        </section>
    </div>
    {chart_script}
</body>
</html>
"""


def export_json(report_stem: str, question: str, model: str, results: Dict[str, GatewayResponse], analysis_text: str, analysis_request_payload: Dict[str, Any], analysis_technical: Dict[str, Any]) -> Path:
    payload = {
        "created_at": datetime.now().isoformat(),
        "question": question,
        "model": model,
        "results": {
            key: {
                "mode": value.mode,
                "content": value.content,
                "prompt_used": value.prompt_used,
                "request_payload": value.request_payload,
                "technical": value.technical,
                "raw": value.raw,
            }
            for key, value in results.items()
        },
        "analysis": {
            "content": analysis_text,
            "request_payload": analysis_request_payload,
            "technical": analysis_technical,
        },
    }
    json_path = REPORTS_DIR / f"{report_stem}.json"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return json_path


def export_csv(report_stem: str, results: Dict[str, GatewayResponse], analysis_technical: Dict[str, Any]) -> Path:
    csv_path = REPORTS_DIR / f"{report_stem}.csv"
    fieldnames = [
        "mode",
        "http_status",
        "model",
        "temperature",
        "max_tokens",
        "top_p",
        "presence_penalty",
        "frequency_penalty",
        "response_time_ms",
        "response_chars",
        "response_words",
        "prompt_tokens",
        "completion_tokens",
        "total_tokens",
        "finish_reason",
        "request_id",
        "gateway_latency_ms",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for value in results.values():
            technical = value.technical or {}
            writer.writerow({
                "mode": value.mode,
                **{key: technical.get(key) for key in fieldnames if key != "mode"},
            })
        writer.writerow({
            "mode": "Анализ различий",
            **{key: analysis_technical.get(key) for key in fieldnames if key != "mode"},
        })
    return csv_path


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LLM Gateway Client")
        self.geometry("1180x860")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        default_request_url = os.getenv("REQUEST_URL", "http://127.0.0.1:8000/generate")
        self.request_url_var = ctk.StringVar(value=default_request_url)
        self.model_var = ctk.StringVar(value=os.getenv("DEFAULT_MODEL", "openai/gpt-4o-mini"))
        self.temperature_var = ctk.StringVar(value="0.3")
        self.max_tokens_var = ctk.StringVar(value="1200")
        self.last_report_path: Optional[Path] = None
        self.last_json_path: Optional[Path] = None
        self.last_csv_path: Optional[Path] = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        cfg = ctk.CTkFrame(self)
        cfg.grid(row=0, column=0, sticky="nsew", padx=16, pady=(16, 8))
        cfg.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(cfg, text="Request URL").grid(row=0, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(cfg, textvariable=self.request_url_var).grid(row=0, column=1, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(cfg, text="Model").grid(row=0, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(cfg, textvariable=self.model_var).grid(row=0, column=3, padx=8, pady=8, sticky="ew")

        ctk.CTkLabel(cfg, text="Temperature").grid(row=1, column=0, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(cfg, textvariable=self.temperature_var, width=120).grid(row=1, column=1, padx=8, pady=8, sticky="w")

        ctk.CTkLabel(cfg, text="Max tokens").grid(row=1, column=2, padx=8, pady=8, sticky="w")
        ctk.CTkEntry(cfg, textvariable=self.max_tokens_var, width=120).grid(row=1, column=3, padx=8, pady=8, sticky="w")

        btns = ctk.CTkFrame(self)
        btns.grid(row=1, column=0, sticky="ew", padx=16, pady=8)
        for i in range(5):
            btns.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(btns, text="Проверить /health", command=self.check_health).grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Получить /models", command=self.load_models).grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Запустить 4 сценария", command=self.run_scenarios).grid(row=0, column=2, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Сохранить вопрос", command=self.save_prompt_to_file).grid(row=0, column=3, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(btns, text="Открыть отчёт", command=self.open_report).grid(row=0, column=4, padx=8, pady=8, sticky="ew")

        main = ctk.CTkFrame(self)
        main.grid(row=2, column=0, sticky="nsew", padx=16, pady=(8, 16))
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(1, weight=1)
        main.grid_rowconfigure(3, weight=1)

        ctk.CTkLabel(main, text="Вопрос пользователю/LLM").grid(row=0, column=0, padx=8, pady=(10, 0), sticky="w")
        self.prompt_text = ctk.CTkTextbox(main, height=180)
        self.prompt_text.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.prompt_text.insert("1.0", "Напишите здесь вопрос для LLM...")

        ctk.CTkLabel(main, text="Лог / результат").grid(row=2, column=0, padx=8, pady=(10, 0), sticky="w")
        self.output_text = ctk.CTkTextbox(main)
        self.output_text.grid(row=3, column=0, sticky="nsew", padx=8, pady=8)

    def _client(self) -> LLMGatewayClient:
        return LLMGatewayClient(
            request_url=self.request_url_var.get().strip(),
            timeout=60,
        )

    def _log(self, text: str) -> None:
        self.output_text.insert("end", text + "\n")
        self.output_text.see("end")
        self.update_idletasks()

    def _question(self) -> str:
        return self.prompt_text.get("1.0", "end").strip()

    def check_health(self) -> None:
        try:
            data = self._client().health()
            self._log("/health OK:\n" + json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as exc:
            messagebox.showerror("Ошибка /health", str(exc))
            self._log(f"Ошибка /health: {exc}")

    def load_models(self) -> None:
        try:
            data = self._client().models()
            self._log("/models:\n" + json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as exc:
            messagebox.showerror("Ошибка /models", str(exc))
            self._log(f"Ошибка /models: {exc}")

    def save_prompt_to_file(self) -> None:
        content = self._question()
        file_path = filedialog.asksaveasfilename(
            title="Сохранить вопрос",
            defaultextension=".txt",
            filetypes=[("Text", "*.txt"), ("Markdown", "*.md"), ("All files", "*.*")],
        )
        if not file_path:
            return
        Path(file_path).write_text(content, encoding="utf-8")
        self._log(f"Вопрос сохранён: {file_path}")

    def run_scenarios(self) -> None:
        question = self._question()
        if not question or question == "Напишите здесь вопрос для LLM...":
            messagebox.showwarning("Нет вопроса", "Введите вопрос для LLM.")
            return

        self.output_text.delete("1.0", "end")
        self._log("Запуск 4 сценариев...")
        try:
            runner = FourModeRunner(
                self._client(),
                self.model_var.get().strip(),
                default_temperature=float(self.temperature_var.get().strip()),
                default_max_tokens=int(self.max_tokens_var.get().strip()),
            )
            results = runner.run_all(question)
            for value in results.values():
                self._log(f"\n===== {value.mode} =====\n{value.content}\n")
                self._log("Техпараметры:\n" + json.dumps(value.technical, ensure_ascii=False, indent=2))

            self._log("\nГенерация анализа различий...")
            analysis_text, analysis_payload, analysis_technical = runner.compare_answers(question, results)
            self._log("\n===== Анализ различий =====\n" + analysis_text)
            self._log("Техпараметры анализа:\n" + json.dumps(analysis_technical, ensure_ascii=False, indent=2))

            report_stem = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            report_html = build_html_report(question, self.model_var.get().strip(), results, analysis_text, analysis_technical)
            report_path = REPORTS_DIR / f"{report_stem}.html"
            report_path.write_text(report_html, encoding="utf-8")
            json_path = export_json(report_stem, question, self.model_var.get().strip(), results, analysis_text, analysis_payload, analysis_technical)
            csv_path = export_csv(report_stem, results, analysis_technical)

            self.last_report_path = report_path
            self.last_json_path = json_path
            self.last_csv_path = csv_path

            webbrowser.open(report_path.resolve().as_uri())

            self._log(f"\nHTML-отчёт сохранён: {report_path}")
            self._log(f"JSON-экспорт сохранён: {json_path}")
            self._log(f"CSV-экспорт сохранён: {csv_path}")
            messagebox.showinfo("Готово", f"Созданы файлы:\n{report_path}\n{json_path}\n{csv_path}\n\nHTML-отчёт открыт в браузере.")
        except Exception as exc:
            messagebox.showerror("Ошибка выполнения", str(exc))
            self._log(f"Ошибка выполнения: {exc}")

    def open_report(self) -> None:
        target = self.last_report_path if self.last_report_path else REPORTS_DIR
        if isinstance(target, Path) and target.exists() and target.is_file():
            webbrowser.open(target.resolve().as_uri())
            self._log(f"Открыт отчёт: {target}")
        else:
            messagebox.showinfo("Путь к отчётам", str(target))
            self._log(f"Папка с отчётами: {target}")


if __name__ == "__main__":
    app = App()
    app.mainloop()
