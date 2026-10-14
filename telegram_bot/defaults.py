"""First-run defaults and the typed config view over SQLite.

RULE 1: no config file. Every value here is written into the ``config`` table on
first run and read back through :class:`BotConfig`. Nothing reads from disk and
nothing reads from the environment except the two Telegram credentials.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, ClassVar

from telegram_bot.db import Database, utcnow

__all__ = [
    "COOLDOWN_MINUTES",
    "DEFAULT_CONFIG",
    "DEFAULT_QUIET_HOURS",
    "DEFAULT_SYMBOLS",
    "DEFAULT_TIMEFRAMES",
    "BotConfig",
    "seed_defaults",
]

#: Symbols enabled on first run.
DEFAULT_SYMBOLS: tuple[str, ...] = ("XAUUSD", "BTCUSD")

#: Internal timeframe identifiers, ascending. The bot exposes them to users as
#: ``1mn``/``5mn``/``15mn``/``1h``; see :mod:`telegram_bot.timeframes`.
DEFAULT_TIMEFRAMES: tuple[str, ...] = ("1m", "5m", "15m", "1h")

#: UTC hours during which no automatic alert is sent. Signals are still computed
#: and stored; only delivery is suppressed.
DEFAULT_QUIET_HOURS: tuple[int, ...] = (22, 23, 0, 1, 2)

#: Per-timeframe cooldown, in minutes.
COOLDOWN_MINUTES: dict[str, int] = {"1m": 15, "5m": 30, "15m": 45, "1h": 60}

#: Maximum automatic signals per hour, per symbol/timeframe pair.
DEFAULT_MAX_PER_HOUR: int = 4

#: The full default configuration, exactly as specified.
DEFAULT_CONFIG: dict[str, Any] = {
    "mode": "balanced",
    "confidence_min": 0.60,
    "risk_sl_atr": 1.5,
    "risk_tp1_atr": 2.5,
    "risk_tp2_atr": 4.0,
    "orderflow": "enabled",
    "quiet_hours": json.dumps(list(DEFAULT_QUIET_HOURS)),
    "max_per_hour": DEFAULT_MAX_PER_HOUR,
    "confluence": "enabled",
    "confluence_min_tfs": 2,
    "confluence_window_candles": 3,
    # Broadcast gate. The engine produces a signal for every qualifying bar; this
    # decides which of them reach subscribers.
    #
    # A WEAK signal is a real signal with a real derivation behind it, but its
    # direction on a near-flat bar is close to a coin flip. Broadcasting those to
    # subscribers who cannot see the derivation would be passing on noise, so
    # they are computed, stored and counted, but not sent.
    #
    # Stored in SQLite like every other setting (RULE 1) and seeded on first run.
    "broadcast_min_strength": "MODERATE",
    "broadcast_min_confidence": 0.40,
    "XAUUSD.atr_period": 14,
    "XAUUSD.sl_atr_mult": 1.5,
    "XAUUSD.tp1_atr_mult": 2.5,
    "XAUUSD.tp2_atr_mult": 4.0,
    "BTCUSD.atr_period": 14,
    "BTCUSD.sl_atr_mult": 1.5,
    "BTCUSD.tp1_atr_mult": 2.5,
    "BTCUSD.tp2_atr_mult": 4.0,
}


def seed_defaults(db: Database) -> bool:
    """Write the default configuration, symbols and timeframes.

    Idempotent: every insert is conditional, so calling this on every start is
    safe and does not overwrite values that already exist.

    Args:
        db: Initialised database.

    Returns:
        ``True`` when this call actually inserted something, i.e. it was the
        first run.
    """
    first_run = db.get_config("mode") is None

    missing = {
        key: value for key, value in DEFAULT_CONFIG.items() if db.get_config(key) is None
    }
    if missing:
        db.set_configs({key: str(value) for key, value in missing.items()})

    quiet = json.dumps(list(DEFAULT_QUIET_HOURS))
    for symbol in DEFAULT_SYMBOLS:
        db.add_symbol(symbol)
        for timeframe in DEFAULT_TIMEFRAMES:
            db.add_timeframe(
                symbol,
                timeframe,
                cooldown_minutes=COOLDOWN_MINUTES[timeframe],
                max_signals_per_hour=DEFAULT_MAX_PER_HOUR,
                quiet_hours=quiet,
            )

    if first_run:
        db.set_config("seeded_at", str(utcnow()))
    return first_run


@dataclass(frozen=True)
class SymbolRisk:
    """Per-symbol risk parameters.

    Attributes:
        symbol: Instrument ticker.
        atr_period: ATR lookback.
        sl_atr_mult: Stop-loss distance in ATR multiples.
        tp1_atr_mult: First take-profit distance in ATR multiples.
        tp2_atr_mult: Second take-profit distance in ATR multiples.
    """

    symbol: str
    atr_period: int
    sl_atr_mult: float
    tp1_atr_mult: float
    tp2_atr_mult: float


@dataclass(frozen=True)
class BotConfig:
    """Typed view over the ``config`` table.

    Read once at startup and refreshed on demand. Nothing here is writable from a
    command (RULE 2), so the fields can be treated as immutable.
    """

    mode: str = "balanced"
    confidence_min: float = 0.60
    risk_sl_atr: float = 1.5
    risk_tp1_atr: float = 2.5
    risk_tp2_atr: float = 4.0
    orderflow_enabled: bool = True
    quiet_hours: tuple[int, ...] = DEFAULT_QUIET_HOURS
    max_per_hour: int = DEFAULT_MAX_PER_HOUR
    confluence_enabled: bool = True
    confluence_min_tfs: int = 2
    confluence_window_candles: int = 3

    #: Broadcast gate. A signal below either threshold is computed, stored and
    #: counted, but not sent to subscribers. See ``DEFAULT_CONFIG`` for why a
    #: WEAK signal is withheld rather than published.
    broadcast_min_strength: str = "MODERATE"
    broadcast_min_confidence: float = 0.40

    #: Strength bands, weakest first, for comparison against
    #: ``broadcast_min_strength``.
    STRENGTH_ORDER: ClassVar[tuple[str, ...]] = ("WEAK", "MODERATE", "STRONG")

    symbol_risk: dict[str, SymbolRisk] = field(default_factory=dict)

    def passes_broadcast_gate(self, strength: str, confidence: float) -> bool:
        """Whether a signal is worth sending to subscribers.

        Either condition is sufficient: the band or the raw confidence. A
        MODERATE band entered on a 0.31 confidence is a marginal call, but a
        STRONG band from an unusually confident composite should not be held back
        by a rounding difference, so an "or" is used rather than an "and".

        Args:
            strength: The signal's band.
            confidence: The signal's weighted confidence.

        Returns:
            ``True`` when the signal clears the gate.
        """
        band = (strength or "").upper()
        allowed = [s.upper() for s in self.STRENGTH_ORDER]
        try:
            threshold = allowed.index(self.broadcast_min_strength.upper())
            band_ok = band in allowed and allowed.index(band) >= threshold
        except ValueError:
            # An unrecognised configured band must not silently disable delivery.
            band_ok = True
        return band_ok or confidence >= self.broadcast_min_confidence

    @classmethod
    def load(cls, db: Database) -> BotConfig:
        """Read the configuration from SQLite, falling back to defaults.

        A missing or malformed value falls back rather than raising: a bot that
        refuses to start because one config key is odd is worse than one running
        on a documented default.
        """
        fallback = cls()
        symbols = db.symbols(enabled_only=False) or list(DEFAULT_SYMBOLS)
        return cls(
            mode=db.get_config("mode", fallback.mode) or fallback.mode,
            confidence_min=_as_float(
                db.get_config("confidence_min"), fallback.confidence_min
            ),
            risk_sl_atr=_as_float(db.get_config("risk_sl_atr"), fallback.risk_sl_atr),
            risk_tp1_atr=_as_float(db.get_config("risk_tp1_atr"), fallback.risk_tp1_atr),
            risk_tp2_atr=_as_float(db.get_config("risk_tp2_atr"), fallback.risk_tp2_atr),
            orderflow_enabled=(db.get_config("orderflow", "enabled") or "enabled")
            == "enabled",
            quiet_hours=_as_int_list(
                db.get_json_config("quiet_hours"), fallback.quiet_hours
            ),
            max_per_hour=int(
                _as_float(db.get_config("max_per_hour"), fallback.max_per_hour)
            ),
            confluence_enabled=(
                db.get_config("confluence", "enabled") or "enabled"
            )
            == "enabled",
            confluence_min_tfs=int(
                _as_float(
                    db.get_config("confluence_min_tfs"), fallback.confluence_min_tfs
                )
            ),
            confluence_window_candles=int(
                _as_float(
                    db.get_config("confluence_window_candles"),
                    fallback.confluence_window_candles,
                )
            ),
            broadcast_min_strength=(
                (db.get_config("broadcast_min_strength") or fallback.broadcast_min_strength)
                .strip()
                .upper()
            ),
            broadcast_min_confidence=_as_float(
                db.get_config("broadcast_min_confidence"),
                fallback.broadcast_min_confidence,
            ),
            symbol_risk={
                symbol: cls._load_symbol_risk(db, symbol, fallback) for symbol in symbols
            },
        )

    @staticmethod
    def _load_symbol_risk(db: Database, symbol: str, fallback: BotConfig) -> SymbolRisk:
        """Read one symbol's risk block, falling back to the global multipliers."""
        return SymbolRisk(
            symbol=symbol,
            atr_period=int(
                _as_float(db.get_config(f"{symbol}.atr_period"), 14.0)
            ),
            sl_atr_mult=_as_float(
                db.get_config(f"{symbol}.sl_atr_mult"), fallback.risk_sl_atr
            ),
            tp1_atr_mult=_as_float(
                db.get_config(f"{symbol}.tp1_atr_mult"), fallback.risk_tp1_atr
            ),
            tp2_atr_mult=_as_float(
                db.get_config(f"{symbol}.tp2_atr_mult"), fallback.risk_tp2_atr
            ),
        )

    def risk_for(self, symbol: str) -> SymbolRisk:
        """Risk parameters for one symbol, falling back to the global values.

        A symbol with no explicit block still gets sane numbers rather than a
        crash, which matters because ``symbols`` is a database table and could in
        principle contain a symbol with no seeded risk keys.
        """
        symbol = symbol.upper()
        existing = self.symbol_risk.get(symbol)
        if existing is not None:
            return existing
        return SymbolRisk(
            symbol=symbol,
            atr_period=14,
            sl_atr_mult=self.risk_sl_atr,
            tp1_atr_mult=self.risk_tp1_atr,
            tp2_atr_mult=self.risk_tp2_atr,
        )

    def is_quiet_hour(self, hour_utc: int) -> bool:
        """Whether ``hour_utc`` is a configured quiet hour."""
        return int(hour_utc) in self.quiet_hours


def _as_float(raw: str | None, default: float) -> float:
    """Parse a float, falling back on absent or malformed content."""
    if raw is None:
        return default
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default


def _as_int_list(raw: Any, default: tuple[int, ...]) -> tuple[int, ...]:
    """Parse a list of hours, falling back on anything unusable."""
    if not isinstance(raw, list) or not raw:
        return default
    hours: list[int] = []
    for value in raw:
        try:
            hours.append(int(value))
        except (TypeError, ValueError):
            return default
    return tuple(hours)
