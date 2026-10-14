"""Telegram signal bot — technical indicators and order flow only.

No AI, no LLM, no model inference of any kind. Every signal comes from the seven
scored layers in :mod:`telegram_bot.layers`, computed on closed candles.

The three rules that shape this package:

**No config files.** All configuration is SQLite, seeded programmatically on
first run. The only environment variables are ``TELEGRAM_BOT_TOKEN`` and
``TELEGRAM_CHAT_ID``.

**No admin commands.** The public surface is exactly the twelve read-only
commands in :mod:`telegram_bot.commands`. There is no login, no setup token and
no way to change a setting from Telegram.

**No repainting.** A signal is computed only on a bar that has closed, and it
never changes afterwards. See :mod:`telegram_bot.engine`.

Quick start::

    export TELEGRAM_BOT_TOKEN=...   # from @BotFather
    export TELEGRAM_CHAT_ID=...     # your chat
    python -m telegram_bot

Order flow
----------
Layer 3 (weight 0.20) is scored from an **estimator**, not a tape. The upstream
feed carries no trade-level data — see :mod:`telegram_bot.orderflow` for exactly
what is missing and why the numbers are marked ``source="proxy"``.
"""

from __future__ import annotations

from telegram_bot.confluence import Confluence, detect_confluence
from telegram_bot.db import Database, SignalRow
from telegram_bot.defaults import BotConfig, seed_defaults
from telegram_bot.engine import Signal, compute_signal, to_closed_frame
from telegram_bot.layers import LAYER_WEIGHTS, LayerScores, compute_layers
from telegram_bot.orderflow import OrderFlowSnapshot, compute_order_flow

__all__ = [
    "LAYER_WEIGHTS",
    "BotConfig",
    "Confluence",
    "Database",
    "LayerScores",
    "OrderFlowSnapshot",
    "Signal",
    "SignalRow",
    "compute_layers",
    "compute_order_flow",
    "compute_signal",
    "detect_confluence",
    "seed_defaults",
    "to_closed_frame",
]
