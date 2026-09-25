"""Authentication: password hashing, signed tokens and an in-memory user store.

This is deliberately dependency-free (stdlib only) so the app can run without
PostgreSQL. The :class:`UserStore` is process-local; swap it for a repository
backed by the database layer when persistence is required.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.persistence import read_json, write_json

_PBKDF2_ITERATIONS = 120_000
_ALGORITHM = "pbkdf2_sha256"
DEFAULT_BILLING_PERIOD_DAYS = 30


def _utcnow() -> datetime:
    return datetime.now(UTC)


class AuthError(Exception):
    """Raised for invalid credentials, tokens or duplicate registrations."""


@dataclass(frozen=True)
class User:
    """A registered account (never exposes the password hash over the API)."""

    id: str
    name: str
    email: str
    password_hash: str | None
    created_at: datetime
    provider: str = "password"
    subject: str | None = None
    verified: bool = True
    plan: str = "free"
    plan_expires_at: datetime | None = None
    analysis_used: int = 0
    analysis_period_start: datetime = field(default_factory=_utcnow)


def hash_password(password: str, *, salt: bytes | None = None) -> str:
    """Hash a password with PBKDF2-HMAC-SHA256."""
    if len(password) < 8:
        raise AuthError("Password must be at least 8 characters")
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ITERATIONS)
    return (
        f"{_ALGORITHM}${_PBKDF2_ITERATIONS}"
        f"${base64.b64encode(salt).decode()}"
        f"${base64.b64encode(digest).decode()}"
    )


def verify_password(password: str, encoded: str) -> bool:
    """Verify a password against a stored hash (constant-time comparison)."""
    try:
        algorithm, iterations, salt_b64, digest_b64 = encoded.split("$")
    except ValueError:
        return False
    if algorithm != _ALGORITHM:
        return False
    salt = base64.b64decode(salt_b64)
    expected = base64.b64decode(digest_b64)
    candidate = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
    return hmac.compare_digest(candidate, expected)



def _b64encode(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def sign_payload(payload: dict[str, object], secret: str) -> str:
    """Sign an arbitrary JSON payload with HMAC-SHA256."""
    body = _b64encode(json.dumps(payload, separators=(",", ":")).encode())
    signature = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64encode(signature)}"


def verify_payload(token: str, secret: str) -> dict[str, object]:
    """Verify and decode a payload produced by :func:`sign_payload`.

    Raises:
        AuthError: If the token is malformed, tampered with or expired.
    """
    try:
        body, signature = token.split(".")
    except ValueError as exc:
        raise AuthError("Malformed token") from exc
    expected = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    if not hmac.compare_digest(expected, _b64decode(signature)):
        raise AuthError("Invalid token signature")
    try:
        payload: dict[str, object] = json.loads(_b64decode(body))
    except (ValueError, json.JSONDecodeError) as exc:
        raise AuthError("Malformed token payload") from exc
    expires_at = payload.get("exp", 0)
    if not isinstance(expires_at, (int, float)) or float(expires_at) < time.time():
        raise AuthError("Token expired")
    return payload


def create_token(user: User, secret: str, *, ttl_seconds: int) -> str:
    """Create a signed, expiring session token for ``user``."""
    return sign_payload(
        {
            "sub": user.id,
            "email": user.email,
            "name": user.name,
            "verified": True,
            "scope": "user",
            "exp": int(time.time()) + ttl_seconds,
        },
        secret,
    )


def create_api_token(*, email: str, name: str, secret: str, ttl_seconds: int) -> str:
    """Create a signed API access token for an approved developer."""
    return sign_payload(
        {
            "email": email,
            "name": name,
            "scope": "developer",
            "exp": int(time.time()) + ttl_seconds,
        },
        secret,
    )


def decode_token(token: str, secret: str) -> dict[str, object]:
    """Validate a bearer token and return its payload."""
    return verify_payload(token, secret)


def _serialise_user(user: User) -> dict[str, Any]:
    """Convert a user to a JSON-safe dict (hashes retained so auth still works)."""
    return {
        "id": user.id,
        "name": user.name,
        "email": user.email,
        "password_hash": user.password_hash,
        "created_at": user.created_at.isoformat(),
        "provider": user.provider,
        "subject": user.subject,
        "verified": True,
        "plan": user.plan,
        "plan_expires_at": user.plan_expires_at.isoformat() if user.plan_expires_at else None,
        "analysis_used": user.analysis_used,
        "analysis_period_start": user.analysis_period_start.isoformat(),
    }


def _deserialise_user(raw: dict[str, Any]) -> User | None:
    """Rebuild a user from persisted JSON, skipping malformed rows."""
    try:
        created_raw = raw.get("created_at")
        period_raw = raw.get("analysis_period_start")
        expires_raw = raw.get("plan_expires_at")
        return User(
            id=str(raw["id"]),
            name=str(raw["name"]),
            email=str(raw["email"]),
            password_hash=raw.get("password_hash"),
            created_at=datetime.fromisoformat(str(created_raw)) if created_raw else datetime.now(UTC),
            provider=str(raw.get("provider") or "password"),
            subject=raw.get("subject"),
            verified=True,
            plan=str(raw.get("plan") or "free"),
            plan_expires_at=(
                datetime.fromisoformat(str(expires_raw)) if expires_raw else None
            ),
            analysis_used=int(raw.get("analysis_used") or 0),
            analysis_period_start=(
                datetime.fromisoformat(str(period_raw))
                if period_raw
                else datetime.now(UTC)
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None


class UserStore:
    """User registry.

    Backed by an in-memory dict. When ``path`` is given the registry is loaded
    from that JSON file on construction and atomically persisted after every
    mutation, so accounts survive restarts and redeploys.
    """

    def __init__(self, path: str | Path | None = None) -> None:
        self._users: dict[str, User] = {}
        self._by_email: dict[str, str] = {}
        self._path = Path(path) if path else None
        self._load()

    def _load(self) -> None:
        """Load persisted users from disk when a path is configured."""
        if self._path is None:
            return
        raw = read_json(self._path)
        if not isinstance(raw, list):
            return
        for row in raw:
            if not isinstance(row, dict):
                continue
            user = _deserialise_user(row)
            if user is None:
                continue
            self._users[user.id] = user
            self._by_email[user.email] = user.id

    def _persist(self) -> None:
        """Write the registry to disk (no-op when persistence is disabled)."""
        if self._path is None:
            return
        write_json(self._path, [_serialise_user(user) for user in self._users.values()])

    @property
    def size(self) -> int:
        """Number of registered users."""
        return len(self._users)

    def register(self, name: str, email: str, password: str) -> User:
        """Create a new user, rejecting duplicate emails."""
        normalised = email.strip().lower()
        if normalised in self._by_email:
            raise AuthError("An account with this email already exists")
        user = User(
            id=uuid.uuid4().hex,
            name=name.strip() or normalised.split("@")[0],
            email=normalised,
            password_hash=hash_password(password),
            created_at=datetime.now(UTC),
        )
        self._users[user.id] = user
        self._by_email[normalised] = user.id
        self._persist()
        return user

    def authenticate(self, email: str, password: str) -> User | None:
        """Return the user when the credentials are valid, else ``None``.

        Accounts created via an OAuth provider have no password and cannot sign
        in this way.
        """
        user = self.get_by_email(email)
        if user is None or user.password_hash is None:
            return None
        return user if verify_password(password, user.password_hash) else None

    def upsert_oauth(self, *, name: str, email: str, provider: str, subject: str) -> User:
        """Create or return the account for an OAuth identity."""
        normalised = email.strip().lower()
        existing = self.get_by_email(normalised)
        if existing is not None:
            return existing
        user = User(
            id=uuid.uuid4().hex,
            name=name.strip() or normalised.split("@")[0],
            email=normalised,
            password_hash=None,
            created_at=datetime.now(UTC),
            provider=provider,
            subject=subject,
        )
        self._users[user.id] = user
        self._by_email[normalised] = user.id
        self._persist()
        return user

    def get(self, user_id: str) -> User | None:
        """Return a user by id."""
        return self._users.get(user_id)

    def all(self) -> list[User]:
        """Return every registered user, newest first."""
        return sorted(self._users.values(), key=lambda user: user.created_at, reverse=True)

    def get_by_email(self, email: str) -> User | None:
        """Return a user by email (case-insensitive)."""
        user_id = self._by_email.get(email.strip().lower())
        return self._users.get(user_id) if user_id else None

    def update(self, user: User) -> User:
        """Replace and persist ``user`` (used for plan/usage mutations)."""
        self._users[user.id] = user
        self._by_email[user.email] = user.id
        self._persist()
        return user
