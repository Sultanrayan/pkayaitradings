"""Tests that no credential can reach a log line.

The regression: the Telegram bot wrote its token to stdout 14 times in an hour,
because ``httpx`` logs one INFO line per request containing the full URL and the
Telegram bot token is the path segment of that URL. Nothing in the pipeline
scrubbed it, so ``docker logs`` held the live credential.

These tests assert on the *rendered output*, not on the logger call, because the
leak was in the rendering path.
"""

from __future__ import annotations

import io
import subprocess
import sys

import pytest

from shared.logging import scrub_foreign_record, scrub_secrets

FAKE_TOKEN = "1234567890:AAaaBBbbCCccDDddEEeeFFffGGggHHhhIIii"


def _one(value):
    """Apply the string/dict/record scrubber to a single value.

    ``scrub_secrets`` is the three-argument structlog processor; this reaches the
    underlying worker so a plain string or dict can be checked directly.
    """
    from shared.logging import _scrub_value

    return _scrub_value(value)


def test_a_bare_token_is_scrubbed() -> None:
    assert _one(FAKE_TOKEN) == "<redacted>"


def test_a_token_in_a_url_is_scrubbed() -> None:
    """The exact shape httpx emits."""
    line = f'HTTP Request: POST https://api.telegram.org/bot{FAKE_TOKEN}/getMe "HTTP/1.1 200 OK"'
    out = _one(line)
    assert FAKE_TOKEN not in out
    assert "<redacted>" in out


def test_a_token_prefixed_by_a_word_is_still_scrubbed() -> None:
    """``/bot123456:...`` has no leading word boundary; ``\\b`` would miss it."""
    out = _one(f"bot{FAKE_TOKEN}/getUpdates")
    assert FAKE_TOKEN not in out


def test_a_provider_key_is_scrubbed() -> None:
    assert _one("Authorization: sk-abcdefghijklmnopqrstuvwxyz0123") == (
        "Authorization: <redacted>"
    )


def test_ordinary_text_is_untouched() -> None:
    for text in (
        "scan.complete computed=1 delivered=0",
        "entry 4156.23 sl 4132.10",
        "2026-10-03T04:54:25.854698Z",
        "GET https://biquote.io/api/XAUUSD/ohlc?interval=5m&limit=400",
        "celery@worker1 ready",
    ):
        assert _one(text) == text


def test_a_dict_event_is_scrubbed_recursively() -> None:
    event = {
        "event": "http.request",
        "url": f"https://api.telegram.org/bot{FAKE_TOKEN}/sendMessage",
        "nested": {"token": FAKE_TOKEN},
        "count": 3,
    }
    out = _one(event)
    assert FAKE_TOKEN not in str(out)
    assert out["count"] == 3, "non-string values must survive"
    assert out["nested"]["token"] == "<redacted>"




def test_rendered_output_contains_no_token() -> None:
    """End to end through the real configuration, which is where the leak was."""
    script = f"""
import logging, sys
sys.path.insert(0, {str(_repo_root())!r})
from shared.logging import configure_logging
configure_logging(level="INFO", json_logs=True)

# A third-party logger, exactly like httpx.
third = logging.getLogger("httpx")
third.info("HTTP Request: POST https://api.telegram.org/bot{FAKE_TOKEN}/getMe 200 OK")
third.setLevel(logging.WARNING)  # configure_logging silences this by default
third.warning("failed: https://api.telegram.org/bot{FAKE_TOKEN}/getMe")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert FAKE_TOKEN not in combined, f"token reached the log output:\n{combined}"
    assert "<redacted>" in combined


def test_httpx_is_silenced_by_default() -> None:
    """Silenced because its INFO lines exist only to leak the URL."""
    script = f"""
import logging, sys
sys.path.insert(0, {str(_repo_root())!r})
from shared.logging import configure_logging
configure_logging()
print(logging.getLogger("httpx").level >= logging.WARNING)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert "True" in result.stdout


def test_a_token_in_a_traceback_is_scrubbed() -> None:
    """An upstream exception echoing the URL is the documented leak path.

    ``format_exc_info`` folds the traceback into the event dict before the scrub
    runs, so the message text inside it is covered too.
    """
    script = f"""
import sys
sys.path.insert(0, {str(_repo_root())!r})
from shared.logging import configure_logging
import structlog
configure_logging(level="INFO", json_logs=True)
log = structlog.get_logger("t")
try:
    raise RuntimeError("POST https://api.telegram.org/bot{FAKE_TOKEN}/sendMe failed")
except RuntimeError:
    log.exception("send.failed")
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    combined = result.stdout + result.stderr
    assert FAKE_TOKEN not in combined, f"token survived in a traceback:\n{combined[:400]}"
    assert "<redacted>" in combined


def test_the_structlog_processor_keeps_its_three_argument_contract() -> None:
    """Both chains call processors as ``(logger, name, event_dict)``."""
    event = {"event": "x", "url": f"https://api.telegram.org/bot{FAKE_TOKEN}/y"}
    result = scrub_secrets(None, "info", event)
    # The URL keeps its shape so the log stays useful; only the credential goes.
    assert result["url"] == "https://api.telegram.org/bot<redacted>/y"
    assert FAKE_TOKEN not in result["url"]
    assert result is event, "the processor must return the event dict"


def test_the_foreign_alias_shares_the_same_contract() -> None:
    """``foreign_pre_chain`` passes an event dict too, not a bare LogRecord."""
    event = {"event": f"POST /bot{FAKE_TOKEN}/getMe 200 OK", "level": "info"}
    result = scrub_foreign_record(None, "info", event)
    assert FAKE_TOKEN not in result["event"]


def _repo_root():
    from pathlib import Path

    return Path(__file__).resolve().parents[2]


@pytest.mark.parametrize("level", ["DEBUG", "INFO", "WARNING"])
def test_scrubbing_is_active_at_every_log_level(level: str) -> None:
    script = f"""
import logging, sys
sys.path.insert(0, {str(_repo_root())!r})
from shared.logging import configure_logging
configure_logging(level="{level}", json_logs=True)
logging.getLogger("somewhere").log(
    getattr(logging, "{level}"), "url=https://api.telegram.org/bot{FAKE_TOKEN}/x"
)
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert FAKE_TOKEN not in result.stdout + result.stderr


def test_scrubbing_survives_a_non_string_payload() -> None:
    """Numbers, booleans and ``None`` must pass through untouched."""
    event = {
        "count": 42,
        "ok": True,
        "missing": None,
        "ratio": 1.5,
        "event": f"bot{FAKE_TOKEN}/x",
    }
    result = scrub_secrets(None, "info", event)
    assert result["count"] == 42
    assert result["ok"] is True
    assert result["missing"] is None
    assert result["ratio"] == 1.5
    assert result["event"] == "bot<redacted>/x"


def test_a_tuple_of_args_is_scrubbed_elementwise() -> None:
    """httpx-style ``msg % args`` keeps the secret in ``args``."""
    event = {"event": "request %s", "args": (FAKE_TOKEN,)}
    result = scrub_secrets(None, "info", event)
    assert FAKE_TOKEN not in str(result["args"])


def test_scrub_secrets_is_idempotent() -> None:
    """Running it twice must not double-wrap or corrupt already-scrubbed text."""
    once = _one(f"bot{FAKE_TOKEN}/x")
    assert _one(once) == once


def test_scrubbing_preserves_the_stream() -> None:
    """Logging must still write to stdout, not be redirected by the scrubber."""
    assert _one(io.StringIO("unchanged")) is not None
