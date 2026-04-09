from __future__ import annotations

import json
import threading
import tkinter as tk
from tkinter import ttk
from urllib import error, request


DEFAULT_BASE_URL = "http://127.0.0.1:8018"


class Day18GuiClient:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Day18 Test Client")
        self.root.geometry("1200x760")

        self.base_url_var = tk.StringVar(value=DEFAULT_BASE_URL)
        self.status_var = tk.StringVar(value="Ready")
        self.auto_refresh_var = tk.BooleanVar(value=False)

        self._build_layout()

    def _build_layout(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        controls = ttk.Frame(self.root, padding=12)
        controls.grid(row=0, column=0, sticky="ew")
        controls.columnconfigure(1, weight=1)

        ttk.Label(controls, text="Base URL").grid(row=0, column=0, sticky="w")
        ttk.Entry(controls, textvariable=self.base_url_var).grid(row=0, column=1, sticky="ew", padx=(8, 12))

        ttk.Button(controls, text="Health", command=lambda: self.fetch_endpoint("/health")).grid(row=0, column=2, padx=4)
        ttk.Button(controls, text="Agent Status", command=lambda: self.fetch_endpoint("/agent/status")).grid(row=0, column=3, padx=4)
        ttk.Button(controls, text="Latest Readings", command=lambda: self.fetch_endpoint("/readings/latest")).grid(row=0, column=4, padx=4)
        ttk.Button(controls, text="Aggregates", command=lambda: self.fetch_endpoint("/aggregates?window_type=15m&limit=100")).grid(row=0, column=5, padx=4)
        ttk.Button(controls, text="Latest Summary", command=lambda: self.fetch_endpoint("/summaries/latest")).grid(row=0, column=6, padx=4)
        ttk.Button(controls, text="Refresh All", command=self.refresh_all).grid(row=0, column=7, padx=(8, 0))

        bottom = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        bottom.grid(row=1, column=0, sticky="nsew")
        bottom.columnconfigure(0, weight=2)
        bottom.columnconfigure(1, weight=3)
        bottom.rowconfigure(0, weight=1)

        left = ttk.Frame(bottom)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        left.rowconfigure(3, weight=1)
        left.rowconfigure(5, weight=1)

        ttk.Label(left, text="Jobs").grid(row=0, column=0, sticky="w")
        self.jobs_tree = self._build_jobs_tree(left)
        self.jobs_tree.grid(row=1, column=0, sticky="nsew", pady=(4, 10))

        ttk.Label(left, text="Latest Readings").grid(row=2, column=0, sticky="w")
        self.readings_tree = self._build_readings_tree(left)
        self.readings_tree.grid(row=3, column=0, sticky="nsew", pady=(4, 10))

        ttk.Label(left, text="Aggregates").grid(row=4, column=0, sticky="w")
        self.aggregates_tree = self._build_aggregates_tree(left)
        self.aggregates_tree.grid(row=5, column=0, sticky="nsew", pady=(4, 0))

        right = ttk.Frame(bottom)
        right.grid(row=0, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)
        right.rowconfigure(3, weight=2)

        ttk.Label(right, text="Summary").grid(row=0, column=0, sticky="w")
        self.summary_text = tk.Text(right, wrap="word", height=12)
        self.summary_text.grid(row=1, column=0, sticky="nsew", pady=(4, 10))

        ttk.Label(right, text="Raw Response").grid(row=2, column=0, sticky="w")
        self.raw_text = tk.Text(right, wrap="none")
        self.raw_text.grid(row=3, column=0, sticky="nsew", pady=(4, 0))

        status_bar = ttk.Frame(self.root, padding=(12, 0, 12, 12))
        status_bar.grid(row=2, column=0, sticky="ew")
        status_bar.columnconfigure(1, weight=1)

        ttk.Checkbutton(
            status_bar,
            text="Auto refresh every 15s",
            variable=self.auto_refresh_var,
            command=self._toggle_auto_refresh,
        ).grid(row=0, column=0, sticky="w")
        ttk.Label(status_bar, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

    def _build_jobs_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("job_name", "last_status", "last_run_at", "next_run_at")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=7)
        for column, title, width in (
            ("job_name", "Job", 150),
            ("last_status", "Status", 90),
            ("last_run_at", "Last Run", 180),
            ("next_run_at", "Next Run", 180),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor="w")
        return tree

    def _build_readings_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("sensor_id", "alias", "value", "units", "collected_at")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=8)
        for column, title, width in (
            ("sensor_id", "Sensor", 200),
            ("alias", "Alias", 120),
            ("value", "Value", 70),
            ("units", "Units", 70),
            ("collected_at", "Collected", 170),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor="w")
        return tree

    def _build_aggregates_tree(self, parent: ttk.Frame) -> ttk.Treeview:
        columns = ("sensor_id", "avg_value", "min_value", "max_value", "last_value")
        tree = ttk.Treeview(parent, columns=columns, show="headings", height=8)
        for column, title, width in (
            ("sensor_id", "Sensor", 200),
            ("avg_value", "Avg", 70),
            ("min_value", "Min", 70),
            ("max_value", "Max", 70),
            ("last_value", "Last", 70),
        ):
            tree.heading(column, text=title)
            tree.column(column, width=width, anchor="w")
        return tree

    def fetch_endpoint(self, path: str) -> None:
        self.status_var.set(f"Loading {path} ...")
        threading.Thread(target=self._load_endpoint, args=(path,), daemon=True).start()

    def refresh_all(self) -> None:
        self.status_var.set("Refreshing all panels ...")
        threading.Thread(target=self._refresh_all_worker, daemon=True).start()

    def _refresh_all_worker(self) -> None:
        try:
            health = self._request_json("/health")
            status = self._request_json("/agent/status")
            readings = self._request_json("/readings/latest")
            aggregates = self._request_json("/aggregates?window_type=15m&limit=100")
            summary = self._request_json("/summaries/latest")
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self.status_var.set(f"Refresh failed: {exc}"))
            return

        def apply() -> None:
            self._render_health(health)
            self._render_agent_status(status)
            self._render_readings(readings)
            self._render_aggregates(aggregates)
            self._render_summary(summary)
            merged = {
                "health": health,
                "agent_status": status,
                "readings": readings,
                "aggregates": aggregates,
                "summary": summary,
            }
            self._set_raw_json(merged)
            self.status_var.set("Refresh complete")

        self.root.after(0, apply)

    def _load_endpoint(self, path: str) -> None:
        try:
            data = self._request_json(path)
        except Exception as exc:  # noqa: BLE001
            self.root.after(0, lambda: self.status_var.set(f"Request failed: {exc}"))
            return

        def apply() -> None:
            if path == "/health":
                self._render_health(data)
            elif path == "/agent/status":
                self._render_agent_status(data)
            elif path.startswith("/readings/latest"):
                self._render_readings(data)
            elif path.startswith("/aggregates"):
                self._render_aggregates(data)
            elif path.startswith("/summaries/latest") or path.startswith("/agent/summary/latest"):
                self._render_summary(data)
            self._set_raw_json(data)
            self.status_var.set(f"Loaded {path}")

        self.root.after(0, apply)

    def _request_json(self, path: str) -> dict:
        base_url = self.base_url_var.get().strip().rstrip("/")
        url = f"{base_url}{path}"
        req = request.Request(url, headers={"Accept": "application/json"})
        try:
            with request.urlopen(req, timeout=20) as response:
                payload = response.read().decode("utf-8")
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"HTTP {exc.code}: {body}") from exc
        except error.URLError as exc:
            raise RuntimeError(f"Connection error: {exc.reason}") from exc
        try:
            return json.loads(payload)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON response from {url}") from exc

    def _render_health(self, data: dict) -> None:
        status = data.get("status", "unknown")
        database = data.get("database", "unknown")
        self.status_var.set(f"Health: {status}, DB: {database}")

    def _render_agent_status(self, data: dict) -> None:
        self._fill_tree(
            self.jobs_tree,
            data.get("jobs", []),
            ("job_name", "last_status", "last_run_at", "next_run_at"),
        )
        latest_summary = data.get("latest_summary")
        if latest_summary:
            self._render_summary({"item": latest_summary})

    def _render_readings(self, data: dict) -> None:
        self._fill_tree(
            self.readings_tree,
            data.get("items", []),
            ("sensor_id", "alias", "value", "units", "collected_at"),
        )

    def _render_aggregates(self, data: dict) -> None:
        self._fill_tree(
            self.aggregates_tree,
            data.get("items", []),
            ("sensor_id", "avg_value", "min_value", "max_value", "last_value"),
        )

    def _render_summary(self, data: dict) -> None:
        item = data.get("item") or data.get("summary") or {}
        lines = []
        if item:
            if item.get("title"):
                lines.append(item["title"])
            if item.get("period_started_at") and item.get("period_finished_at"):
                lines.append(f"{item['period_started_at']} -> {item['period_finished_at']}")
            if item.get("content"):
                lines.append("")
                lines.append(item["content"])
        else:
            lines.append("No summary yet.")

        self.summary_text.delete("1.0", tk.END)
        self.summary_text.insert("1.0", "\n".join(lines))

    def _fill_tree(self, tree: ttk.Treeview, rows: list[dict], columns: tuple[str, ...]) -> None:
        tree.delete(*tree.get_children())
        for row in rows:
            values = [row.get(column, "") for column in columns]
            tree.insert("", tk.END, values=values)

    def _set_raw_json(self, data: dict) -> None:
        self.raw_text.delete("1.0", tk.END)
        self.raw_text.insert("1.0", json.dumps(data, ensure_ascii=False, indent=2))

    def _toggle_auto_refresh(self) -> None:
        if self.auto_refresh_var.get():
            self._schedule_auto_refresh()
        else:
            self.status_var.set("Auto refresh disabled")

    def _schedule_auto_refresh(self) -> None:
        if not self.auto_refresh_var.get():
            return
        self.refresh_all()
        self.root.after(15000, self._schedule_auto_refresh)


def main() -> None:
    root = tk.Tk()
    app = Day18GuiClient(root)
    app.refresh_all()
    root.mainloop()


if __name__ == "__main__":
    main()
