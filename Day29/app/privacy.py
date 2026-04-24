from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from typing import Any


SENSITIVE_FIELDS = {
    "name",
    "manager_name",
    "client_name",
    "contract_name",
}


@dataclass(slots=True)
class AnonymizationResult:
    payload: dict[str, Any]
    mapping: dict[str, str]

    def deanonymize_text(self, text: str) -> str:
        result = text
        for token, original in sorted(self.mapping.items(), key=lambda item: len(item[0]), reverse=True):
            result = result.replace(token, original)
        return result

    def anonymize_text(self, text: str) -> str:
        reverse_mapping = {original: token for token, original in self.mapping.items()}
        result = text
        for original, token in sorted(reverse_mapping.items(), key=lambda item: len(item[0]), reverse=True):
            result = result.replace(original, token)
        return result


def _walk(value: Any, mapping: dict[str, str], counters: dict[str, int]) -> Any:
    if isinstance(value, dict):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if key in SENSITIVE_FIELDS and isinstance(item, str) and item.strip():
                kind = key.replace("_name", "").replace("name", "entity").upper()
                counters[kind] = counters.get(kind, 0) + 1
                token = f"{kind}_{counters[kind]:03d}"
                mapping[token] = item
                result[key] = token
            else:
                result[key] = _walk(item, mapping, counters)
        return result
    if isinstance(value, list):
        return [_walk(item, mapping, counters) for item in value]
    return value


def anonymize_payload(payload: dict[str, Any]) -> AnonymizationResult:
    mapping: dict[str, str] = {}
    counters: dict[str, int] = {}
    anonymized = _walk(deepcopy(payload), mapping, counters)
    return AnonymizationResult(payload=anonymized, mapping=mapping)


def build_text_anonymization_result(snapshots: list[dict[str, Any]]) -> AnonymizationResult:
    mapping: dict[str, str] = {}
    counters = {
        "MANAGER": 0,
        "CLIENT": 0,
        "CONTRACT": 0,
        "ENTITY": 0,
    }
    seen: set[tuple[str, str]] = set()

    def register(kind: str, original: str) -> None:
        value = (original or "").strip()
        if not value:
            return
        key = (kind, value)
        if key in seen:
            return
        seen.add(key)
        counters[kind] += 1
        token = f"{kind}_{counters[kind]:03d}"
        mapping[token] = value

    for snapshot in snapshots:
        for record in snapshot.get("records", []):
            register("MANAGER", str(record.get("manager_name", "")))
            register("CLIENT", str(record.get("client_name", "")))
            register("CONTRACT", str(record.get("contract_name", "")))

    return AnonymizationResult(payload={}, mapping=mapping)
