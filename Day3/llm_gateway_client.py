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

MODEL_OPTIONS = [
    "openai/gpt-4o-mini",
    "openai/gpt-4o",
    "openai/gpt-4.1-mini",
    "openai/gpt-4.1",
    "anthropic/claude-sonnet-4-20250514",
    "anthropic/claude-3-5-sonnet-20241022",
    "google/gemini-2.0-flash",
    "google/gemini-1.5-pro",
]

DEFAULT_STEP_BY_STEP_PROMPT = (
    "Ты полезный ассистент. Решай задачу пошагово, явно выделяя этапы анализа, "
    "но финальный ответ делай практичным и понятным."
)

DEFAULT_SELF_PROMPT_BUILDER = (
    "Сгенерируй один сильный system prompt для другой нейросети, который поможет "
    "лучше ответить на вопрос пользователя. Верни только текст промпта без пояснений."
)

DEFAULT_EXPERTS_PROMPT = textwrap.dedent(
    """
    Ты симулируешь мини-дискуссию группы экспертов:
    1) Аналитик — структурирует задачу и риски.
    2) Инженер — предлагает практическое решение.
    3) Критик — указывает слабые места и ограничения.
    4) Модератор — собирает общий итог и рекомендацию.
    Ответ оформи по ролям, а в конце дай согласованный вывод.
    """
).strip()

DEFAULT_COMPARISON_PROMPT = (
    "Сделай краткий, но содержательный анализ различий между четырьмя ответами. "
    "Сравни глубину, точность, практичность, структуру и возможные ограничения. "
    "Отдельно отметь различия по времени ответа и токенам, если они переданы. "
    "Ответ дай на русском языке, в HTML-совместимом тексте с абзацами и маркированным списком."
)


@dataclass
class ScenarioConfig:
    temperature: float
    max_tokens: int
    system_prompt: Optional[str] = None


@dataclass
class RunConfig:
    direct: ScenarioConfig
    step_by_step: ScenarioConfig
    self_prompt_builder: ScenarioConfig
    self_prompt_answer: ScenarioConfig
    experts: ScenarioConfig
    comparison: ScenarioConfig


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
            path = path[:-len("/generate")]
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
    def __init__(self, client: LLMGatewayClient, model: str, config: RunConfig):
        self.client = client
        self.model = model
        self.config = config

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
        cfg = self.config.direct
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[{"role": "user", "content": question}],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        return GatewayResponse(
            mode="1. Прямой ответ",
            content=raw.get("content", ""),
            raw=raw,
            request_payload=payload,
            technical=technical,
        )

    def _step_by_step_answer(self, question: str) -> GatewayResponse:
        cfg = self.config.step_by_step
        system_prompt = (cfg.system_prompt or "").strip()
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
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
        builder_cfg = self.config.self_prompt_builder
        builder_prompt = (builder_cfg.system_prompt or "").strip()
        builder_raw, _, _ = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": builder_prompt},
                {"role": "user", "content": question},
            ],
            temperature=builder_cfg.temperature,
            max_tokens=builder_cfg.max_tokens,
        )
        generated_prompt = (builder_raw.get("content") or "").strip()
        answer_cfg = self.config.self_prompt_answer
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": generated_prompt},
                {"role": "user", "content": question},
            ],
            temperature=answer_cfg.temperature,
            max_tokens=answer_cfg.max_tokens,
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
        cfg = self.config.experts
        system_prompt = (cfg.system_prompt or "").strip()
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": question},
            ],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
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
        cfg = self.config.comparison
        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": (cfg.system_prompt or "").strip()},
                {
                    "role": "user",
                    "content": (
                        f"Вопрос пользователя:\n{question}\n\n"
                        f"Ответы:\n{json.dumps(comparison_payload, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
            temperature=cfg.temperature,
            max_tokens=cfg.max_tokens,
        )
        return raw.get("content", ""), payload, technical


class SettingsPanel(ctk.CTkScrollableFrame):
    def __init__(self, master: Any, model_var: ctk.StringVar, request_url_var: ctk.StringVar):
        super().__init__(master)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(3, weight=1)

        self.request_url_var = request_url_var
        self.model_var = model_var

        self._add_general_section()
        self._add_scenarios_section()

    def _add_general_section(self) -> None:
        row = 0
        ctk.CTkLabel(self, text="Общие настройки", font=ctk.CTkFont(size=16, weight="bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", padx=8, pady=(8, 12)
        )
        row += 1

        ctk.CTkLabel(self, text="Request URL").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ctk.CTkEntry(self, textvariable=self.request_url_var).grid(row=row, column=1, columnspan=3, sticky="ew", padx=8, pady=6)
        row += 1

        ctk.CTkLabel(self, text="Модель").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ctk.CTkComboBox(self, variable=self.model_var, values=MODEL_OPTIONS).grid(
            row=row, column=1, columnspan=3, sticky="ew", padx=8, pady=6
        )
        row += 1

        self.next_row = row

    def _add_scenario_block(
        self,
        title: str,
        temp_default: str,
        max_tokens_default: str,
        prompt_default: Optional[str],
    ) -> Tuple[ctk.StringVar, ctk.StringVar, Optional[ctk.CTkTextbox], int]:
        row = self.next_row
        ctk.CTkLabel(self, text=title, font=ctk.CTkFont(weight="bold")).grid(
            row=row, column=0, columnspan=4, sticky="w", padx=8, pady=(16, 6)
        )
        row += 1

        temp_var = ctk.StringVar(value=temp_default)
        max_tokens_var = ctk.StringVar(value=max_tokens_default)

        ctk.CTkLabel(self, text="Temperature").grid(row=row, column=0, sticky="w", padx=8, pady=6)
        ctk.CTkEntry(self, textvariable=temp_var, width=120).grid(row=row, column=1, sticky="w", padx=8, pady=6)

        ctk.CTkLabel(self, text="Max tokens").grid(row=row, column=2, sticky="w", padx=8, pady=6)
        ctk.CTkEntry(self, textvariable=max_tokens_var, width=120).grid(row=row, column=3, sticky="w", padx=8, pady=6)
        row += 1

        prompt_box = None
        if prompt_default is not None:
            ctk.CTkLabel(self, text="System prompt").grid(row=row, column=0, columnspan=4, sticky="w", padx=8, pady=(4, 0))
            row += 1
            prompt_box = ctk.CTkTextbox(self, height=120)
            prompt_box.grid(row=row, column=0, columnspan=4, sticky="nsew", padx=8, pady=6)
            prompt_box.insert("1.0", prompt_default)
            row += 1

        self.next_row = row
        return temp_var, max_tokens_var, prompt_box, row

    def _add_scenarios_section(self) -> None:
        self.direct_temp_var, self.direct_max_tokens_var, _, _ = self._add_scenario_block(
            "1. Прямой ответ",
            "0.3",
            "1200",
            None,
        )

        self.step_temp_var, self.step_max_tokens_var, self.step_prompt_box, _ = self._add_scenario_block(
            "2. Решай пошагово",
            "0.3",
            "1200",
            DEFAULT_STEP_BY_STEP_PROMPT,
        )

        self.builder_temp_var, self.builder_max_tokens_var, self.builder_prompt_box, _ = self._add_scenario_block(
            "3а. Генерация system prompt нейросетью",
            "0.4",
            "500",
            DEFAULT_SELF_PROMPT_BUILDER,
        )

        self.self_answer_temp_var, self.self_answer_max_tokens_var, _, _ = self._add_scenario_block(
            "3б. Ответ через сгенерированный system prompt",
            "0.3",
            "1200",
            None,
        )

        self.experts_temp_var, self.experts_max_tokens_var, self.experts_prompt_box, _ = self._add_scenario_block(
            "4. Группа экспертов",
            "0.5",
            "1800",
            DEFAULT_EXPERTS_PROMPT,
        )

        self.comparison_temp_var, self.comparison_max_tokens_var, self.comparison_prompt_box, _ = self._add_scenario_block(
            "Анализ различий",
            "0.2",
            "1500",
            DEFAULT_COMPARISON_PROMPT,
        )

    @staticmethod
    def _textbox_value(box: Optional[ctk.CTkTextbox]) -> Optional[str]:
        if box is None:
            return None
        return box.get("1.0", "end").strip()

    def build_run_config(self) -> RunConfig:
        return RunConfig(
            direct=ScenarioConfig(
                temperature=float(self.direct_temp_var.get().strip()),
                max_tokens=int(self.direct_max_tokens_var.get().strip()),
            ),
            step_by_step=ScenarioConfig(
                temperature=float(self.step_temp_var.get().strip()),
                max_tokens=int(self.step_max_tokens_var.get().strip()),
                system_prompt=self._textbox_value(self.step_prompt_box),
            ),
            self_prompt_builder=ScenarioConfig(
                temperature=float(self.builder_temp_var.get().strip()),
                max_tokens=int(self.builder_max_tokens_var.get().strip()),
                system_prompt=self._textbox_value(self.builder_prompt_box),
            ),
            self_prompt_answer=ScenarioConfig(
                temperature=float(self.self_answer_temp_var.get().strip()),
                max_tokens=int(self.self_answer_max_tokens_var.get().strip()),
            ),
            experts=ScenarioConfig(
                temperature=float(self.experts_temp_var.get().strip()),
                max_tokens=int(self.experts_max_tokens_var.get().strip()),
                system_prompt=self._textbox_value(self.experts_prompt_box),
            ),
            comparison=ScenarioConfig(
                temperature=float(self.comparison_temp_var.get().strip()),
                max_tokens=int(self.comparison_max_tokens_var.get().strip()),
                system_prompt=self._textbox_value(self.comparison_prompt_box),
            ),
        )


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
        self.geometry("1280x920")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        default_request_url = os.getenv("REQUEST_URL", "http://127.0.0.1:8000/generate")
        default_model = os.getenv("DEFAULT_MODEL", MODEL_OPTIONS[0])
        if default_model not in MODEL_OPTIONS:
            default_model = MODEL_OPTIONS[0]

        self.request_url_var = ctk.StringVar(value=default_request_url)
        self.model_var = ctk.StringVar(value=default_model)
        self.last_report_path: Optional[Path] = None
        self.last_json_path: Optional[Path] = None
        self.last_csv_path: Optional[Path] = None

        self._build_ui()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top_buttons = ctk.CTkFrame(self)
        top_buttons.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        for i in range(5):
            top_buttons.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(top_buttons, text="Проверить /health", command=self.check_health).grid(row=0, column=0, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(top_buttons, text="Получить /models", command=self.load_models).grid(row=0, column=1, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(top_buttons, text="Запустить 4 сценария", command=self.run_scenarios).grid(row=0, column=2, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(top_buttons, text="Сохранить вопрос", command=self.save_prompt_to_file).grid(row=0, column=3, padx=8, pady=8, sticky="ew")
        ctk.CTkButton(top_buttons, text="Открыть отчёт", command=self.open_report).grid(row=0, column=4, padx=8, pady=8, sticky="ew")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=16, pady=(8, 16))

        self.main_tab = self.tabs.add("Запрос и запуск")
        self.settings_tab = self.tabs.add("Настройки")

        self._build_main_tab()
        self._build_settings_tab()

    def _build_main_tab(self) -> None:
        self.main_tab.grid_columnconfigure(0, weight=1)
        self.main_tab.grid_rowconfigure(1, weight=1)
        self.main_tab.grid_rowconfigure(3, weight=1)

        info = ctk.CTkFrame(self.main_tab)
        info.grid(row=0, column=0, sticky="ew", padx=8, pady=(8, 4))
        info.grid_columnconfigure((1, 3), weight=1)
        ctk.CTkLabel(info, text="Текущая модель:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, textvariable=self.model_var).grid(row=0, column=1, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, text="Request URL:").grid(row=0, column=2, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, textvariable=self.request_url_var).grid(row=0, column=3, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(self.main_tab, text="Вопрос пользователю / LLM").grid(row=1, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.prompt_text = ctk.CTkTextbox(self.main_tab, height=220)
        self.prompt_text.grid(row=2, column=0, sticky="nsew", padx=8, pady=8)
        self.prompt_text.insert("1.0", "Напишите здесь вопрос для LLM...")

        ctk.CTkLabel(self.main_tab, text="Лог / результат").grid(row=3, column=0, padx=8, pady=(10, 0), sticky="nw")
        self.output_text = ctk.CTkTextbox(self.main_tab)
        self.output_text.grid(row=4, column=0, sticky="nsew", padx=8, pady=8)
        self.main_tab.grid_rowconfigure(2, weight=1)
        self.main_tab.grid_rowconfigure(4, weight=1)

    def _build_settings_tab(self) -> None:
        self.settings_tab.grid_columnconfigure(0, weight=1)
        self.settings_tab.grid_rowconfigure(0, weight=1)
        self.settings_panel = SettingsPanel(self.settings_tab, self.model_var, self.request_url_var)
        self.settings_panel.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

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
            config = self.settings_panel.build_run_config()
            runner = FourModeRunner(
                self._client(),
                self.model_var.get().strip(),
                config,
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
        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", f"Проверьте числовые настройки: {exc}")
            self._log(f"Ошибка параметров: {exc}")
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
