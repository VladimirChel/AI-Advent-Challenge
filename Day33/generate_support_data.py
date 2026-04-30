from __future__ import annotations

import argparse
import json
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import DEFAULT_DEMO_TICKET_COUNT, DEFAULT_DEMO_USER_COUNT, TICKETS_FILE, USERS_FILE


PLANS = ["free", "starter", "pro", "enterprise"]
LOCALES = ["ru", "en"]
ACCOUNT_STATUSES = ["active", "active", "active", "pending_verification", "locked"]
TICKET_STATUSES = ["open", "open", "pending", "resolved"]
PRIORITIES = ["low", "medium", "high", "urgent"]

AUTH_SCENARIOS = [
    (
        "Не работает авторизация",
        "auth",
        "login",
        "После ввода логина и пароля меня возвращает на форму входа.",
    ),
    (
        "Не приходит код 2FA",
        "auth",
        "two_factor",
        "Код подтверждения не приходит на почту уже 10 минут.",
    ),
    (
        "Аккаунт заблокирован после нескольких попыток входа",
        "auth",
        "security",
        "После нескольких попыток входа система пишет, что доступ временно заблокирован.",
    ),
    (
        "Не удаётся войти после сброса пароля",
        "auth",
        "password_reset",
        "Сбросил пароль, но новый пароль не принимается.",
    ),
]

OTHER_SCENARIOS = [
    (
        "Не проходит оплата",
        "billing",
        "payments",
        "Платёж отклоняется, хотя карта рабочая.",
    ),
    (
        "Не удаётся обновить профиль",
        "profile",
        "profile",
        "После сохранения профиля изменения пропадают.",
    ),
    (
        "Ошибка при экспорте отчёта",
        "reports",
        "exports",
        "Файл не скачивается после нажатия на экспорт.",
    ),
]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate demo JSON data for the Day33 support assistant.")
    parser.add_argument("--count-users", type=int, default=DEFAULT_DEMO_USER_COUNT)
    parser.add_argument("--count-tickets", type=int, default=DEFAULT_DEMO_TICKET_COUNT)
    parser.add_argument("--seed", type=int, default=33)
    parser.add_argument("--users-file", default=str(USERS_FILE))
    parser.add_argument("--tickets-file", default=str(TICKETS_FILE))
    parser.add_argument("--seed-demo", action="store_true", help="Generate a stable demo-heavy dataset.")
    return parser.parse_args()


def build_users(count: int, rng: random.Random) -> list[dict]:
    now = datetime.now(timezone.utc)
    users: list[dict] = []
    for index in range(1, count + 1):
        created_at = now - timedelta(days=rng.randint(5, 800))
        users.append(
            {
                "id": f"U-{1000 + index}",
                "name": f"User {index}",
                "username": f"user{index}",
                "email": f"user{index}@example.com",
                "plan": rng.choice(PLANS),
                "locale": rng.choice(LOCALES),
                "account_status": rng.choice(ACCOUNT_STATUSES),
                "created_at": created_at.isoformat(),
                "tags": rng.sample(
                    ["b2b", "mobile", "web", "vip", "frequent_support", "security_sensitive"],
                    k=rng.randint(1, 3),
                ),
            }
        )
    return users


def build_tickets(count: int, users: list[dict], rng: random.Random, demo_mode: bool) -> list[dict]:
    now = datetime.now(timezone.utc)
    tickets: list[dict] = []
    scenarios = AUTH_SCENARIOS * 3 + OTHER_SCENARIOS if demo_mode else AUTH_SCENARIOS + OTHER_SCENARIOS
    for index in range(1, count + 1):
        subject, category, product_area, text = rng.choice(scenarios)
        user = rng.choice(users)
        created_at = now - timedelta(hours=rng.randint(1, 500))
        messages = [
            {"role": "user", "text": text},
            {
                "role": "support",
                "text": rng.choice(
                    [
                        "Уточните, пожалуйста, точное время ошибки.",
                        "Проверяем детали инцидента.",
                        "Спасибо, смотрим журнал авторизации.",
                    ]
                ),
            },
        ]
        if category == "auth" and product_area == "security":
            user["account_status"] = "locked"
        tickets.append(
            {
                "id": f"T-{1000 + index}",
                "user_id": user["id"],
                "subject": subject,
                "category": category,
                "status": rng.choice(TICKET_STATUSES),
                "priority": rng.choice(PRIORITIES),
                "product_area": product_area,
                "created_at": created_at.isoformat(),
                "messages": messages,
            }
        )
    return tickets


def write_json(path: Path, payload: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    args = parse_args()
    rng = random.Random(args.seed)
    users = build_users(args.count_users, rng)
    tickets = build_tickets(args.count_tickets, users, rng, args.seed_demo)
    write_json(Path(args.users_file), users)
    write_json(Path(args.tickets_file), tickets)
    print(f"Generated {len(users)} users -> {args.users_file}")
    print(f"Generated {len(tickets)} tickets -> {args.tickets_file}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
