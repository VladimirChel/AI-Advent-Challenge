from __future__ import annotations

import json
import urllib.request


def main() -> int:
    payload = {
        "question": "Почему не работает авторизация?",
        "ticket_id": "T-1001",
    }
    request = urllib.request.Request(
        "http://127.0.0.1:8010/support/answer",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=120) as response:
        print(response.read().decode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
