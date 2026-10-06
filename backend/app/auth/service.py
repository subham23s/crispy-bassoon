"""Password hashing and HS256 JWT authentication without a mandatory dependency."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from datetime import datetime, timezone
from typing import Any

from app.database.interfaces import Repository


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _unb64(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 210_000)
    return f"pbkdf2_sha256$210000${_b64(salt)}${_b64(digest)}"


def _refresh_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256":
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), _unb64(salt), int(rounds))
        return hmac.compare_digest(_b64(actual), expected)
    except (ValueError, TypeError):
        return False


def issue_token(user: dict[str, Any], secret: str, minutes: int = 60) -> str:
    now = int(time.time())
    header = {"alg": "HS256", "typ": "JWT"}
    payload = {"sub": user["id"], "email": user["email"], "role": user["role"], "iat": now, "exp": now + minutes * 60}
    encoded_header = _b64(json.dumps(header, separators=(",", ":")).encode())
    encoded_payload = _b64(json.dumps(payload, separators=(",", ":")).encode())
    unsigned = f"{encoded_header}.{encoded_payload}".encode()
    signature = _b64(hmac.new(secret.encode(), unsigned, hashlib.sha256).digest())
    return f"{encoded_header}.{encoded_payload}.{signature}"


def decode_token(token: str, secret: str) -> dict[str, Any]:
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Malformed access token")
    unsigned = f"{parts[0]}.{parts[1]}".encode()
    expected = _b64(hmac.new(secret.encode(), unsigned, hashlib.sha256).digest())
    if not hmac.compare_digest(expected, parts[2]):
        raise ValueError("Invalid access token signature")
    payload = json.loads(_unb64(parts[1]))
    if int(payload.get("exp", 0)) <= int(time.time()):
        raise ValueError("Access token expired")
    return payload


class AuthService:
    def __init__(self, repository: Repository, secret: str, access_token_minutes: int = 60) -> None:
        self.repository = repository
        self.secret = secret
        self.access_token_minutes = access_token_minutes

    def _session(self, user: dict[str, Any]) -> dict[str, Any]:
        refresh_token = _b64(secrets.token_bytes(48))
        now = int(time.time())
        refresh_expires_at = now + 30 * 24 * 60 * 60
        self.repository.save_refresh_token(
            _refresh_hash(refresh_token),
            user["id"],
            refresh_expires_at,
            datetime.now(timezone.utc).isoformat(),
        )
        return {
            "user": user,
            "access_token": issue_token(user, self.secret, self.access_token_minutes),
            "refresh_token": refresh_token,
            "token_type": "bearer",
            "expires_in": self.access_token_minutes * 60,
        }

    def register(self, email: str, password: str, role: str = "USER") -> dict[str, Any]:
        if "@" not in email or len(email.strip()) < 5:
            raise ValueError("A valid email address is required")
        if len(password) < 10:
            raise ValueError("Password must contain at least 10 characters")
        if self.repository.get_user_by_email(email):
            raise ValueError("An account with that email already exists")
        # Public registration cannot self-assign elevated roles. Admin/researcher
        # provisioning belongs in an authenticated administrative workflow.
        safe_role = "USER"
        user = self.repository.create_user(str(uuid.uuid4()), email, hash_password(password), safe_role, datetime.now(timezone.utc).isoformat())
        return self._session(user)

    def login(self, email: str, password: str) -> dict[str, Any]:
        row = self.repository.get_user_by_email(email)
        if row is None or not verify_password(password, row["password_hash"]):
            raise ValueError("Invalid email or password")
        user = {"id": row["id"], "email": row["email"], "role": row["role"], "created_at": row["created_at"]}
        return self._session(user)

    def refresh(self, refresh_token: str) -> dict[str, Any]:
        if not refresh_token:
            raise ValueError("refresh_token is required")
        row = self.repository.get_refresh_token(_refresh_hash(refresh_token))
        if row is None or int(row["expires_at"]) <= int(time.time()):
            raise ValueError("Invalid or expired refresh token")
        user_row = self.repository.get_user(row["user_id"])
        if user_row is None:
            raise ValueError("User account is unavailable")
        if not self.repository.revoke_refresh_token(_refresh_hash(refresh_token), int(time.time())):
            raise ValueError("Invalid or already rotated refresh token")
        user = dict(user_row)
        return self._session(user)

    def logout(self, refresh_token: str) -> None:
        if refresh_token:
            self.repository.revoke_refresh_token(_refresh_hash(refresh_token), int(time.time()))

    def authenticate(self, token: str) -> dict[str, Any]:
        return decode_token(token, self.secret)
