import html
import json
import os
import time
import webbrowser
from dataclasses import dataclass, asdict
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

DEFAULT_SCENARIOS_JSON = json.dumps(
    [
        {
            "name": "Базовый ответ",
            "enabled": True,
            "model": "openai/gpt-4o-mini",
            "system_prompt": "Ты полезный ассистент. Дай практичный и точный ответ на русском языке.",
            "temperature": 0.7,
            "max_tokens": 1200,
            "top_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
        },
        {
            "name": "Креативный ответ",
            "enabled": True,
            "model": "anthropic/claude-sonnet-4-20250514",
            "system_prompt": "Ты полезный ассистент. Предлагай нестандартные, но реалистичные варианты решения.",
            "temperature": 0.7,
            "max_tokens": 1200,
            "top_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
        },
        {
            "name": "Строгий эксперт",
            "enabled": True,
            "model": "openai/gpt-4.1",
            "system_prompt": "Ты строгий эксперт. Проверяй допущения, отмечай риски, ограничения и важные детали.",
            "temperature": 0.7,
            "max_tokens": 1200,
            "top_p": 1.0,
            "presence_penalty": 0.0,
            "frequency_penalty": 0.0,
        },
    ],
    ensure_ascii=False,
    indent=2,
)

DEFAULT_EVALUATION_PROMPT = """Ты выступаешь как LLM-as-a-judge.
Тебе передают:
1) вопрос пользователя,
2) критерии оценки,
3) набор ответов от разных сценариев,
4) технические параметры каждого запроса.

Твоя задача:
- оценить каждый ответ по каждому критерию по шкале от 1 до 10;
- дать короткое объяснение по каждому сценарию;
- отметить компромиссы: где ответ точнее, где полезнее, где рискованнее;
- отдельно проанализировать, как технические параметры запроса могли повлиять на результат;
- сравнивать не только качество текста, но и цену/скорость/объём генерации, если это видно из technical;
- явно указывать наблюдаемые связи, например между temperature, max_tokens, penalties, временем ответа, токенами и итоговым качеством;
- не придумывать причинность, если данных недостаточно: в этом случае прямо писать, что это гипотеза или слабый сигнал;
- вернуть РОВНО JSON без markdown.

Формат JSON:
{
  "summary_html": "<h3>...</h3><p>...</p><ul><li>...</li></ul>",
  "parameter_impact_html": "<h3>...</h3><ul><li>...</li></ul>",
  "winner": "Название сценария",
  "criteria": ["..."],
  "parameter_impact": [
    {
      "parameter": "temperature",
      "observation": "...",
      "scenarios": ["..."],
      "confidence": "low|medium|high"
    }
  ],
  "scores": [
    {
      "scenario": "Название сценария",
      "total_score": 0,
      "by_criteria": {
        "criterion_1": {"score": 0, "comment": "..."},
        "criterion_2": {"score": 0, "comment": "..."}
      },
      "strengths": ["...", "..."],
      "weaknesses": ["...", "..."],
      "technical_summary": "...",
      "verdict": "..."
    }
  ]
}
"""

DEFAULT_CRITERIA_TEXT = """Точность
креативность
разнообразность
Следование задаче
Риск галлюцинаций"""

DEFAULT_GLOBAL_SYSTEM_PROMPT = "Отвечай на русском языке."

AUTOLOAD_JUDGE_PROMPT_FILE = APP_DIR / "system_promt_judge.txt"
AUTOLOAD_CRITERIA_FILE = APP_DIR / "criteria.txt"
AUTOLOAD_REQUEST_SERIES_FILE = APP_DIR / "request_series.json"


@dataclass
class ScenarioConfig:
    name: str
    enabled: bool
    system_prompt: str
    temperature: float
    max_tokens: int
    model: Optional[str] = None
    top_p: float = 1.0
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0


@dataclass
class GatewayResponse:
    scenario_name: str
    content: str
    raw: Dict[str, Any]
    request_payload: Dict[str, Any]
    technical: Dict[str, Any]


class LLMGatewayClient:
    def __init__(self, request_url: str, timeout: int = 90):
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
        response = requests.get(f"{self.base_url}/health", headers=self.headers, timeout=self.timeout)
        response.raise_for_status()
        return response.json()

    def models(self) -> Any:
        response = requests.get(f"{self.base_url}/models", headers=self.headers, timeout=self.timeout)
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
        try:
            response.raise_for_status()
        except requests.HTTPError as exc:
            response_preview = (response.text or "").strip()
            if len(response_preview) > 4000:
                response_preview = response_preview[:4000] + "\n...<truncated>"
            payload_preview = json.dumps(payload, ensure_ascii=False, indent=2)
            raise ValueError(
                "Ошибка HTTP при вызове gateway:\n"
                f"URL: {self.request_url}\n"
                f"Status: {response.status_code}\n"
                f"Payload:\n{payload_preview}\n\n"
                f"Response body:\n{response_preview or '<empty>'}"
            ) from exc
        raw = response.json()
        content = (raw.get("content") or "").strip()
        usage = raw.get("usage") or {}
        technical = {
            "request_url": self.request_url,
            "http_status": response.status_code,
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "top_p": top_p,
            "presence_penalty": presence_penalty,
            "frequency_penalty": frequency_penalty,
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


class ExperimentRunner:
    def __init__(self, client: LLMGatewayClient, model: str):
        self.client = client
        self.model = model

    def run_series(
        self,
        user_question: str,
        global_system_prompt: str,
        scenarios: List[ScenarioConfig],
    ) -> List[GatewayResponse]:
        results: List[GatewayResponse] = []
        for scenario in scenarios:
            if not scenario.enabled:
                continue

            combined_system = "\n\n".join(
                part.strip()
                for part in [global_system_prompt.strip(), scenario.system_prompt.strip()]
                if part and part.strip()
            )

            messages = []
            if combined_system:
                messages.append({"role": "system", "content": combined_system})
            messages.append({"role": "user", "content": user_question})

            scenario_model = (scenario.model or self.model).strip()

            raw, payload, technical = self.client.generate(
                model=scenario_model,
                messages=messages,
                temperature=scenario.temperature,
                max_tokens=scenario.max_tokens,
                top_p=scenario.top_p,
                presence_penalty=scenario.presence_penalty,
                frequency_penalty=scenario.frequency_penalty,
            )
            results.append(
                GatewayResponse(
                    scenario_name=scenario.name,
                    content=raw.get("content", ""),
                    raw=raw,
                    request_payload=payload,
                    technical=technical,
                )
            )
        return results

    def evaluate_results(
        self,
        user_question: str,
        criteria: List[str],
        results: List[GatewayResponse],
        evaluation_system_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> Tuple[Dict[str, Any], Dict[str, Any], Dict[str, Any]]:
        results_payload = []
        for item in results:
            results_payload.append(
                {
                    "scenario": item.scenario_name,
                    "answer": item.content,
                    "technical": item.technical,
                }
            )

        user_message = {
            "question": user_question,
            "criteria": criteria,
            "answers": results_payload,
        }

        raw, payload, technical = self.client.generate(
            model=self.model,
            messages=[
                {"role": "system", "content": evaluation_system_prompt.strip()},
                {"role": "user", "content": json.dumps(user_message, ensure_ascii=False, indent=2)},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        parsed = safe_json_parse(raw.get("content", ""))
        return parsed, payload, technical


def safe_json_parse(text: str) -> Dict[str, Any]:
    cleaned = (text or "").strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.lower().startswith("json"):
            cleaned = cleaned[4:].strip()
    try:
        return json.loads(cleaned)
    except Exception:
        start = cleaned.find("{")
        end = cleaned.rfind("}")
        if start != -1 and end != -1 and end > start:
            return json.loads(cleaned[start:end + 1])
        raise ValueError("Не удалось распарсить JSON оценки от модели.")


def parse_scenarios_json(text: str) -> List[ScenarioConfig]:
    data = json.loads(text)
    if not isinstance(data, list) or not data:
        raise ValueError("JSON сценариев должен быть непустым массивом.")
    scenarios = []
    for idx, item in enumerate(data, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Элемент #{idx} в сценариях должен быть объектом.")
        scenarios.append(
            ScenarioConfig(
                name=str(item.get("name") or f"Сценарий {idx}"),
                enabled=bool(item.get("enabled", True)),
                system_prompt=str(item.get("system_prompt") or ""),
                temperature=float(item.get("temperature", 0.3)),
                max_tokens=int(item.get("max_tokens", 1200)),
                model=(str(item.get("model")).strip() or None) if item.get("model") is not None else None,
                top_p=float(item.get("top_p", 1.0)),
                presence_penalty=float(item.get("presence_penalty", 0.0)),
                frequency_penalty=float(item.get("frequency_penalty", 0.0)),
            )
        )
    return scenarios


def parse_criteria_text(text: str) -> List[str]:
    criteria = [line.strip("-• \t\r") for line in text.splitlines() if line.strip()]
    if not criteria:
        raise ValueError("Нужно указать хотя бы один критерий оценки.")
    return criteria


def _safe_num(value: Any) -> float:
    return value if isinstance(value, (int, float)) else 0


def technical_table(technical: Dict[str, Any]) -> str:
    rows = []
    for key, value in technical.items():
        rendered = html.escape(json.dumps(value, ensure_ascii=False)) if isinstance(value, (dict, list)) else html.escape(str(value))
        rows.append(f"<tr><td>{html.escape(str(key))}</td><td>{rendered}</td></tr>")
    return (
        '<table class="tech-table"><thead><tr><th>Параметр</th><th>Значение</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def scores_table_html(criteria: List[str], evaluation_data: Dict[str, Any]) -> str:
    rows = []
    for item in evaluation_data.get("scores", []):
        by_criteria = item.get("by_criteria", {}) or {}
        cols = [
            f"<td>{html.escape(str(item.get('scenario', '')))}</td>",
            f"<td>{html.escape(str(item.get('total_score', '')))}</td>",
        ]
        for criterion in criteria:
            c = by_criteria.get(criterion, {}) or {}
            score = c.get("score", "")
            comment = c.get("comment", "")
            cols.append(
                "<td>"
                f"<div><strong>{html.escape(str(score))}</strong></div>"
                f"<div class='muted'>{html.escape(str(comment))}</div>"
                "</td>"
            )
        cols.append(f"<td>{html.escape(str(item.get('verdict', '')))}</td>")
        rows.append("<tr>" + "".join(cols) + "</tr>")

    header = ["<th>Сценарий</th>", "<th>Итог</th>"] + [f"<th>{html.escape(c)}</th>" for c in criteria] + ["<th>Вердикт</th>"]
    return (
        '<table class="score-table"><thead><tr>'
        + "".join(header)
        + "</tr></thead><tbody>"
        + "".join(rows)
        + "</tbody></table>"
    )


def scenario_comparison_table_html(results: List[GatewayResponse], evaluation_data: Dict[str, Any]) -> str:
    score_map = {
        str(item.get("scenario", "")): item for item in (evaluation_data.get("scores", []) or []) if isinstance(item, dict)
    }

    rows = []
    for result in results:
        technical = result.technical or {}
        score_item = score_map.get(result.scenario_name, {})
        technical_summary = score_item.get("technical_summary", "") if isinstance(score_item, dict) else ""
        verdict = score_item.get("verdict", "") if isinstance(score_item, dict) else ""
        total_score = score_item.get("total_score", "") if isinstance(score_item, dict) else ""

        def esc(v: Any) -> str:
            return html.escape("" if v is None else str(v))

        rows.append(
            "<tr>"
            f"<td>{esc(result.scenario_name)}</td>"
            f"<td>{esc(technical.get('model'))}</td>"
            f"<td>{esc(technical.get('temperature'))}</td>"
            f"<td>{esc(technical.get('top_p'))}</td>"
            f"<td>{esc(technical.get('max_tokens'))}</td>"
            f"<td>{esc(technical.get('presence_penalty'))}</td>"
            f"<td>{esc(technical.get('frequency_penalty'))}</td>"
            f"<td>{esc(technical.get('response_time_ms'))}</td>"
            f"<td>{esc(technical.get('total_tokens'))}</td>"
            f"<td>{esc(total_score)}</td>"
            f"<td>{esc(technical_summary)}</td>"
            f"<td>{esc(verdict)}</td>"
            "</tr>"
        )

    if not rows:
        return "<p>Нет данных для сравнения сценариев.</p>"

    return (
        '<table class="score-table"><thead><tr>'
        '<th>Сценарий</th>'
        '<th>Модель</th>'
        '<th>Temperature</th>'
        '<th>Top-p</th>'
        '<th>Max tokens</th>'
        '<th>Presence penalty</th>'
        '<th>Frequency penalty</th>'
        '<th>Latency, ms</th>'
        '<th>Total tokens</th>'
        '<th>Score</th>'
        '<th>Technical summary</th>'
        '<th>Verdict</th>'
        '</tr></thead><tbody>'
        + ''.join(rows)
        + '</tbody></table>'
    )


def build_chart_script(results: List[GatewayResponse], evaluation_data: Dict[str, Any]) -> str:
    labels = [item.scenario_name for item in results]
    times = [_safe_num(item.technical.get("response_time_ms")) for item in results]
    totals = [_safe_num(item.technical.get("total_tokens")) for item in results]
    prompt_tokens = [_safe_num(item.technical.get("prompt_tokens")) for item in results]
    completion_tokens = [_safe_num(item.technical.get("completion_tokens")) for item in results]

    criteria = evaluation_data.get("criteria", []) or []
    score_items = evaluation_data.get("scores", []) or []
    scenario_to_total = {item.get("scenario"): item.get("total_score", 0) for item in score_items}
    total_scores = [scenario_to_total.get(label, 0) for label in labels]

    return f"""
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
<script>
const labels = {json.dumps(labels, ensure_ascii=False)};

new Chart(document.getElementById('timeChart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [{{ label: 'Время ответа, мс', data: {json.dumps(times)} }}]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});

new Chart(document.getElementById('tokensChart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [
      {{ label: 'Prompt tokens', data: {json.dumps(prompt_tokens)} }},
      {{ label: 'Completion tokens', data: {json.dumps(completion_tokens)} }},
      {{ label: 'Total tokens', data: {json.dumps(totals)} }}
    ]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});

new Chart(document.getElementById('scoreChart'), {{
  type: 'bar',
  data: {{
    labels,
    datasets: [{{ label: 'Итоговая оценка judge-модели', data: {json.dumps(total_scores)} }}]
  }},
  options: {{ responsive: true, maintainAspectRatio: false }}
}});
</script>
"""


def build_html_report(
    question: str,
    model: str,
    global_system_prompt: str,
    criteria: List[str],
    scenarios: List[ScenarioConfig],
    results: List[GatewayResponse],
    evaluation_data: Dict[str, Any],
    evaluation_technical: Dict[str, Any],
) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    winner = evaluation_data.get("winner", "—")
    summary_html = evaluation_data.get("summary_html", "<p>Нет summary_html от judge-модели.</p>")
    parameter_impact_html = evaluation_data.get("parameter_impact_html", "<p>Judge-модель не вернула отдельный анализ влияния параметров.</p>")

    scenario_config_map = {s.name: s for s in scenarios}

    result_blocks = []
    for item in results:
        cfg = scenario_config_map.get(item.scenario_name)
        cfg_html = ""
        if cfg:
            cfg_html = f"""
            <div class="meta-grid">
                <div><strong>Модель сценария</strong><br>{html.escape(str(cfg.model or model))}</div>
                <div><strong>Temperature</strong><br>{html.escape(str(cfg.temperature))}</div>
                <div><strong>Max tokens</strong><br>{html.escape(str(cfg.max_tokens))}</div>
                <div><strong>Top P</strong><br>{html.escape(str(cfg.top_p))}</div>
                <div><strong>Presence penalty</strong><br>{html.escape(str(cfg.presence_penalty))}</div>
                <div><strong>Frequency penalty</strong><br>{html.escape(str(cfg.frequency_penalty))}</div>
            </div>
            <details>
                <summary>System prompt сценария</summary>
                <pre>{html.escape(cfg.system_prompt)}</pre>
            </details>
            """

        result_blocks.append(
            f"""
            <section class="card">
                <h2>{html.escape(item.scenario_name)}</h2>
                {cfg_html}
                <h3>Ответ модели</h3>
                <pre>{html.escape(item.content)}</pre>
                <h3>Технические параметры</h3>
                {technical_table(item.technical)}
                <details>
                    <summary>Payload запроса</summary>
                    <pre>{html.escape(json.dumps(item.request_payload, ensure_ascii=False, indent=2))}</pre>
                </details>
                <details>
                    <summary>Raw response</summary>
                    <pre>{html.escape(json.dumps(item.raw, ensure_ascii=False, indent=2))}</pre>
                </details>
            </section>
            """
        )

    return f"""<!DOCTYPE html>
<html lang="ru">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>LLM batch report</title>
  <style>
    body {{ font-family: Arial, sans-serif; margin: 0; padding: 24px; background: #f6f7fb; color: #1d2433; }}
    .container {{ max-width: 1440px; margin: 0 auto; }}
    .card {{ background: white; border-radius: 16px; padding: 20px; margin-bottom: 20px; box-shadow: 0 8px 30px rgba(0,0,0,0.08); }}
    h1, h2, h3 {{ margin-top: 0; }}
    pre {{ white-space: pre-wrap; word-wrap: break-word; background: #0f172a; color: #e2e8f0; padding: 14px; border-radius: 12px; overflow-x: auto; }}
    .meta-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 12px; margin-bottom: 16px; }}
    .meta-grid > div {{ background: #eef2ff; padding: 12px; border-radius: 12px; }}
    .charts {{ display: grid; grid-template-columns: 1fr; gap: 20px; }}
    .chart-box {{ height: 340px; }}
    .tech-table, .score-table {{ width: 100%; border-collapse: collapse; margin: 12px 0 16px; background: #fff; }}
    .tech-table th, .tech-table td, .score-table th, .score-table td {{ border: 1px solid #d8ddea; padding: 8px 10px; text-align: left; vertical-align: top; }}
    .tech-table th, .score-table th {{ background: #eef2ff; }}
    .muted {{ color: #576074; font-size: 12px; margin-top: 6px; }}
    details {{ margin: 12px 0; }}
    .pill {{ display: inline-block; padding: 6px 12px; border-radius: 999px; background: #dbeafe; font-weight: bold; }}
  </style>
</head>
<body>
  <div class="container">
    <section class="card">
      <h1>Отчёт по серии запросов к LLM</h1>
      <div class="meta-grid">
        <div><strong>Время</strong><br>{html.escape(timestamp)}</div>
        <div><strong>Модель</strong><br>{html.escape(model)}</div>
        <div><strong>Количество сценариев</strong><br>{len(results)}</div>
        <div><strong>Победитель</strong><br><span class="pill">{html.escape(str(winner))}</span></div>
      </div>

      <h2>Вопрос</h2>
      <pre>{html.escape(question)}</pre>

      <h2>Глобальный system prompt</h2>
      <pre>{html.escape(global_system_prompt)}</pre>

      <h2>Критерии оценки</h2>
      <ul>{''.join(f'<li>{html.escape(c)}</li>' for c in criteria)}</ul>
    </section>

    <section class="card">
      <h2>Сводка judge-модели</h2>
      <div>{summary_html}</div>
      <h3>Таблица оценок</h3>
      {scores_table_html(criteria, evaluation_data)}
      <h3>Сравнение сценариев и техпараметров</h3>
      {scenario_comparison_table_html(results, evaluation_data)}
      <h3>Влияние технических параметров</h3>
      <div>{parameter_impact_html}</div>
      <details>
        <summary>Технические параметры judge-запроса</summary>
        {technical_table(evaluation_technical)}
      </details>
    </section>

    <section class="card">
      <h2>Графики</h2>
      <div class="charts">
        <div>
          <h3>Время ответа</h3>
          <div class="chart-box"><canvas id="timeChart"></canvas></div>
        </div>
        <div>
          <h3>Токены</h3>
          <div class="chart-box"><canvas id="tokensChart"></canvas></div>
        </div>
        <div>
          <h3>Итоговые оценки</h3>
          <div class="chart-box"><canvas id="scoreChart"></canvas></div>
        </div>
      </div>
    </section>

    {''.join(result_blocks)}
  </div>
  {build_chart_script(results, evaluation_data)}
</body>
</html>
"""


def export_json(
    report_stem: str,
    question: str,
    model: str,
    global_system_prompt: str,
    criteria: List[str],
    scenarios: List[ScenarioConfig],
    results: List[GatewayResponse],
    evaluation_data: Dict[str, Any],
    evaluation_payload: Dict[str, Any],
    evaluation_technical: Dict[str, Any],
) -> Path:
    payload = {
        "created_at": datetime.now().isoformat(),
        "question": question,
        "model": model,
        "global_system_prompt": global_system_prompt,
        "criteria": criteria,
        "scenarios": [asdict(s) for s in scenarios],
        "results": [
            {
                "scenario_name": item.scenario_name,
                "content": item.content,
                "request_payload": item.request_payload,
                "technical": item.technical,
                "raw": item.raw,
            }
            for item in results
        ],
        "evaluation": {
            "result": evaluation_data,
            "request_payload": evaluation_payload,
            "technical": evaluation_technical,
        },
    }
    path = REPORTS_DIR / f"{report_stem}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path



class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("LLM Experiment Lab")
        self.geometry("1460x980")
        ctk.set_appearance_mode("System")
        ctk.set_default_color_theme("blue")

        default_request_url = os.getenv("REQUEST_URL", "http://127.0.0.1:8000/generate")
        default_model = os.getenv("DEFAULT_MODEL", MODEL_OPTIONS[0])
        if default_model not in MODEL_OPTIONS:
            default_model = MODEL_OPTIONS[0]

        self.request_url_var = ctk.StringVar(value=default_request_url)
        self.model_var = ctk.StringVar(value=default_model)
        self.last_report_path: Optional[Path] = None

        self._build_ui()
        self._autoload_startup_files()

    def _build_ui(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        top = ctk.CTkFrame(self)
        top.grid(row=0, column=0, sticky="ew", padx=12, pady=(12, 6))
        for i in range(6):
            top.grid_columnconfigure(i, weight=1)

        ctk.CTkButton(top, text="Проверить /health", command=self.check_health).grid(row=0, column=0, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(top, text="Получить /models", command=self.load_models).grid(row=0, column=1, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(top, text="Запустить серию", command=self.run_experiments).grid(row=0, column=2, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(top, text="Сохранить вопрос", command=self.save_prompt_to_file).grid(row=0, column=3, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(top, text="Открыть отчёт", command=self.open_report).grid(row=0, column=4, padx=6, pady=6, sticky="ew")
        ctk.CTkButton(top, text="Сохранить сценарии JSON", command=self.save_scenarios_json).grid(row=0, column=5, padx=6, pady=6, sticky="ew")

        self.tabs = ctk.CTkTabview(self)
        self.tabs.grid(row=1, column=0, sticky="nsew", padx=12, pady=(6, 12))

        self.run_tab = self.tabs.add("Запуск")
        self.settings_tab = self.tabs.add("Настройки")
        self.scenarios_tab = self.tabs.add("Сценарии JSON")
        self.evaluation_tab = self.tabs.add("Judge / критерии")

        self._build_run_tab()
        self._build_settings_tab()
        self._build_scenarios_tab()
        self._build_evaluation_tab()

    def _build_run_tab(self) -> None:
        self.run_tab.grid_columnconfigure(0, weight=1)
        self.run_tab.grid_rowconfigure(2, weight=1)
        self.run_tab.grid_rowconfigure(4, weight=1)

        info = ctk.CTkFrame(self.run_tab)
        info.grid(row=0, column=0, sticky="ew", padx=8, pady=8)
        info.grid_columnconfigure((1, 3), weight=1)

        ctk.CTkLabel(info, text="Текущая модель:").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, textvariable=self.model_var).grid(row=0, column=1, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, text="Request URL:").grid(row=0, column=2, sticky="w", padx=8, pady=8)
        ctk.CTkLabel(info, textvariable=self.request_url_var).grid(row=0, column=3, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(self.run_tab, text="Вопрос").grid(row=1, column=0, sticky="nw", padx=8)
        self.prompt_text = ctk.CTkTextbox(self.run_tab, height=220)
        self.prompt_text.grid(row=2, column=0, sticky="nsew", padx=8, pady=(4, 8))
        self.prompt_text.insert("1.0", "Напишите здесь вопрос для серии LLM-запросов...")

        ctk.CTkLabel(self.run_tab, text="Лог выполнения").grid(row=3, column=0, sticky="nw", padx=8)
        self.output_text = ctk.CTkTextbox(self.run_tab)
        self.output_text.grid(row=4, column=0, sticky="nsew", padx=8, pady=(4, 8))

    def _build_settings_tab(self) -> None:
        self.settings_tab.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(self.settings_tab, text="Request URL").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkEntry(self.settings_tab, textvariable=self.request_url_var).grid(row=0, column=1, sticky="ew", padx=8, pady=8)

        ctk.CTkLabel(self.settings_tab, text="Модель, общая для всех запросов и Judge-модели ").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        ctk.CTkComboBox(self.settings_tab, variable=self.model_var, values=MODEL_OPTIONS).grid(row=1, column=1, sticky="ew", padx=8, pady=8)

        ctk.CTkLabel(self.settings_tab, text="Глобальный system prompt").grid(row=2, column=0, sticky="nw", padx=8, pady=8)
        self.global_system_prompt_box = ctk.CTkTextbox(self.settings_tab, height=160)
        self.global_system_prompt_box.grid(row=2, column=1, sticky="nsew", padx=8, pady=8)
        self.global_system_prompt_box.insert("1.0", DEFAULT_GLOBAL_SYSTEM_PROMPT)

        self.settings_tab.grid_rowconfigure(2, weight=1)

    def _build_scenarios_tab(self) -> None:
        self.scenarios_tab.grid_columnconfigure(0, weight=1)
        self.scenarios_tab.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(
            self.scenarios_tab,
            text="Список сценариев в JSON. Один объект = один запрос к модели. Можно задать поле model, иначе используется модель из настроек.",
        ).grid(row=0, column=0, sticky="w", padx=8, pady=(8, 4))

        self.scenarios_box = ctk.CTkTextbox(self.scenarios_tab)
        self.scenarios_box.grid(row=1, column=0, sticky="nsew", padx=8, pady=8)
        self.scenarios_box.insert("1.0", DEFAULT_SCENARIOS_JSON)

    def _build_evaluation_tab(self) -> None:
        self.evaluation_tab.grid_columnconfigure(1, weight=1)
        self.evaluation_tab.grid_rowconfigure(3, weight=1)
        self.evaluation_tab.grid_rowconfigure(5, weight=1)

        ctk.CTkLabel(self.evaluation_tab, text="Temperature judge-модели").grid(row=0, column=0, sticky="w", padx=8, pady=8)
        self.eval_temp_var = ctk.StringVar(value="0.2")
        ctk.CTkEntry(self.evaluation_tab, textvariable=self.eval_temp_var, width=120).grid(row=0, column=1, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(self.evaluation_tab, text="Max tokens judge-модели").grid(row=1, column=0, sticky="w", padx=8, pady=8)
        self.eval_max_tokens_var = ctk.StringVar(value="10000")
        ctk.CTkEntry(self.evaluation_tab, textvariable=self.eval_max_tokens_var, width=120).grid(row=1, column=1, sticky="w", padx=8, pady=8)

        ctk.CTkLabel(self.evaluation_tab, text="Критерии оценки, по одному на строку").grid(row=2, column=0, sticky="nw", padx=8, pady=8)
        self.criteria_box = ctk.CTkTextbox(self.evaluation_tab, height=180)
        self.criteria_box.grid(row=2, column=1, sticky="nsew", padx=8, pady=8)
        self.criteria_box.insert("1.0", DEFAULT_CRITERIA_TEXT)

        ctk.CTkLabel(self.evaluation_tab, text="System prompt для judge-модели").grid(row=4, column=0, sticky="nw", padx=8, pady=8)
        self.eval_prompt_box = ctk.CTkTextbox(self.evaluation_tab)
        self.eval_prompt_box.grid(row=4, column=1, sticky="nsew", padx=8, pady=8)
        self.eval_prompt_box.insert("1.0", DEFAULT_EVALUATION_PROMPT)

    def _set_textbox_content(self, textbox: ctk.CTkTextbox, content: str) -> None:
        textbox.delete("1.0", "end")
        textbox.insert("1.0", content)

    def _autoload_text_file(self, path: Path, textbox: ctk.CTkTextbox, description: str) -> None:
        if not path.exists():
            self._log(f"Автозагрузка пропущена: файл {path.name} не найден.")
            return
        content = path.read_text(encoding="utf-8").strip()
        self._set_textbox_content(textbox, content)
        self._log(f"Автозагружен {description} из файла: {path}")

    def _autoload_json_file(self, path: Path, textbox: ctk.CTkTextbox, description: str) -> None:
        if not path.exists():
            self._log(f"Автозагрузка пропущена: файл {path.name} не найден.")
            return
        raw_content = path.read_text(encoding="utf-8")
        parsed = json.loads(raw_content)
        formatted = json.dumps(parsed, ensure_ascii=False, indent=2)
        self._set_textbox_content(textbox, formatted)
        self._log(f"Автозагружен {description} из файла: {path}")

    def _autoload_startup_files(self) -> None:
        try:
            self._autoload_text_file(
                AUTOLOAD_JUDGE_PROMPT_FILE,
                self.eval_prompt_box,
                "system prompt judge",
            )
            self._autoload_text_file(
                AUTOLOAD_CRITERIA_FILE,
                self.criteria_box,
                "критерии judge",
            )
            self._autoload_json_file(
                AUTOLOAD_REQUEST_SERIES_FILE,
                self.scenarios_box,
                "JSON серии запросов",
            )
        except Exception as exc:
            self._log(f"Ошибка автозагрузки стартовых файлов: {exc}")
            messagebox.showwarning("Ошибка автозагрузки", str(exc))

    def _log(self, text: str) -> None:
        self.output_text.insert("end", text + "\n")
        self.output_text.see("end")
        self.update_idletasks()

    def _client(self) -> LLMGatewayClient:
        return LLMGatewayClient(request_url=self.request_url_var.get().strip(), timeout=600)

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

    def save_scenarios_json(self) -> None:
        content = self.scenarios_box.get("1.0", "end").strip()
        file_path = filedialog.asksaveasfilename(
            title="Сохранить сценарии",
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if not file_path:
            return
        Path(file_path).write_text(content, encoding="utf-8")
        self._log(f"Сценарии сохранены: {file_path}")

    def run_experiments(self) -> None:
        question = self._question()
        if not question or question == "Напишите здесь вопрос для серии LLM-запросов...":
            messagebox.showwarning("Нет вопроса", "Введите вопрос для LLM.")
            return

        self.output_text.delete("1.0", "end")
        try:
            global_system_prompt = self.global_system_prompt_box.get("1.0", "end").strip()
            scenarios = parse_scenarios_json(self.scenarios_box.get("1.0", "end").strip())
            criteria = parse_criteria_text(self.criteria_box.get("1.0", "end").strip())
            eval_temp = float(self.eval_temp_var.get().strip())
            eval_max_tokens = int(self.eval_max_tokens_var.get().strip())
            eval_prompt = self.eval_prompt_box.get("1.0", "end").strip()

            enabled_count = len([s for s in scenarios if s.enabled])
            if enabled_count == 0:
                raise ValueError("Нет ни одного включённого сценария.")

            self._log(f"Запуск серии запросов. Активных сценариев: {enabled_count}")
            runner = ExperimentRunner(self._client(), self.model_var.get().strip())
            results = runner.run_series(question, global_system_prompt, scenarios)

            for item in results:
                self._log(f"\n===== {item.scenario_name} =====\n{item.content}\n")
                self._log("Технические параметры:\n" + json.dumps(item.technical, ensure_ascii=False, indent=2))

            self._log("\nЗапуск judge-модели для анализа ответов...")
            evaluation_data, evaluation_payload, evaluation_technical = runner.evaluate_results(
                user_question=question,
                criteria=criteria,
                results=results,
                evaluation_system_prompt=eval_prompt,
                temperature=eval_temp,
                max_tokens=eval_max_tokens,
            )

            self._log("Payload judge-запроса:\n" + json.dumps(evaluation_payload, ensure_ascii=False, indent=2))
            self._log("Технические параметры judge-запроса:\n" + json.dumps(evaluation_technical, ensure_ascii=False, indent=2))
            self._log("Результат judge-модели:\n" + json.dumps(evaluation_data, ensure_ascii=False, indent=2))

            report_stem = f"llm_experiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            html_report = build_html_report(
                question=question,
                model=self.model_var.get().strip(),
                global_system_prompt=global_system_prompt,
                criteria=criteria,
                scenarios=scenarios,
                results=results,
                evaluation_data=evaluation_data,
                evaluation_technical=evaluation_technical,
            )
            report_path = REPORTS_DIR / f"{report_stem}.html"
            report_path.write_text(html_report, encoding="utf-8")
                        

            self.last_report_path = report_path
                        

            webbrowser.open(report_path.resolve().as_uri())

            self._log(f"\nHTML-отчёт сохранён: {report_path}")
                        
            messagebox.showinfo(
                "Готово",
                f"Созданы файлы:\n{report_path}\n\nHTML-отчёт открыт в браузере.",
            )

        except ValueError as exc:
            messagebox.showerror("Ошибка параметров", str(exc))
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
