from __future__ import annotations

import argparse
import json

from pipeline_runner import run_pipeline


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Day19 MCP pipeline.")
    parser.add_argument("--dry-run", action="store_true", help="Collect and summarize without sending to Telegram.")
    parser.add_argument("--send-on-error", action="store_true", help="Send a Telegram error message if a step fails.")
    parser.add_argument("--print-summary", action="store_true", help="Print only the rendered summary text.")
    args = parser.parse_args()

    result = run_pipeline(send_enabled=not args.dry_run, send_on_error=args.send_on_error)

    if args.print_summary and result.get("message_text"):
        print(result["message_text"])
        return

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not result.get("ok"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
