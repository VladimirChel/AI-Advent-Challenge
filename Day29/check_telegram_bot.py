from __future__ import annotations

import argparse
import json
import sys

from app.config import load_config
from app.telegram_bot import TelegramBot


def main() -> int:
    parser = argparse.ArgumentParser(description="Smoke test Telegram bot transport")
    parser.add_argument("--updates", action="store_true", help="Also test getUpdates")
    args = parser.parse_args()

    config = load_config()
    if not config.telegram_bot_token:
        print(json.dumps({"ok": False, "error": "missing_telegram_bot_token"}, ensure_ascii=False))
        return 1

    bot = TelegramBot(config)

    try:
        get_me_response = bot.session.get(f"{bot.base_url}/getMe", timeout=30)
        get_me_response.raise_for_status()
        get_me_payload = get_me_response.json()
    except Exception as exc:
        print(
            json.dumps(
                {
                    "ok": False,
                    "step": "getMe",
                    "proxy_configured": bool(config.telegram_proxy_url),
                    "proxy_scheme": config.telegram_proxy_url.split("://", 1)[0] if config.telegram_proxy_url else None,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                },
                ensure_ascii=False,
            )
        )
        return 1

    result = {
        "ok": bool(get_me_payload.get("ok")),
        "step": "getMe",
        "proxy_configured": bool(config.telegram_proxy_url),
        "proxy_scheme": config.telegram_proxy_url.split("://", 1)[0] if config.telegram_proxy_url else None,
        "bot_username": get_me_payload.get("result", {}).get("username"),
        "bot_id": get_me_payload.get("result", {}).get("id"),
    }

    if not result["ok"]:
        print(json.dumps(result, ensure_ascii=False))
        return 1

    if args.updates:
        try:
            updates = bot.get_updates()
        except Exception as exc:
            print(
                json.dumps(
                    {
                        **result,
                        "step": "getUpdates",
                        "updates_ok": False,
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                )
            )
            return 1
        result["step"] = "getUpdates"
        result["updates_ok"] = True
        result["updates_count"] = len(updates)

    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
