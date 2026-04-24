from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from app.models import DailyTotals, DebtRecord


DATE_RE = re.compile(r"Дата отчета:\s*(\d{2}\.\d{2}\.\d{4})")
CONTRACT_RE = re.compile(r"(договор|контракт|^№)", re.IGNORECASE)
CLIENT_ORG_MARKERS = (
    "ООО",
    "АО",
    "ПАО",
    "ЗАО",
    "ИП",
    "LLC",
    "LTD",
    "INC",
    "CORP",
    "COMPANY",
    "GROUP",
    "ГК",
)
HEADER_VALUES = {
    "Задолженность клиентов",
    "Параметры:",
    "Валюта",
    "Объект расчетов.Менеджер",
    "Клиент",
    "Договор",
}

SUPPORTED_REPORT_EXTENSIONS = (".xlsx", ".xls", ".ods")
EXTENSION_PRIORITY = {
    ".xlsx": 0,
    ".xls": 1,
    ".ods": 2,
}


def _clean_text(value: Any) -> str:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return ""
    return str(value).strip()


def _parse_float(value: Any) -> float:
    if value is None or (isinstance(value, float) and pd.isna(value)):
        return 0.0
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip().replace(" ", "").replace(",", ".")
    if not text:
        return 0.0
    try:
        return float(text)
    except ValueError:
        return 0.0


def _extract_report_date(df: pd.DataFrame) -> datetime.date:
    for row in df.itertuples(index=False):
        for cell in row:
            match = DATE_RE.search(_clean_text(cell))
            if match:
                return datetime.strptime(match.group(1), "%d.%m.%Y").date()
    raise ValueError("Report date not found in XLSX")


def _looks_like_manager(text: str) -> bool:
    if not text or any(char.isdigit() for char in text):
        return False
    if CONTRACT_RE.search(text):
        return False
    if any(marker in text.upper() for marker in CLIENT_ORG_MARKERS):
        return False
    words = [part for part in re.split(r"\s+", text) if part]
    return 2 <= len(words) <= 4 and all(len(word) > 1 for word in words)


def _classify_row(label: str, current_manager: str, current_client: str) -> str:
    upper = label.upper()
    if label in HEADER_VALUES:
        return "header"
    if upper == "RUB":
        return "currency"
    if CONTRACT_RE.search(label):
        return "contract"
    if not current_manager or _looks_like_manager(label):
        return "manager"
    if current_client and _looks_like_manager(label):
        return "manager"
    return "client"


def parse_report(path: Path) -> dict[str, Any]:
    df = pd.read_excel(path, header=None)
    report_date = _extract_report_date(df)

    currency = ""
    total_debt = 0.0
    total_overdue = 0.0
    current_manager = ""
    current_client = ""
    records: list[DebtRecord] = []

    for _, row in df.iterrows():
        label = _clean_text(row.iloc[0] if len(row) > 0 else "")
        debt = _parse_float(row.iloc[5] if len(row) > 5 else None)
        overdue_debt = _parse_float(row.iloc[6] if len(row) > 6 else None)
        if not label:
            continue

        row_type = _classify_row(label, current_manager=current_manager, current_client=current_client)
        if row_type == "header":
            continue
        if row_type == "currency":
            currency = label
            total_debt = debt
            total_overdue = overdue_debt
            continue
        if row_type == "manager":
            current_manager = label
            current_client = ""
            continue
        if row_type == "client":
            current_client = label
            continue
        if row_type == "contract" and current_manager and current_client:
            records.append(
                DebtRecord(
                    report_date=report_date,
                    currency=currency or "RUB",
                    manager_name=current_manager,
                    client_name=current_client,
                    contract_name=label,
                    debt=debt,
                    overdue_debt=overdue_debt,
                    source_file=path.name,
                )
            )

    if not records:
        raise ValueError(f"No debt records parsed from {path}")

    totals = DailyTotals(
        report_date=report_date,
        currency=currency or "RUB",
        total_debt=total_debt or sum(item.debt for item in records),
        total_overdue_debt=total_overdue or sum(item.overdue_debt for item in records),
        source_file=path.name,
    )
    return {
        "report_date": report_date.isoformat(),
        "source_file": path.name,
        "currency": totals.currency,
        "totals": totals.to_dict(),
        "records": [item.to_dict() for item in records],
    }


def parse_reports(source_dir: Path) -> list[dict[str, Any]]:
    snapshots: list[dict[str, Any]] = []
    selected_by_stem: dict[str, Path] = {}
    for path in sorted(source_dir.iterdir()):
        if not path.is_file() or path.suffix.lower() not in SUPPORTED_REPORT_EXTENSIONS:
            continue
        existing = selected_by_stem.get(path.stem)
        if existing is None:
            selected_by_stem[path.stem] = path
            continue
        current_priority = EXTENSION_PRIORITY.get(path.suffix.lower(), 99)
        existing_priority = EXTENSION_PRIORITY.get(existing.suffix.lower(), 99)
        if current_priority < existing_priority:
            selected_by_stem[path.stem] = path
    for path in sorted(selected_by_stem.values()):
        snapshots.append(parse_report(path))
    return snapshots


def save_snapshot(snapshot: dict[str, Any], destination: Path) -> Path:
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination


def build_snapshots(source_dir: Path, snapshots_dir: Path) -> list[Path]:
    results: list[Path] = []
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    for path in snapshots_dir.glob("*.json"):
        path.unlink()
    for snapshot in parse_reports(source_dir):
        report_date = snapshot["report_date"]
        stem = Path(snapshot["source_file"]).stem
        destination = snapshots_dir / f"{report_date}__{stem}.json"
        results.append(save_snapshot(snapshot, destination))
    return results
