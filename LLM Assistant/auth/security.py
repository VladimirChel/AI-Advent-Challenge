from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone

from config import AUTH_SECRET_KEY, AUTH_TOKEN_TTL_SECONDS


PBKDF2_ITERATIONS = 120_000


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ITERATIONS)
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${_b64url_encode(salt)}${_b64url_encode(digest)}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations, salt_b64, digest_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False

    if algorithm != "pbkdf2_sha256":
        return False

    salt = _b64url_decode(salt_b64)
    expected = _b64url_decode(digest_b64)
    actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, int(iterations))
    return hmac.compare_digest(actual, expected)


def create_access_token(*, user_id: str, email: str) -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=AUTH_TOKEN_TTL_SECONDS)
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {
        "sub": user_id,
        "email": email,
        "iat": int(now.timestamp()),
        "exp": int(expires_at.timestamp()),
    }

    header_b64 = _b64url_encode(json.dumps(header, separators=(",", ":")).encode("utf-8"))
    payload_b64 = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode("utf-8"))
    message = f"{header_b64}.{payload_b64}".encode("ascii")
    signature = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    token = f"{header_b64}.{payload_b64}.{_b64url_encode(signature)}"
    return token, AUTH_TOKEN_TTL_SECONDS


def decode_access_token(token: str) -> dict[str, str | int]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("invalid_token")

    header_b64, payload_b64, signature_b64 = parts
    message = f"{header_b64}.{payload_b64}".encode("ascii")
    expected = hmac.new(AUTH_SECRET_KEY.encode("utf-8"), message, hashlib.sha256).digest()
    actual = _b64url_decode(signature_b64)
    if not hmac.compare_digest(actual, expected):
        raise ValueError("invalid_signature")

    payload = json.loads(_b64url_decode(payload_b64).decode("utf-8"))
    exp = int(payload.get("exp", 0))
    now_ts = int(datetime.now(timezone.utc).timestamp())
    if exp <= now_ts:
        raise ValueError("token_expired")

    return payload
