from __future__ import annotations

import re

from fastapi import HTTPException

from auth.repository import create_user, get_user_by_email, get_user_by_id
from auth.schemas import PublicUser, TokenResponse
from auth.security import create_access_token, hash_password, normalize_email, verify_password


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _validate_email(email: str) -> str:
    normalized = normalize_email(email)
    if not EMAIL_RE.match(normalized):
        raise HTTPException(status_code=422, detail="invalid_email")
    return normalized


def register_user(*, email: str, password: str) -> TokenResponse:
    normalized_email = _validate_email(email)
    password_hash = hash_password(password)
    created = create_user(email=normalized_email, password_hash=password_hash)
    if not created:
        raise HTTPException(status_code=409, detail="email_already_registered")

    public_user = PublicUser.model_validate(created)
    token, expires_in = create_access_token(user_id=public_user.id, email=public_user.email)
    return TokenResponse(access_token=token, expires_in=expires_in, user=public_user)


def login_user(*, email: str, password: str) -> TokenResponse:
    normalized_email = _validate_email(email)
    user = get_user_by_email(normalized_email)
    if not user or not verify_password(password, str(user["password_hash"])):
        raise HTTPException(status_code=401, detail="invalid_credentials")

    if not bool(user["is_active"]):
        raise HTTPException(status_code=403, detail="user_inactive")

    public_user = PublicUser(id=str(user["id"]), email=str(user["email"]), is_active=bool(user["is_active"]))
    token, expires_in = create_access_token(user_id=public_user.id, email=public_user.email)
    return TokenResponse(access_token=token, expires_in=expires_in, user=public_user)


def get_public_user(user_id: str) -> PublicUser:
    user = get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="user_not_found")
    if not bool(user["is_active"]):
        raise HTTPException(status_code=403, detail="user_inactive")
    return PublicUser.model_validate(user)
