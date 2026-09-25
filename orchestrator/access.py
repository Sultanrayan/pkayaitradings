"""Developer API access requests and their approval workflow.

Requests are stored in memory. When the admin approves a request, an API access
token is generated and emailed to the developer.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from typing import Any

from shared.logging import get_logger
from shared.persistence import read_json, write_json

_logger = get_logger(__name__)


class RequestStatus(StrEnum):
    """Lifecycle status of an access request."""

    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"


@dataclass(frozen=True)
class AccessRequest:
    """A developer's application to use the agent API."""

    id: str
    name: str
    email: str
    use_case: str
    website: str
    status: RequestStatus
    created_at: datetime
    reviewed_at: datetime | None = None
    token: str | None = None


def _serialise_request(request: AccessRequest) -> dict[str, Any]:
    """Convert an access request to a JSON-safe dict."""
    return {
        "id": request.id,
        "name": request.name,
        "email": request.email,
        "use_case": request.use_case,
        "website": request.website,
        "status": str(request.status),
        "created_at": request.created_at.isoformat(),
        "reviewed_at": request.reviewed_at.isoformat() if request.reviewed_at else None,
        "token": request.token,
    }


def _deserialise_request(raw: dict[str, Any]) -> AccessRequest | None:
    """Rebuild an access request from persisted JSON, skipping malformed rows."""
    try:
        created_raw = raw.get("created_at")
        reviewed_raw = raw.get("reviewed_at")
        return AccessRequest(
            id=str(raw["id"]),
            name=str(raw["name"]),
            email=str(raw["email"]),
            use_case=str(raw.get("use_case", "")),
            website=str(raw.get("website", "")),
            status=RequestStatus(str(raw.get("status", RequestStatus.PENDING))),
            created_at=datetime.fromisoformat(str(created_raw)) if created_raw else datetime.now(UTC),
            reviewed_at=datetime.fromisoformat(str(reviewed_raw)) if reviewed_raw else None,
            token=raw.get("token"),
        )
    except (KeyError, TypeError, ValueError):
        return None


class AccessRequestStore:
    """Store of access requests, optionally persisted to a JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._items: dict[str, AccessRequest] = {}
        self._path = Path(path) if path else None
        self._load()

    def _load(self) -> None:
        """Load persisted requests from disk when a path is configured."""
        if self._path is None:
            return
        raw = read_json(self._path)
        if not isinstance(raw, list):
            return
        for row in raw:
            if not isinstance(row, dict):
                continue
            request = _deserialise_request(row)
            if request is not None:
                self._items[request.id] = request

    def _persist(self) -> None:
        """Write the requests to disk (no-op when persistence is disabled)."""
        if self._path is None:
            return
        write_json(self._path, [_serialise_request(item) for item in self._items.values()])

    def create(
        self, *, name: str, email: str, use_case: str, website: str
    ) -> AccessRequest:
        """Create a pending request for ``email``."""
        request = AccessRequest(
            id=uuid.uuid4().hex,
            name=name.strip(),
            email=email.strip().lower(),
            use_case=use_case.strip(),
            website=website.strip(),
            status=RequestStatus.PENDING,
            created_at=datetime.now(UTC),
        )
        self._items[request.id] = request
        self._persist()
        _logger.info("access.request_created", email=request.email, request_id=request.id)
        return request

    def list(self) -> list[AccessRequest]:
        """Return all requests, newest first."""
        return sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)

    def get(self, request_id: str) -> AccessRequest | None:
        """Return a request by id."""
        return self._items.get(request_id)

    def approve(self, request_id: str, token: str) -> AccessRequest | None:
        """Mark a request approved and attach its access token."""
        request = self._items.get(request_id)
        if request is None:
            return None
        updated = replace(
            request, status=RequestStatus.APPROVED, reviewed_at=datetime.now(UTC), token=token
        )
        self._items[request_id] = updated
        self._persist()
        return updated

    def reject(self, request_id: str) -> AccessRequest | None:
        """Mark a request rejected."""
        request = self._items.get(request_id)
        if request is None:
            return None
        updated = replace(
            request, status=RequestStatus.REJECTED, reviewed_at=datetime.now(UTC)
        )
        self._items[request_id] = updated
        self._persist()
        return updated
