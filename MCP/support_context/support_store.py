from __future__ import annotations

import json
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DAY33_DATA_DIR = ROOT_DIR / "Day33" / "data"
USERS_FILE = DAY33_DATA_DIR / "users.json"
TICKETS_FILE = DAY33_DATA_DIR / "tickets.json"


def _read_json(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return list(json.loads(path.read_text(encoding="utf-8")))


def load_users() -> list[dict[str, Any]]:
    return _read_json(USERS_FILE)


def load_tickets() -> list[dict[str, Any]]:
    return _read_json(TICKETS_FILE)


def get_user(user_id: str) -> dict[str, Any]:
    for user in load_users():
        if user.get("id") == user_id:
            return user
    raise ValueError(f"User not found: {user_id}")


def _normalize(value: str) -> str:
    return " ".join((value or "").strip().lower().split())


def _user_username(user: dict[str, Any]) -> str:
    explicit_username = str(user.get("username", "") or "").strip()
    if explicit_username:
        return explicit_username
    email = str(user.get("email", "") or "").strip()
    if "@" in email:
        return email.split("@", 1)[0].strip()
    return ""


def resolve_user_identity(query: str) -> dict[str, Any]:
    normalized_query = _normalize(query)
    if not normalized_query:
        return {"matched": False, "user": None, "candidates": []}

    users = load_users()
    exact_matches = [
        user
        for user in users
        if normalized_query in {
            _normalize(str(user.get("name", ""))),
            _normalize(_user_username(user)),
        }
    ]
    if len(exact_matches) == 1:
        return {"matched": True, "user": exact_matches[0], "candidates": []}

    partial_matches = [
        user
        for user in users
        if normalized_query in _normalize(str(user.get("name", "")))
        or normalized_query in _normalize(_user_username(user))
    ]
    if len(partial_matches) == 1:
        return {"matched": True, "user": partial_matches[0], "candidates": []}

    candidates = exact_matches or partial_matches
    return {
        "matched": False,
        "user": None,
        "candidates": [
            {
                "id": user.get("id"),
                "name": user.get("name"),
                "username": _user_username(user),
            }
            for user in candidates[:5]
        ],
    }


def get_ticket(ticket_id: str) -> dict[str, Any]:
    for ticket in load_tickets():
        if ticket.get("id") == ticket_id:
            return ticket
    raise ValueError(f"Ticket not found: {ticket_id}")


def find_user_tickets(user_id: str, limit: int = 5) -> dict[str, Any]:
    tickets = [ticket for ticket in load_tickets() if ticket.get("user_id") == user_id]
    tickets.sort(key=lambda item: item.get("created_at", ""), reverse=True)
    return {"tickets": tickets[:limit]}
