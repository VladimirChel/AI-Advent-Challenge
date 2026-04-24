from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

from app.models import DebtRecord


def _load_snapshot(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _to_float(value: Any) -> float:
    return float(value or 0.0)


def _fmt_money(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


@dataclass(slots=True)
class AnalyticsStore:
    snapshots: list[dict[str, Any]]

    @classmethod
    def from_dir(cls, snapshots_dir: Path) -> "AnalyticsStore":
        snapshots = [_load_snapshot(path) for path in sorted(snapshots_dir.glob("*.json"))]
        if not snapshots:
            raise ValueError("No snapshots found. Run index first.")
        deduped: dict[tuple[str, str], dict[str, Any]] = {}
        for snapshot in snapshots:
            key = (snapshot["report_date"], snapshot["source_file"])
            deduped[key] = snapshot
        ordered = sorted(deduped.values(), key=lambda item: item["report_date"])
        return cls(snapshots=ordered)

    @property
    def latest(self) -> dict[str, Any]:
        return self.snapshots[-1]

    @property
    def latest_date(self) -> str:
        return self.latest["report_date"]

    def _window(self, days: int = 3) -> list[dict[str, Any]]:
        return self.snapshots[-days:]

    def totals_timeline(self, days: int = 3) -> list[dict[str, Any]]:
        return [
            {
                "report_date": snapshot["report_date"],
                "total_debt": _to_float(snapshot["totals"]["total_debt"]),
                "total_overdue_debt": _to_float(snapshot["totals"]["total_overdue_debt"]),
            }
            for snapshot in self._window(days)
        ]

    def _aggregate_latest(self, field: str) -> list[dict[str, Any]]:
        totals: dict[str, dict[str, float]] = defaultdict(lambda: {"debt": 0.0, "overdue_debt": 0.0})
        for record in self.latest["records"]:
            key = record[field]
            totals[key]["debt"] += _to_float(record["debt"])
            totals[key]["overdue_debt"] += _to_float(record["overdue_debt"])
        rows = [
            {"name": name, "debt": payload["debt"], "overdue_debt": payload["overdue_debt"]}
            for name, payload in totals.items()
        ]
        rows.sort(key=lambda item: item["debt"], reverse=True)
        return rows

    def top_clients(self, limit: int = 5) -> list[dict[str, Any]]:
        return self._aggregate_latest("client_name")[:limit]

    def top_managers(self, limit: int = 5) -> list[dict[str, Any]]:
        return self._aggregate_latest("manager_name")[:limit]

    def _aggregate_for_snapshot(self, snapshot: dict[str, Any], field: str) -> dict[str, dict[str, float]]:
        totals: dict[str, dict[str, float]] = defaultdict(lambda: {"debt": 0.0, "overdue_debt": 0.0})
        for record in snapshot["records"]:
            key = record[field]
            totals[key]["debt"] += _to_float(record["debt"])
            totals[key]["overdue_debt"] += _to_float(record["overdue_debt"])
        return totals

    def entity_details(self, name: str, entity_type: str | None = None, days: int = 3) -> dict[str, Any] | None:
        candidates = ["client_name", "manager_name"] if entity_type is None else [f"{entity_type}_name"]
        latest_match: dict[str, Any] | None = None
        timeline: list[dict[str, Any]] = []
        for snapshot in self._window(days):
            for field in candidates:
                aggregated = self._aggregate_for_snapshot(snapshot, field)
                for entity_name, payload in aggregated.items():
                    if entity_name.casefold() == name.casefold():
                        row = {
                            "report_date": snapshot["report_date"],
                            "entity_type": field.replace("_name", ""),
                            "name": entity_name,
                            "debt": payload["debt"],
                            "overdue_debt": payload["overdue_debt"],
                        }
                        timeline.append(row)
                        latest_match = row
        if latest_match is None:
            return None
        latest_snapshot_records = [
            record
            for record in self.latest["records"]
            if (
                record.get(f"{latest_match['entity_type']}_name", "").casefold() == latest_match["name"].casefold()
            )
        ]
        latest_snapshot_records.sort(key=lambda item: _to_float(item["debt"]), reverse=True)
        latest_match["contracts"] = latest_snapshot_records[:10]
        latest_match["timeline"] = timeline
        return latest_match

    def summary_context(self, question: str, days: int = 3) -> dict[str, Any]:
        latest = self.latest
        timeline = self.totals_timeline(days)
        previous = timeline[-2] if len(timeline) >= 2 else None
        latest_total = _to_float(latest["totals"]["total_debt"])
        latest_overdue = _to_float(latest["totals"]["total_overdue_debt"])
        return {
            "question": question,
            "report_date": latest["report_date"],
            "currency": latest["currency"],
            "data_points_days": len(timeline),
            "totals": {
                "total_debt": latest_total,
                "total_overdue_debt": latest_overdue,
                "delta_total_debt": latest_total - _to_float(previous["total_debt"]) if previous else None,
                "delta_total_overdue_debt": latest_overdue - _to_float(previous["total_overdue_debt"]) if previous else None,
            },
            "top_clients": self.top_clients(limit=5),
            "top_managers": self.top_managers(limit=5),
            "timeline": timeline,
        }

    def render_today_summary(self) -> str:
        latest = self.latest
        return (
            f"Отчет на {latest['report_date']}\n"
            f"Общий долг: {_fmt_money(_to_float(latest['totals']['total_debt']))} {latest['currency']}\n"
            f"Просрочено: {_fmt_money(_to_float(latest['totals']['total_overdue_debt']))} {latest['currency']}"
        )

    def render_top_summary(self) -> str:
        clients = self.top_clients(limit=5)
        lines = [f"Топ-5 контрагентов по долгу на {self.latest_date}:"]
        for index, item in enumerate(clients, start=1):
            lines.append(
                f"{index}. {item['name']} — {_fmt_money(item['debt'])} RUB, просрочка {_fmt_money(item['overdue_debt'])} RUB"
            )
        return "\n".join(lines)

    def render_trend_summary(self, days: int = 3) -> str:
        timeline = self.totals_timeline(days)
        lines = [f"Динамика по дебиторской задолженности за {len(timeline)} дн.:"]
        for row in timeline:
            lines.append(
                f"{row['report_date']}: долг {_fmt_money(row['total_debt'])} RUB, "
                f"просрочка {_fmt_money(row['total_overdue_debt'])} RUB"
            )
        if len(timeline) >= 2:
            latest = timeline[-1]
            previous = timeline[-2]
            lines.append(
                f"Изменение к предыдущему дню: долг {_fmt_money(latest['total_debt'] - previous['total_debt'])} RUB, "
                f"просрочка {_fmt_money(latest['total_overdue_debt'] - previous['total_overdue_debt'])} RUB"
            )
        else:
            lines.append("Для полноценного тренда нужно больше одного отчета.")
        if len(timeline) < days:
            lines.append(f"В папке доступно только {len(timeline)} дн. данных, а не {days}.")
        return "\n".join(lines)

    def render_entity_summary(self, name: str) -> str | None:
        details = self.entity_details(name)
        if details is None:
            return None
        entity_title = "Контрагент" if details["entity_type"] == "client" else "Менеджер"
        lines = [
            f"{entity_title}: {details['name']}",
            f"Долг на {details['report_date']}: {_fmt_money(details['debt'])} RUB",
            f"Просрочка: {_fmt_money(details['overdue_debt'])} RUB",
            "Динамика:",
        ]
        for row in details["timeline"]:
            lines.append(
                f"{row['report_date']}: {_fmt_money(row['debt'])} RUB, просрочка {_fmt_money(row['overdue_debt'])} RUB"
            )
        if details["contracts"]:
            lines.append("Крупнейшие договоры:")
            for record in details["contracts"][:5]:
                lines.append(
                    f"- {record['contract_name']} — {_fmt_money(_to_float(record['debt']))} RUB"
                )
        return "\n".join(lines)


def find_entity_mention(store: AnalyticsStore, text: str) -> str | None:
    text_cf = text.casefold()
    candidates = {
        item["name"]
        for item in store.top_clients(limit=50) + store.top_managers(limit=50)
    }
    matches = [name for name in candidates if name.casefold() in text_cf]
    matches.sort(key=len, reverse=True)
    return matches[0] if matches else None
