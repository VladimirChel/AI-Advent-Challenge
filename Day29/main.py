from __future__ import annotations

import argparse
import json

from app.analytics import AnalyticsStore
from app.config import load_config
from app.report_parser import build_snapshots
from app.service import DebtAssistantService
from app.telegram_bot import TelegramBot


def cmd_index() -> None:
    config = load_config()
    paths = build_snapshots(config.documents_dir, config.snapshots_dir)
    print(json.dumps({"snapshots_built": len(paths), "snapshots_dir": str(config.snapshots_dir)}, ensure_ascii=False))


def cmd_ask(question: str, anonymized: bool = False) -> None:
    config = load_config()
    store = AnalyticsStore.from_dir(config.snapshots_dir)
    service = DebtAssistantService(config, store)
    answer = service.answer(question, conversation_id="cli", anonymized=anonymized)
    print(answer.text)


def cmd_bot() -> None:
    config = load_config()
    build_snapshots(config.documents_dir, config.snapshots_dir)
    bot = TelegramBot(config)
    bot.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Debt report assistant MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("index", help="Parse XLSX files into JSON snapshots")

    ask_parser = subparsers.add_parser("ask", help="Ask a question from CLI")
    ask_parser.add_argument("question", help="Question about debt report")
    ask_parser.add_argument("--anonymized", action="store_true", help="Return anonymized output")

    subparsers.add_parser("bot", help="Run Telegram bot")

    args = parser.parse_args()
    if args.command == "index":
        cmd_index()
        return
    if args.command == "ask":
        cmd_ask(args.question, anonymized=args.anonymized)
        return
    if args.command == "bot":
        cmd_bot()
        return


if __name__ == "__main__":
    main()
