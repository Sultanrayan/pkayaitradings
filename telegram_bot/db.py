"""SQLite persistence for the Telegram signal bot.

All configuration lives here (RULE 1). There is no config file, no setup flow and
no admin surface — the schema is created on first run and populated with the
defaults declared in :mod:`telegram_bot.defaults`.

Thread and task model
---------------------
The bot is asyncio, but SQLite calls are synchronous and cheap (local file, no
network). Every public method therefore takes the lock internally and is safe to
call from any task; no cursor is shared between tasks.

Time is stored as integer Unix seconds. That is what the schema specifies, and it
keeps range queries index-friendly. ``datetime`` objects are converted at the
boundary only.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

__all__ = [
    "SCHEMA_STATEMENTS",
    "Database",
    "SignalRow",
    "utcnow",
]

SCHEMA_STATEMENTS: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS config (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS symbols (
        symbol TEXT PRIMARY KEY,
        enabled INTEGER DEFAULT 1,
        added_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS timeframes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        enabled INTEGER DEFAULT 1,
        cooldown_minutes INTEGER DEFAULT 30,
        max_signals_per_hour INTEGER DEFAULT 4,
        quiet_hours TEXT,
        UNIQUE(symbol, timeframe)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS signals (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        action TEXT NOT NULL,
        entry REAL NOT NULL,
        sl REAL NOT NULL,
        tp1 REAL NOT NULL,
        tp2 REAL NOT NULL,
        confidence REAL NOT NULL,
        layers TEXT NOT NULL,
        order_flow TEXT,
        reason TEXT NOT NULL,
        is_confluence INTEGER DEFAULT 0,
        confluence_tfs TEXT,
        sent_at INTEGER NOT NULL,
        outcome TEXT,
        closed_at INTEGER,
        pnl_pct REAL,
        UNIQUE(symbol, timeframe, timestamp, action)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS order_flow_alerts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        symbol TEXT NOT NULL,
        timeframe TEXT NOT NULL,
        timestamp INTEGER NOT NULL,
        alert_type TEXT NOT NULL,
        details TEXT NOT NULL,
        sent_at INTEGER NOT NULL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS performance (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        period TEXT NOT NULL,
        timeframe TEXT,
        start_ts INTEGER NOT NULL,
        end_ts INTEGER NOT NULL,
        total_signals INTEGER,
        wins INTEGER,
        losses INTEGER,
        win_rate REAL,
        avg_rr REAL
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS rate_limits (
        user_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        last_used INTEGER NOT NULL,
        PRIMARY KEY (user_id, command)
    )
    """,
    # Indexes are not in the specified schema but are additive and necessary:
    # without these, every scan's "have I processed this bar?" check is a full
    # table scan on `signals`, which grows by ~1150 rows/day.
    "CREATE INDEX IF NOT EXISTS idx_signals_pair_ts ON signals(symbol, timeframe, timestamp)",
    "CREATE INDEX IF NOT EXISTS idx_signals_sent ON signals(sent_at)",
    "CREATE INDEX IF NOT EXISTS idx_signals_confluence ON signals(is_confluence, sent_at)",
    "CREATE INDEX IF NOT EXISTS idx_signals_outcome ON signals(outcome)",
    "CREATE INDEX IF NOT EXISTS idx_of_alerts_ts ON order_flow_alerts(symbol, timestamp)",
    # Companion to the specified `rate_limits` table.
    #
    # The specified schema keeps one `last_used` timestamp per (user, command).
    # That is enough to express "1 per minute" exactly, but it cannot express
    # "/status 10 per minute": with a single timestamp there is no way to know
    # whether the previous four calls fell inside the window or an hour ago.
    # Counting against `last_used` alone would let a user fire 10 `/status` calls
    # in the first second and then be locked out, which is not a rate limit.
    #
    # This table records each use as a row so the count in a sliding window is
    # exact. The specified table is still written, and is still what the 1-per-minute
    # commands rely on; this one makes the higher limits correct.
    """
    CREATE TABLE IF NOT EXISTS rate_limit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        command TEXT NOT NULL,
        used_at INTEGER NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_rle_lookup ON rate_limit_events(user_id, command, used_at)",
    # Who receives automatic alerts.
    #
    # Not in the specified schema, and not configuration: this is runtime state,
    # not a setting. It exists because the bot is open to any user — a person who
    # sends /start is registered here and receives subsequent alerts, with no
    # allow-list, admin command or setup step (RULE 2).
    #
    # `user_id` is the primary key rather than `chat_id` because a user may start
    # the bot in a private chat and later in a group; the account follows them,
    # not the conversation.
    """
    CREATE TABLE IF NOT EXISTS subscribers (
        user_id INTEGER PRIMARY KEY,
        chat_id INTEGER NOT NULL,
        username TEXT,
        first_name TEXT,
        subscribed_at INTEGER NOT NULL,
        last_seen INTEGER NOT NULL,
        active INTEGER NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_subs_active ON subscribers(active, last_seen)",
)


def utcnow() -> int:
    """Current Unix time in whole seconds.

    Every timestamp the bot stores or compares comes from here, so tests can freeze
    time by patching this one function.
    """
    return int(time.time())


#: Internal timeframe names, duplicated here to keep :mod:`telegram_bot.db` free of
#: an import from :mod:`telegram_bot.timeframes`. That module imports nothing from
#: this one, so the cycle would not actually form — but a store should not need to
#: know the bot's vocabulary to sort a column.
_KNOWN_TFS = {"1m", "5m", "15m", "1h"}


@dataclass(frozen=True)
class Subscriber:
    """One user who receives automatic alerts.

    Attributes:
        user_id: Telegram account id, the primary key.
        chat_id: Conversation alerts are delivered to. Normally equal to
            ``user_id`` for a private chat, but a group chat has its own id and
            the two must not be conflated.
        username: Telegram ``@handle``, or ``None``.
        first_name: Display name, or ``None``.
        subscribed_at: When the user first pressed ``/start``.
        last_seen: When the user was last active.
        active: Whether alerts are currently being delivered.
    """

    user_id: int
    chat_id: int
    username: str | None
    first_name: str | None
    subscribed_at: int
    last_seen: int
    active: bool


@dataclass(frozen=True)
class SignalRow:
    """One stored signal, as read back from the database.

    Attributes:
        id: Row id.
        symbol: Instrument ticker.
        timeframe: Internal timeframe, e.g. ``5m``.
        timestamp: Unix seconds of the anchor bar's close.
        action: ``BUY`` or ``SELL``.
        entry: Entry price.
        sl: Stop-loss level.
        tp1: First take-profit.
        tp2: Second take-profit.
        confidence: Confidence in ``[0, 1]``.
        layers: Per-layer scores, decoded from JSON.
        order_flow: Order-flow snapshot, decoded from JSON, or ``None``.
        reason: Human-readable justification.
        is_confluence: Whether this row is part of a confluence alert.
        confluence_tfs: Timeframes participating in the confluence.
        sent_at: Unix seconds when the row was written.
        outcome: ``win``, ``loss``, ``open``, or ``None``.
        closed_at: Unix seconds the outcome was recorded.
        pnl_pct: Realised move in percent, or ``None``.
    """

    id: int
    symbol: str
    timeframe: str
    timestamp: int
    action: str
    entry: float
    sl: float
    tp1: float
    tp2: float
    confidence: float
    layers: dict[str, float]
    order_flow: dict[str, Any] | None
    reason: str
    is_confluence: bool
    confluence_tfs: tuple[str, ...]
    sent_at: int
    outcome: str | None
    closed_at: int | None
    pnl_pct: float | None


class Database:
    """Thread-safe SQLite wrapper owning the bot's entire state.

    Args:
        path: Database file path. ``":memory:"`` is supported for tests.

    Example:
        >>> db = Database(":memory:")
        >>> db.initialise()
        >>> db.symbols()
        ['XAUUSD', 'BTCUSD']
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        # WAL keeps readers from blocking the scheduler's writes. Foreign keys are
        # off by default in SQLite and are not needed here (no relational
        # constraints are declared), but durability settings are worth pinning.
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")
        self._conn.commit()

    def close(self) -> None:
        """Close the underlying connection."""
        with self._lock:
            self._conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ #
    # Schema
    # ------------------------------------------------------------------ #

    def initialise(self) -> None:
        """Create the schema if absent. Safe to call repeatedly."""
        with self._lock:
            for statement in SCHEMA_STATEMENTS:
                self._conn.execute(statement)
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Config
    # ------------------------------------------------------------------ #

    def set_config(self, key: str, value: str) -> None:
        """Write one config key.

        Not reachable from any command — RULE 2 means there is no admin surface.
        Used only by first-run defaults and by tests.
        """
        with self._lock:
            self._conn.execute(
                "INSERT INTO config(key, value, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                (key, value, utcnow()),
            )
            self._conn.commit()

    def set_configs(self, items: dict[str, str]) -> None:
        """Write several config keys in one transaction."""
        with self._lock:
            self._conn.executemany(
                "INSERT INTO config(key, value, updated_at) VALUES(?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
                "updated_at=excluded.updated_at",
                [(k, v, utcnow()) for k, v in items.items()],
            )
            self._conn.commit()

    def get_config(self, key: str, default: str | None = None) -> str | None:
        """Read one config key, or ``default`` when absent."""
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM config WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row is not None else default

    def get_json_config(self, key: str, default: Any = None) -> Any:
        """Read a config key holding JSON, falling back on malformed content."""
        raw = self.get_config(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # A corrupt value must not crash the bot; the caller's default stands.
            return default

    def all_config(self) -> dict[str, str]:
        """Every config key/value pair."""
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM config").fetchall()
        return {row["key"]: row["value"] for row in rows}

    # ------------------------------------------------------------------ #
    # Symbols and timeframes
    # ------------------------------------------------------------------ #

    def add_symbol(self, symbol: str, *, enabled: bool = True) -> None:
        """Insert a symbol if absent. Existing rows are left untouched."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO symbols(symbol, enabled, added_at) VALUES(?, ?, ?) "
                "ON CONFLICT(symbol) DO NOTHING",
                (symbol.upper(), 1 if enabled else 0, utcnow()),
            )
            self._conn.commit()

    def symbols(self, *, enabled_only: bool = True) -> list[str]:
        """Configured symbols, alphabetically."""
        query = "SELECT symbol FROM symbols"
        if enabled_only:
            query += " WHERE enabled = 1"
        query += " ORDER BY symbol"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [row["symbol"] for row in rows]

    def add_timeframe(
        self,
        symbol: str,
        timeframe: str,
        *,
        enabled: bool = True,
        cooldown_minutes: int = 30,
        max_signals_per_hour: int = 4,
        quiet_hours: str | None = None,
    ) -> None:
        """Insert a symbol/timeframe pair if absent."""
        with self._lock:
            self._conn.execute(
                "INSERT INTO timeframes"
                "(symbol, timeframe, enabled, cooldown_minutes, "
                "max_signals_per_hour, quiet_hours) VALUES(?, ?, ?, ?, ?, ?) "
                "ON CONFLICT(symbol, timeframe) DO NOTHING",
                (
                    symbol.upper(),
                    timeframe,
                    1 if enabled else 0,
                    cooldown_minutes,
                    max_signals_per_hour,
                    quiet_hours,
                ),
            )
            self._conn.commit()

    def timeframes_for(self, symbol: str, *, enabled_only: bool = True) -> list[str]:
        """Timeframes configured for one symbol, finest first.

        Ordering is by bar duration, not by string. A lexicographic ``ORDER BY``
        puts ``15m`` before ``1m`` and ``5m`` last, which would render the command
        help as "15mn, 1h, 1mn, 5mn" instead of the specified "1mn, 5mn, 15mn, 1h".
        """
        query = "SELECT timeframe FROM timeframes WHERE symbol = ?"
        params: list[Any] = [symbol.upper()]
        if enabled_only:
            query += " AND enabled = 1"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        from telegram_bot.timeframes import bar_seconds

        return sorted(
            (row["timeframe"] for row in rows),
            key=lambda tf: bar_seconds(tf) if tf in _KNOWN_TFS else 0,
        )

    def timeframe_settings(self, symbol: str, timeframe: str) -> dict[str, Any]:
        """Cooldown and caps for one pair, falling back to spec defaults."""
        with self._lock:
            row = self._conn.execute(
                "SELECT cooldown_minutes, max_signals_per_hour, quiet_hours "
                "FROM timeframes WHERE symbol = ? AND timeframe = ?",
                (symbol.upper(), timeframe),
            ).fetchone()
        if row is None:
            return {"cooldown_minutes": 30, "max_signals_per_hour": 4, "quiet_hours": None}
        return {
            "cooldown_minutes": int(row["cooldown_minutes"]),
            "max_signals_per_hour": int(row["max_signals_per_hour"]),
            "quiet_hours": row["quiet_hours"],
        }

    def all_pairs(self) -> list[tuple[str, str]]:
        """Every enabled ``(symbol, timeframe)`` pair, ordered for stable scans."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT symbol, timeframe FROM timeframes WHERE enabled = 1 "
                "ORDER BY symbol, timeframe"
            ).fetchall()
        return [(row["symbol"], row["timeframe"]) for row in rows]

    # ------------------------------------------------------------------ #
    # Signals
    # ------------------------------------------------------------------ #

    def save_signal(self, record: dict[str, Any]) -> int | None:
        """Insert a signal, ignoring a duplicate for the same bar and action.

        The ``UNIQUE(symbol, timeframe, timestamp, action)`` constraint is what
        makes "no duplicates" a database guarantee rather than an application
        convention — a second scan of the same bar cannot double-post even if two
        scheduler jobs race.

        Args:
            record: Signal fields. ``timestamp`` and ``sent_at`` are Unix seconds;
                ``layers`` and ``order_flow`` are serialised to JSON here.

        Returns:
            The new row id, or ``None`` when the row already existed.
        """
        payload = (
            record["symbol"].upper(),
            record["timeframe"],
            int(record["timestamp"]),
            record["action"],
            float(record["entry"]),
            float(record["sl"]),
            float(record["tp1"]),
            float(record["tp2"]),
            float(record["confidence"]),
            json.dumps(record.get("layers", {}), sort_keys=True),
            json.dumps(record["order_flow"]) if record.get("order_flow") else None,
            record.get("reason", ""),
            1 if record.get("is_confluence") else 0,
            json.dumps(record["confluence_tfs"]) if record.get("confluence_tfs") else None,
            int(record.get("sent_at", utcnow())),
        )
        with self._lock:
            cursor = self._conn.execute(
                "INSERT OR IGNORE INTO signals"
                "(symbol, timeframe, timestamp, action, entry, sl, tp1, tp2, "
                "confidence, layers, order_flow, reason, is_confluence, "
                "confluence_tfs, sent_at) "
                "VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                payload,
            )
            self._conn.commit()
            return cursor.lastrowid if cursor.rowcount else None

    @staticmethod
    def _row_to_signal(row: sqlite3.Row) -> SignalRow:
        """Decode one row, tolerating malformed JSON in optional columns."""
        def _loads(value: str | None, fallback: Any) -> Any:
            if not value:
                return fallback
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return fallback

        return SignalRow(
            id=int(row["id"]),
            symbol=row["symbol"],
            timeframe=row["timeframe"],
            timestamp=int(row["timestamp"]),
            action=row["action"],
            entry=float(row["entry"]),
            sl=float(row["sl"]),
            tp1=float(row["tp1"]),
            tp2=float(row["tp2"]),
            confidence=float(row["confidence"]),
            layers=_loads(row["layers"], {}),
            order_flow=_loads(row["order_flow"], None),
            reason=row["reason"] or "",
            is_confluence=bool(row["is_confluence"]),
            confluence_tfs=tuple(_loads(row["confluence_tfs"], ()) or ()),
            sent_at=int(row["sent_at"]),
            outcome=row["outcome"],
            closed_at=None if row["closed_at"] is None else int(row["closed_at"]),
            pnl_pct=None if row["pnl_pct"] is None else float(row["pnl_pct"]),
        )

    def has_signal(self, symbol: str, timeframe: str, timestamp: int, action: str) -> bool:
        """Whether a signal for this bar and action is already stored.

        The scan loop calls this before computing anything, so a bar is processed
        exactly once even across restarts.
        """
        with self._lock:
            row = self._conn.execute(
                "SELECT 1 FROM signals WHERE symbol = ? AND timeframe = ? "
                "AND timestamp = ? AND action = ? LIMIT 1",
                (symbol.upper(), timeframe, int(timestamp), action),
            ).fetchone()
        return row is not None

    def latest_signal(
        self, symbol: str, timeframe: str | None = None, *, confluence_only: bool = False
    ) -> SignalRow | None:
        """Most recent signal for a pair, or for a symbol across timeframes.

        Args:
            symbol: Instrument ticker.
            timeframe: Restrict to one timeframe, or ``None`` for any.
            confluence_only: Restrict to confluence alerts.

        Returns:
            The newest row by bar timestamp, or ``None``.
        """
        query = "SELECT * FROM signals WHERE symbol = ?"
        params: list[Any] = [symbol.upper()]
        if timeframe is not None:
            query += " AND timeframe = ?"
            params.append(timeframe)
        if confluence_only:
            query += " AND is_confluence = 1"
        query += " ORDER BY timestamp DESC, id DESC LIMIT 1"
        with self._lock:
            row = self._conn.execute(query, params).fetchone()
        return self._row_to_signal(row) if row is not None else None

    def last_signal_time(self, symbol: str, timeframe: str) -> int | None:
        """Bar timestamp of the most recent signal for a pair, or ``None``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT timestamp FROM signals WHERE symbol = ? AND timeframe = ? "
                "ORDER BY timestamp DESC LIMIT 1",
                (symbol.upper(), timeframe),
            ).fetchone()
        return int(row["timestamp"]) if row is not None else None

    def signals_since(self, since_ts: int) -> list[SignalRow]:
        """Every signal sent at or after ``since_ts``, oldest first."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE sent_at >= ? ORDER BY sent_at, id",
                (int(since_ts),),
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def signals_in_range(
        self, start_ts: int, end_ts: int, *, symbol: str | None = None
    ) -> list[SignalRow]:
        """Signals whose bar timestamp falls in ``[start_ts, end_ts]``."""
        query = "SELECT * FROM signals WHERE timestamp BETWEEN ? AND ?"
        params: list[Any] = [int(start_ts), int(end_ts)]
        if symbol is not None:
            query += " AND symbol = ?"
            params.append(symbol.upper())
        query += " ORDER BY timestamp, id"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def signals_in_window(
        self, symbol: str, timeframe: str, start_ts: int, end_ts: int
    ) -> list[SignalRow]:
        """Signals for one pair within a window — used by the confluence check."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE symbol = ? AND timeframe = ? "
                "AND timestamp BETWEEN ? AND ? ORDER BY timestamp",
                (symbol.upper(), timeframe, int(start_ts), int(end_ts)),
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def signal_count_since(self, since_ts: int) -> int:
        """How many signals were sent since ``since_ts``."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM signals WHERE sent_at >= ?", (int(since_ts),)
            ).fetchone()
        return int(row["n"])

    def recent_signals(self, symbol: str, *, since_ts: int | None = None) -> list[SignalRow]:
        """Newest-first signals for one symbol, optionally within a window."""
        query = "SELECT * FROM signals WHERE symbol = ?"
        params: list[Any] = [symbol.upper()]
        if since_ts is not None:
            query += " AND sent_at >= ?"
            params.append(int(since_ts))
        query += " ORDER BY sent_at DESC, id DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def count_signals_for_pair_since(self, symbol: str, timeframe: str, since_ts: int) -> int:
        """Signals for one pair since ``since_ts`` — the hourly cap check."""
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM signals WHERE symbol = ? AND timeframe = ? "
                "AND sent_at >= ?",
                (symbol.upper(), timeframe, int(since_ts)),
            ).fetchone()
        return int(row["n"])

    def set_outcome(self, signal_id: int, outcome: str, pnl_pct: float) -> None:
        """Record a resolved outcome for a signal.

        Written by the scanner when a later bar reaches TP1 or SL, never by a
        command.
        """
        with self._lock:
            self._conn.execute(
                "UPDATE signals SET outcome = ?, closed_at = ?, pnl_pct = ? WHERE id = ?",
                (outcome, utcnow(), float(pnl_pct), int(signal_id)),
            )
            self._conn.commit()

    def open_signals(self) -> list[SignalRow]:
        """Signals still awaiting an outcome."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE outcome IS NULL OR outcome = 'open' "
                "ORDER BY timestamp"
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    def outcomes_since(self, since_ts: int) -> list[SignalRow]:
        """Resolved signals since ``since_ts``, for the performance command."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM signals WHERE outcome IS NOT NULL AND outcome != 'open' "
                "AND closed_at >= ? ORDER BY closed_at",
                (int(since_ts),),
            ).fetchall()
        return [self._row_to_signal(row) for row in rows]

    # ------------------------------------------------------------------ #
    # Order flow alerts
    # ------------------------------------------------------------------ #

    def record_order_flow_alert(
        self, symbol: str, timeframe: str, timestamp: int, alert_type: str, details: str
    ) -> int:
        """Store an order-flow alert."""
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO order_flow_alerts"
                "(symbol, timeframe, timestamp, alert_type, details, sent_at) "
                "VALUES(?, ?, ?, ?, ?, ?)",
                (symbol.upper(), timeframe, int(timestamp), alert_type, details, utcnow()),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def recent_order_flow_alerts(self, symbol: str, *, limit: int = 20) -> list[sqlite3.Row]:
        """Newest order-flow alerts for a symbol."""
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM order_flow_alerts WHERE symbol = ? "
                "ORDER BY timestamp DESC, id DESC LIMIT ?",
                (symbol.upper(), int(limit)),
            ).fetchall()
        return list(rows)

    # ------------------------------------------------------------------ #
    # Rate limits
    # ------------------------------------------------------------------ #

    def check_rate_limit(
        self, user_id: int, command: str, limit: int, window_seconds: int = 60
    ) -> bool:
        """Record a command use and report whether it is allowed.

        Args:
            user_id: Telegram user id.
            command: Command name, without the slash.
            limit: Maximum uses per window.
            window_seconds: Window length in seconds.

        Returns:
            ``True`` when the call is allowed.

        A rejected call is not recorded, so a user who exhausts a limit is not
        penalised for the whole window from the moment they hit it.
        """
        now = utcnow()
        cutoff = now - window_seconds
        with self._lock:
            self._prune_rate_events(now, window_seconds)
            used = self._conn.execute(
                "SELECT COUNT(*) AS n FROM rate_limit_events "
                "WHERE user_id = ? AND command = ? AND used_at >= ?",
                (int(user_id), command, cutoff),
            ).fetchone()
            if int(used["n"]) >= limit:
                return False

            self._conn.execute(
                "INSERT INTO rate_limits(user_id, command, last_used) VALUES(?, ?, ?) "
                "ON CONFLICT(user_id, command) DO UPDATE SET last_used = excluded.last_used",
                (int(user_id), command, now),
            )
            self._conn.execute(
                "INSERT INTO rate_limit_events(user_id, command, used_at) VALUES(?, ?, ?)",
                (int(user_id), command, now),
            )
            self._conn.commit()
        return True

    def _prune_rate_events(self, now: int, window_seconds: int) -> None:
        """Delete event rows older than the widest window worth keeping.

        Pruned inside the caller's transaction. Without this the table grows
        without bound — one row per command use, forever.
        """
        self._conn.execute(
            "DELETE FROM rate_limit_events WHERE used_at < ?", (int(now - window_seconds),)
        )

    def rate_limit_uses(self, user_id: int, command: str, window_seconds: int = 60) -> int:
        """How many times a command was used in the trailing window."""
        cutoff = utcnow() - window_seconds
        with self._lock:
            row = self._conn.execute(
                "SELECT COUNT(*) AS n FROM rate_limit_events "
                "WHERE user_id = ? AND command = ? AND used_at >= ?",
                (int(user_id), command, cutoff),
            ).fetchone()
        return int(row["n"])

    def clear_rate_limits(self, user_id: int | None = None) -> None:
        """Drop recorded rate-limit state. Used by tests only."""
        with self._lock:
            if user_id is None:
                self._conn.execute("DELETE FROM rate_limits")
                self._conn.execute("DELETE FROM rate_limit_events")
            else:
                self._conn.execute(
                    "DELETE FROM rate_limits WHERE user_id = ?", (int(user_id),)
                )
                self._conn.execute(
                    "DELETE FROM rate_limit_events WHERE user_id = ?", (int(user_id),)
                )
            self._conn.commit()

    # ------------------------------------------------------------------ #
    # Subscribers
    # ------------------------------------------------------------------ #

    def subscribe(
        self,
        user_id: int,
        chat_id: int,
        *,
        username: str | None = None,
        first_name: str | None = None,
        now: int | None = None,
    ) -> None:
        """Register a user for automatic alerts, or refresh an existing one.

        Idempotent, and deliberately so: ``/start`` runs on every launch of the
        bot by every subscriber, so this must never duplicate or fail on repeat.

        A previously deactivated subscriber who returns is reactivated, because
        someone who messages the bot again is asking to hear from it.

        Args:
            user_id: Telegram account id.
            chat_id: Conversation the alerts should be delivered to.
            username: Telegram ``@handle``, for diagnostics only.
            first_name: Display name, for diagnostics only.
            now: Injected clock.
        """
        stamp = utcnow() if now is None else int(now)
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO subscribers(user_id, chat_id, username, first_name,
                                        subscribed_at, last_seen, active)
                VALUES(?, ?, ?, ?, ?, ?, 1)
                ON CONFLICT(user_id) DO UPDATE SET
                    chat_id=excluded.chat_id,
                    username=excluded.username,
                    first_name=excluded.first_name,
                    last_seen=excluded.last_seen,
                    active=1
                """,
                (int(user_id), int(chat_id), username, first_name, stamp, stamp),
            )
            self._conn.commit()

    def unsubscribe(self, user_id: int) -> None:
        """Stop sending alerts to a user, keeping their row for the record."""
        with self._lock:
            self._conn.execute(
                "UPDATE subscribers SET active=0 WHERE user_id=?", (int(user_id),)
            )
            self._conn.commit()

    def subscribers(self, *, active_only: bool = True) -> list[Subscriber]:
        """Everyone who should receive automatic alerts.

        Args:
            active_only: Exclude unsubscribed users. Default ``True``.

        Returns:
            Subscribers, least recently seen first, so a stale entry is reached
            last rather than first.
        """
        query = "SELECT * FROM subscribers"
        if active_only:
            query += " WHERE active=1"
        query += " ORDER BY last_seen ASC"
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [
            Subscriber(
                user_id=int(row["user_id"]),
                chat_id=int(row["chat_id"]),
                username=row["username"],
                first_name=row["first_name"],
                subscribed_at=int(row["subscribed_at"]),
                last_seen=int(row["last_seen"]),
                active=bool(row["active"]),
            )
            for row in rows
        ]

    def touch_subscriber(self, user_id: int, *, now: int | None = None) -> None:
        """Record that a user was seen, without changing their subscription.

        Applied on every command so ``subscribers()`` can order by genuine recent
        activity rather than by when someone last pressed /start.
        """
        stamp = utcnow() if now is None else int(now)
        with self._lock:
            self._conn.execute(
                "UPDATE subscribers SET last_seen=? WHERE user_id=?",
                (stamp, int(user_id)),
            )
            self._conn.commit()

    def subscriber_count(self, *, active_only: bool = True) -> int:
        """How many users receive alerts."""
        query = "SELECT COUNT(*) AS n FROM subscribers"
        if active_only:
            query += " WHERE active=1"
        with self._lock:
            row = self._conn.execute(query).fetchone()
        return int(row["n"])

    # ------------------------------------------------------------------ #
    # Performance snapshots
    # ------------------------------------------------------------------ #

    def save_performance_snapshot(
        self,
        period: str,
        start_ts: int,
        end_ts: int,
        *,
        timeframe: str | None = None,
        total_signals: int | None = None,
        wins: int | None = None,
        losses: int | None = None,
        win_rate: float | None = None,
        avg_rr: float | None = None,
    ) -> int:
        """Append a performance snapshot row.

        Snapshots are historical records written by the daily/weekly jobs; the
        ``/performance`` command reads live from ``signals`` rather than from here,
        so a stale snapshot can never make the command lie.
        """
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO performance"
                "(period, timeframe, start_ts, end_ts, total_signals, wins, losses, "
                "win_rate, avg_rr) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    period,
                    timeframe,
                    int(start_ts),
                    int(end_ts),
                    total_signals,
                    wins,
                    losses,
                    win_rate,
                    avg_rr,
                ),
            )
            self._conn.commit()
            return int(cursor.lastrowid or 0)

    def performance_snapshots(self, period: str | None = None) -> list[sqlite3.Row]:
        """Stored snapshots, newest first."""
        query = "SELECT * FROM performance"
        params: list[Any] = []
        if period is not None:
            query += " WHERE period = ?"
            params.append(period)
        query += " ORDER BY end_ts DESC"
        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return list(rows)


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    """Convert sqlite rows to plain dicts, for JSON logging."""
    return [dict(row) for row in rows]


def group_by(rows: Sequence[SignalRow], key: Any) -> dict[Any, list[SignalRow]]:
    """Group rows by a computed key."""
    grouped: dict[Any, list[SignalRow]] = {}
    for row in rows:
        grouped.setdefault(key(row), []).append(row)
    return grouped
