from __future__ import annotations

import json
import sys
from typing import Any


def _binary_stream(stream: Any) -> Any:
    return getattr(stream, "buffer", stream)


def read_message(stdin: Any) -> dict[str, Any] | None:
    content_length: int | None = None
    binary_stdin = _binary_stream(stdin)

    while True:
        line = binary_stdin.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        header = line.decode("utf-8").strip()
        if header.lower().startswith("content-length:"):
            content_length = int(header.split(":", 1)[1].strip())

    if content_length is None:
        raise ValueError("Missing Content-Length header")

    body = binary_stdin.read(content_length)
    if not body:
        return None
    return json.loads(body.decode("utf-8"))


def write_message(stdout: Any, message: dict[str, Any]) -> None:
    encoded = json.dumps(message, ensure_ascii=False).encode("utf-8")
    binary_stdout = _binary_stream(stdout)
    binary_stdout.write(f"Content-Length: {len(encoded)}\r\n\r\n".encode("ascii"))
    binary_stdout.write(encoded)
    binary_stdout.flush()


def write_log(message: str) -> None:
    print(message, file=sys.stderr, flush=True)
