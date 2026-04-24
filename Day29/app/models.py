from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


@dataclass(slots=True)
class DebtRecord:
    report_date: date
    currency: str
    manager_name: str
    client_name: str
    contract_name: str
    debt: float
    overdue_debt: float
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["report_date"] = self.report_date.isoformat()
        return payload


@dataclass(slots=True)
class DailyTotals:
    report_date: date
    currency: str
    total_debt: float
    total_overdue_debt: float
    source_file: str

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["report_date"] = self.report_date.isoformat()
        return payload
