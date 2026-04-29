from __future__ import annotations

import argparse
import json

from app.analytics import AnalyticsStore
from app.config import load_config
from app.mcp_tools import handle_get_document_print_form
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


def cmd_print_form(
    document_type: str,
    document_number: str,
    document_date: str | None,
    organization: str | None,
    print_form: str | None,
    output_format: str,
    save_to_file: bool,
) -> None:
    config = load_config()
    result = handle_get_document_print_form(
        {
            "document_type": document_type,
            "document_number": document_number,
            "document_date": document_date,
            "organization": organization,
            "print_form": print_form,
            "output_format": output_format,
            "save_to_file": save_to_file,
        },
        config=config,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


def main() -> None:
    parser = argparse.ArgumentParser(description="Debt report assistant MVP")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("index", help="Parse XLSX files into JSON snapshots")

    ask_parser = subparsers.add_parser("ask", help="Ask a question from CLI")
    ask_parser.add_argument("question", help="Question about debt report")
    ask_parser.add_argument("--anonymized", action="store_true", help="Return anonymized output")

    subparsers.add_parser("bot", help="Run Telegram bot")

    print_form_parser = subparsers.add_parser("print-form", help="Fetch a document print form from 1C HTTP service")
    print_form_parser.add_argument("document_type", help="External document type, for example sales_invoice")
    print_form_parser.add_argument("document_number", help="Document number in 1C")
    print_form_parser.add_argument("--document-date", dest="document_date", help="Document date in YYYY-MM-DD format")
    print_form_parser.add_argument("--organization", help="Organization or another search qualifier")
    print_form_parser.add_argument("--print-form", dest="print_form", help="Print form name, for example invoice")
    print_form_parser.add_argument("--output-format", default="pdf", choices=["pdf", "html", "raw"], help="Expected output format")
    print_form_parser.add_argument("--save-to-file", action="store_true", help="Save the result to output/print_forms")

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
    if args.command == "print-form":
        cmd_print_form(
            args.document_type,
            args.document_number,
            document_date=args.document_date,
            organization=args.organization,
            print_form=args.print_form,
            output_format=args.output_format,
            save_to_file=args.save_to_file,
        )
        return


if __name__ == "__main__":
    main()
