"""Billing: persisted payment intents for plan upgrades.

Each checkout creates a :class:`BillingPayment` keyed by the Khpay
``transaction_id``. When the payment is confirmed (via webhook or a client
poll) the intent is marked ``paid`` and the matching user's plan is activated.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from shared.logging import get_logger
from shared.persistence import read_json, write_json

_logger = get_logger(__name__)

PAYMENT_PENDING = "pending"
PAYMENT_PAID = "paid"
PAYMENT_EXPIRED = "expired"


@dataclass(frozen=True)
class BillingPayment:
    """A single plan-upgrade payment intent."""

    transaction_id: str
    user_id: str
    plan: str
    amount: float
    status: str = PAYMENT_PENDING
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class BillingStore:
    """Store of payment intents, optionally persisted to a JSON file."""

    def __init__(self, path: str | Path | None = None) -> None:
        self._items: dict[str, BillingPayment] = {}
        self._path = Path(path) if path else None
        self._load()

    def _load(self) -> None:
        if self._path is None:
            return
        raw = read_json(self._path)
        if not isinstance(raw, list):
            return
        for row in raw:
            if not isinstance(row, dict):
                continue
            payment = _deserialise(row)
            if payment is not None:
                self._items[payment.transaction_id] = payment

    def _persist(self) -> None:
        if self._path is None:
            return
        write_json(self._path, [_serialise(item) for item in self._items.values()])

    def create(self, payment: BillingPayment) -> BillingPayment:
        """Record a new pending payment."""
        self._items[payment.transaction_id] = payment
        self._persist()
        return payment

    def get(self, transaction_id: str) -> BillingPayment | None:
        return self._items.get(transaction_id)

    def mark(self, transaction_id: str, status: str) -> BillingPayment | None:
        """Update a payment's status (``paid``/``expired``) and persist."""
        payment = self._items.get(transaction_id)
        if payment is None or payment.status == status:
            return payment
        updated = BillingPayment(
            transaction_id=payment.transaction_id,
            user_id=payment.user_id,
            plan=payment.plan,
            amount=payment.amount,
            status=status,
            created_at=payment.created_at,
        )
        self._items[transaction_id] = updated
        self._persist()
        return updated

    def list_for_user(self, user_id: str) -> list[BillingPayment]:
        return sorted(
            (item for item in self._items.values() if item.user_id == user_id),
            key=lambda item: item.created_at,
            reverse=True,
        )

    def list_all(self) -> list[BillingPayment]:
        """Return every payment, newest first."""
        return sorted(self._items.values(), key=lambda item: item.created_at, reverse=True)


def _serialise(payment: BillingPayment) -> dict[str, Any]:
    return {
        "transaction_id": payment.transaction_id,
        "user_id": payment.user_id,
        "plan": payment.plan,
        "amount": payment.amount,
        "status": payment.status,
        "created_at": payment.created_at.isoformat(),
    }


def _deserialise(raw: dict[str, Any]) -> BillingPayment | None:
    try:
        created_raw = raw.get("created_at")
        return BillingPayment(
            transaction_id=str(raw["transaction_id"]),
            user_id=str(raw["user_id"]),
            plan=str(raw["plan"]),
            amount=float(raw["amount"]),
            status=str(raw.get("status") or PAYMENT_PENDING),
            created_at=(
                datetime.fromisoformat(str(created_raw)) if created_raw else datetime.now(UTC)
            ),
        )
    except (KeyError, TypeError, ValueError):
        return None
