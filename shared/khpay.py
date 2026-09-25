"""Khpay (KHQR) payment client.

Calls the Khpay REST API (``https://khpay.site/api/v1``) over TLS using the
``ak_...`` API key. Generates KHQR payment codes and checks their status, so
the backend can offer plan upgrades without a browser or the khpay CLI.
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import httpx

from shared.logging import get_logger

_logger = get_logger(__name__)


class KhpayError(Exception):
    """Raised when the Khpay API rejects a request or returns an error."""


class KhpayClient:
    """Thin async client for the Khpay REST API."""

    def __init__(self, base_url: str, api_key: str, *, timeout: float = 15.0) -> None:
        if not api_key:
            raise ValueError("Khpay API key is not configured")
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout

    async def create_payment(
        self,
        *,
        amount: float,
        currency: str = "USD",
        note: str | None = None,
        callback_url: str | None = None,
        client_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a KHQR payment and return the payment descriptor.

        The response contains ``transaction_id``, ``qr_image`` (base64 PNG data
        URI) and ``qr_string`` (the scanable KHQR content).
        """
        payload: dict[str, Any] = {"amount": amount, "currency": currency}
        if note:
            payload["note"] = note
        if callback_url:
            payload["callback_url"] = callback_url
        if client_id:
            payload["client_id"] = client_id
        return await self._request("POST", "qr/generate", body=payload)

    async def check_payment(self, transaction_id: str) -> dict[str, Any]:
        """Return the Khpay payment status (``paid`` bool + ``status`` string)."""
        return await self._request("GET", f"qr/check/{quote(transaction_id, safe='')}")

    async def _request(self, method: str, path: str, *, body: dict[str, Any] | None = None) -> dict[str, Any]:
        url = f"{self._base_url}/{path.lstrip('/')}"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                response = await client.request(method, url, headers=headers, json=body)
            data = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise KhpayError(f"Khpay request failed: {exc!r}") from exc

        if response.status_code != 200 or not data.get("success"):
            raise KhpayError(
                f"Khpay error (HTTP {response.status_code}): {data.get('message') or data}"
            )
        result = data.get("data")
        if not isinstance(result, dict):
            raise KhpayError("Khpay returned an unexpected response shape")
        return result


def build_khpay_client(base_url: str, api_key: str) -> KhpayClient | None:
    """Build a client, or ``None`` when no API key is configured."""
    if not api_key:
        _logger.info("khpay.not_configured")
        return None
    return KhpayClient(base_url=base_url, api_key=api_key)