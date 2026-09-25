"""Transactional email delivery.

Prefers Brevo's transactional email HTTP API (``api.brevo.com/v3``) using an
``xkeysib-...`` API key. Falls back to Brevo's SMTP relay when no API key is
configured, so local development keeps working. Includes the HTML template for
the API access token.
"""

from __future__ import annotations

import asyncio
import smtplib
from email.message import EmailMessage
from email.utils import formataddr

import httpx

from shared.config import Settings
from shared.logging import get_logger

_logger = get_logger(__name__)


class EmailError(Exception):
    """Raised when an email cannot be sent."""


class EmailSender:
    """Email sender backed by the Brevo API (with SMTP fallback)."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._api_key = settings.brevo_api_key
        self._api_url = settings.brevo_api_url
        self._host = settings.smtp_host
        self._port = settings.smtp_port
        self._login = settings.smtp_login
        self._password = settings.smtp_password
        self._sender = settings.email_sender
        self._sender_name = settings.email_sender_name

    @property
    def configured(self) -> bool:
        """Whether a Brevo API key or SMTP credentials are available."""
        has_api = bool(self._api_key)
        has_smtp = bool(self._login and self._password)
        return (has_api or has_smtp) and bool(self._sender)

    def send(self, *, to: str, subject: str, html: str, text: str | None = None) -> None:
        """Send an HTML email synchronously (call via ``asyncio.to_thread``)."""
        if not self.configured:
            raise EmailError("Email is not configured")
        if self._api_key:
            self._send_brevo_api(to=to, subject=subject, html=html, text=text)
        else:
            self._send_smtp(to=to, subject=subject, html=html, text=text)

    def _send_brevo_api(self, *, to: str, subject: str, html: str, text: str | None) -> None:
        """Send through Brevo's transactional email HTTP API."""
        payload = {
            "sender": {"name": self._sender_name, "email": self._sender},
            "to": [{"email": to}],
            "subject": subject,
            "htmlContent": html,
        }
        if text:
            payload["textContent"] = text
        headers = {
            "accept": "application/json",
            "api-key": self._api_key,
            "content-type": "application/json",
        }
        try:
            response = httpx.post(self._api_url, json=payload, headers=headers, timeout=20.0)
        except httpx.HTTPError as exc:
            raise EmailError(f"Brevo API request failed: {exc!r}") from exc
        if response.status_code >= 400:
            raise EmailError(
                f"Brevo API send failed (HTTP {response.status_code}): {response.text[:200]}"
            )

    def _send_smtp(self, *, to: str, subject: str, html: str, text: str | None) -> None:
        """Fallback: send through Brevo's SMTP relay."""
        message = EmailMessage()
        message["From"] = formataddr((self._sender_name, self._sender))
        message["To"] = to
        message["Subject"] = subject
        message.set_content(text or "This email requires an HTML capable client.")
        message.add_alternative(html, subtype="html")
        try:
            with smtplib.SMTP(self._host, self._port, timeout=20) as server:
                server.ehlo()
                server.starttls()
                server.ehlo()
                server.login(self._login, self._password)
                server.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            raise EmailError(f"SMTP send failed: {exc!r}") from exc

    async def send_async(
        self, *, to: str, subject: str, html: str, text: str | None = None
    ) -> None:
        """Send an email without blocking the event loop."""
        await asyncio.to_thread(self.send, to=to, subject=subject, html=html, text=text)


def render_access_token_email(
    *, name: str, token: str, api_base_url: str, logo_url: str
) -> str:
    """Render the API access token email sent after an approval."""
    return f"""\
<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#000000;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;">
    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#000000;padding:32px 0;">
      <tr>
        <td align="center">
          <table role="presentation" width="520" cellpadding="0" cellspacing="0" style="width:520px;max-width:92%;background:#0a0a0a;border:1px solid #1f1f1f;border-radius:16px;overflow:hidden;">
            <tr>
              <td style="padding:28px 32px 0;text-align:center;">
                <img src="{logo_url}" alt="Pkay TDAI" width="56" height="56" style="border-radius:12px;display:inline-block;" />
                <div style="margin-top:12px;color:#fafafa;font-size:16px;font-weight:600;">Pkay TDAI</div>
              </td>
            </tr>
            <tr>
              <td style="padding:24px 32px 8px;text-align:center;">
                <h1 style="margin:0;color:#fafafa;font-size:20px;font-weight:600;">Your API access is approved</h1>
                <p style="margin:12px 0 0;color:#8b8b8b;font-size:14px;line-height:1.6;">
                  Hi {name}, your request to use the Pkay TDAI developer API has been approved.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:16px 32px;text-align:center;">
                <div style="padding:16px;background:#111111;border:1px solid #262626;border-radius:12px;word-break:break-all;">
                  <code style="color:#22c55e;font-size:12px;font-family:ui-monospace,Menlo,Consolas,monospace;">{token}</code>
                </div>
                <p style="margin:16px 0 0;color:#8b8b8b;font-size:12px;">
                  Send it as <code>Authorization: Bearer &lt;token&gt;</code> to every request.
                </p>
              </td>
            </tr>
            <tr>
              <td style="padding:8px 32px 28px;text-align:center;">
                <p style="margin:0;color:#8b8b8b;font-size:12px;">
                  Base URL: <a href="{api_base_url}" style="color:#eab308;text-decoration:none;">{api_base_url}</a><br />
                  See the API reference at <a href="{api_base_url}/api-reference" style="color:#eab308;text-decoration:none;">{api_base_url}/api-reference</a>.
                </p>
              </td>
            </tr>
          </table>
          <p style="color:#3f3f46;font-size:11px;margin:20px 0 0;">Pkay TDAI &middot; Market intelligence</p>
        </td>
      </tr>
    </table>
  </body>
</html>"""
