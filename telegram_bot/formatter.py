"""Message rendering — the UI format, reproduced exactly.

Every string here is a specification, not a suggestion. The layout, the box-drawing
characters, the alignment padding, the label ordering and the sign convention are
all fixed by the required output, and ``tests/test_formatter.py`` asserts them
against literal expected text rather than against a pattern.

Two conventions worth stating once:

* **Sign convention.** For a BUY, SL is shown as a negative offset from entry and
  the targets as positive. For a SELL the geometry mirrors: SL positive, targets
  negative. That is not the raw price difference — it is the offset *from entry*,
  signed so it always points where it would cost or gain.
* **Price precision.** XAUUSD is quoted to 2 decimals; BTCUSD to 2 as well. The
  *offsets* use 2 decimals for both. Large-offset values on BTCUSD (thousands) read
  correctly without scientific notation because formatting goes through
  ``f"{value:,.2f}"`` with a manual sign, never through ``round``.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import UTC, datetime
from typing import Any

from telegram_bot.confluence import Confluence, confluence_label
from telegram_bot.engine import Signal, reward_to_risk
from telegram_bot.layers import DISPLAY_LAYERS
from telegram_bot.orderflow import OrderFlowSnapshot
from telegram_bot.timeframes import INTERNAL_TO_USER, label_for

__all__ = [
    "BRAND",
    "SEPARATOR",
    "format_analysis",
    "format_confluence",
    "format_help",
    "format_no_confluence",
    "format_orderflow",
    "format_performance",
    "format_signal",
    "format_start",
    "format_status",
    "progress_bar",
]

#: Footer on every message.
BRAND = "Powered by Pkay AI"

#: Horizontal rule under every header.
SEPARATOR = "━" * 20

#: Ten-cell progress bar used for layer percentages.
BAR_WIDTH = 10


#: Label column width for the confidence block. The required format aligns every
#: bar at column 12: "Trend:" is 6 characters plus 6 spaces, "Order Flow:" is 11
#: plus 1. Any other width visibly misaligns the bars.
LABEL_WIDTH = 12


def _fmt_money(value: float) -> str:
    """Fixed-2-decimal price with no thousands separator.

    The required format shows ``4156.23`` and ``95420.00``, not ``4,156.23`` and
    ``95,420.00``, so the separator is deliberately omitted.
    """
    return f"{value:.2f}"


def _fmt_offset(value: float) -> str:
    """Signed offset from entry, e.g. ``-24.13`` or ``+48.26``."""
    return f"{value:+.2f}"


def progress_bar(percent: int) -> str:
    """Render a 0-100 percentage as a ten-cell bar.

    The single place block characters are produced, so a change to the bar style
    cannot desynchronise the two message formats that use it.
    """
    percent = max(0, min(100, int(percent)))
    filled = round(percent / 100 * BAR_WIDTH)
    return "█" * filled + "░" * (BAR_WIDTH - filled)


def _timestamp(ts: int) -> str:
    """Format Unix seconds as ``YYYY-MM-DD HH:MM UTC``."""
    return datetime.fromtimestamp(int(ts), tz=UTC).strftime("%Y-%m-%d %H:%M UTC")


def _user_timeframe(timeframe: str) -> str:
    """User-facing token for an internal timeframe."""
    return INTERNAL_TO_USER.get(timeframe, timeframe)


def _header(symbol: str, timeframe: str) -> str:
    """``XAUUSD 5M`` — symbol plus display label."""
    return f"{symbol.upper()} {label_for(timeframe)}"


def format_signal(signal: Signal, *, levels: dict[str, float] | None = None) -> str:
    """Render a plain signal message.

    Args:
        signal: The signal to render.
        levels: Optional override for the displayed levels, used by confluence
            so the card can show blended levels. Defaults to the signal's own.

    Returns:
        The complete message, without a trailing newline.
    """
    values = levels or {
        "entry": signal.entry,
        "sl": signal.sl,
        "tp1": signal.tp1,
        "tp2": signal.tp2,
    }
    entry = float(values["entry"])
    sl = float(values["sl"])
    tp1 = float(values["tp1"])
    tp2 = float(values["tp2"])

    icon = "🟢" if signal.action == "BUY" else "🔴"
    header = f"{icon} {signal.action} — {_header(signal.symbol, signal.timeframe)}"

    # Offsets are always measured from entry and always carry a sign, so a SELL
    # reads as the mirror image of a BUY rather than as three negative numbers.
    sl_offset = sl - entry
    tp1_offset = tp1 - entry
    tp2_offset = tp2 - entry

    rr = reward_to_risk(entry, sl, tp2)

    lines: list[str] = [
        header,
        SEPARATOR,
        f"Entry: {_fmt_money(entry)}",
        f"SL:    {_fmt_money(sl)} ({_fmt_offset(sl_offset)})",
        f"TP1:   {_fmt_money(tp1)} ({_fmt_offset(tp1_offset)})",
        f"TP2:   {_fmt_money(tp2)} ({_fmt_offset(tp2_offset)})",
        f"RR:    1:{rr:.1f}",
        "",
        f"Confidence: {round(signal.confidence * 100)}%",
    ]

    for index, name in enumerate(DISPLAY_LAYERS):
        percent = _layer_percent(signal, name)
        branch = "└" if index == len(DISPLAY_LAYERS) - 1 else "├"
        label = _display_label(name)
        lines.append(f"{branch} {(label + ':'):<{LABEL_WIDTH}}{progress_bar(percent)} {percent}%")

    lines.append("")
    lines.extend(_order_flow_block(signal.order_flow))

    # --- Narrative sections, derived from the bot's own indicators ---
    #
    # Each is emitted only when populated, so a Signal built without them (older
    # stored rows, a hand-built fixture) renders the card as it always did rather
    # than printing four empty headings.
    if signal.recommendation:
        lines.append("")
        lines.append("📋 Recommendation:")
        lines.append(_wrap(signal.recommendation))

    if signal.explanation:
        lines.append("")
        lines.append("📝 Explanation:")
        lines.append(_wrap(signal.explanation))

    if signal.risk_notes:
        lines.append("")
        lines.append("⚠️ Risk Notes:")
        lines.append(_wrap(signal.risk_notes))

    if signal.invalidation:
        lines.append("")
        lines.append("🚫 Invalidation:")
        lines.append(_wrap(signal.invalidation))

    if signal.strength:
        lines.append("")
        lines.append(f"Strength: {signal.strength}")

    lines.append("")
    lines.append(f"Time: {_timestamp(signal.bar_ts)}")
    lines.append(BRAND)
    return "\n".join(lines)


def _wrap(text: str, width: int = 42) -> str:
    """Soft-wrap a narrative field to keep the card readable on a phone.

    Telegram does not wrap on the client for preformatted-looking blocks, and an
    un-wrapped 300-character explanation is unreadable in a chat list. Wrapping
    here rather than relying on the client keeps the card identical wherever it is
    rendered.
    """
    import textwrap

    collapsed = " ".join(text.split())
    if not collapsed:
        return ""
    return "\n".join(textwrap.wrap(collapsed, width=width))


def _display_label(name: str) -> str:
    """Human label for a layer, matching the required UI exactly."""
    return {
        "trend": "Trend",
        "momentum": "Momentum",
        "order_flow": "Order Flow",
        "volume": "Volume",
        "volatility": "Volatility",
    }.get(name, name.replace("_", " ").title())


def _layer_percent(signal: Signal, name: str) -> int:
    """Layer score as a 0-100 display percentage."""
    score = signal.layers.get(name)
    if score is None:
        return 0
    return round(min(1.0, abs(float(score))) * 100)


def _imbalance_text(delta: float, ratio: float) -> str:
    """Render the bid/ask imbalance, tolerating every degenerate value.

    ``ratio`` is bid-side over ask-side, so a sell must invert it. Three values
    need explicit handling, and the first two used to reach a ``ZeroDivisionError``
    or print ``inf`` on a live card:

    * ``0.0`` — a one-sided book with no ask. Inverting divides by zero.
    * ``inf`` — a one-sided book with no bid.
    * ``1.0`` — balanced, where an ``x`` ratio is noise.
    """
    if delta == 0 or ratio == 1.0:
        return "balanced" if delta == 0 else ("bid" if ratio > 1.0 else "ask")

    try:
        ratio_value = float(ratio)
    except (TypeError, ValueError):
        return "balanced"

    if ratio_value <= 0.0:
        # ``ratio`` is bid size over ask size, so zero means the bid side is
        # empty: an ask-only book. Not invertible, and the opposite of the
        # intuitive reading, so it is stated directly.
        return "ask"
    if ratio_value == float("inf"):
        # No ask at all: a pure bid book.
        return "bid"

    if delta > 0:
        return f"bid {ratio_value:.1f}x ask"
    inverted = 1.0 / ratio_value
    if inverted == float("inf"):
        return "ask"
    return f"ask {inverted:.1f}x bid"


def _order_flow_block(snapshot: OrderFlowSnapshot) -> list[str]:
    """The ``Order Flow:`` section."""
    delta = snapshot.delta
    side = "buyers" if delta > 0 else ("sellers" if delta < 0 else "flat")
    absorption = snapshot.absorption or "none"
    imbalance = _imbalance_text(float(snapshot.delta), float(snapshot.imbalance_ratio))

    return [
        "Order Flow:",
        f"├ Delta:      {delta:+.0f} ({side})",
        f"├ CVD:        {snapshot.cvd_trend}",
        f"├ Absorption: {absorption}",
        f"└ Imbalance:  {imbalance}",
    ]


def format_analysis(
    *,
    symbol: str,
    timeframe: str,
    layers: dict[str, Any],
    signal: Signal | None,
    reason: str,
    bar_ts: int,
) -> str:
    """Render the ``/agenza`` analysis block.

    Shown before the signal card. When there is no signal the card is omitted and
    the block ends with the reason, matching the required format.

    Args:
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        layers: Mapping of layer name to a ``LayerResult``.
        signal: The fired signal, or ``None``.
        reason: Explanation, used in both the fired and unfired variants.
        bar_ts: Bar close time in Unix seconds.

    Returns:
        The analysis block.
    """
    lines = [
        f"🔍 Analysis — {symbol.upper()} {label_for(timeframe)}",
        SEPARATOR,
    ]

    for index, name in enumerate(DISPLAY_LAYERS):
        branch = "└" if index == len(DISPLAY_LAYERS) - 1 else "├"
        label = _display_label(name)
        result = layers.get(name)
        percent = round(min(1.0, abs(result.score)) * 100) if result and result.evaluable else 0
        detail = result.detail if result and result.evaluable else "n/a"
        lines.append(
            f"{branch} {(label + ':'):<{LABEL_WIDTH}}"
            f"{progress_bar(percent)} {percent}% ({detail})"
        )

    lines.append("")
    if signal is None:
        lines.append("Signal: ❌ No signal")
        lines.append(f"Confidence: {round(_confidence_from(layers) * 100)}% (below {_threshold_text(reason)})")
        lines.append(f"Reason: {reason}")
        lines.append("")
        lines.append(f"Time: {_timestamp(bar_ts)}")
        lines.append(BRAND)
        return "\n".join(lines)

    # The required format shows ✅ for both directions here; the direction is
    # carried by the word, and the green/red circle appears on the card below.
    lines.append(f"Signal: ✅ {signal.action}")
    lines.append(f"Confidence: {round(signal.confidence * 100)}%")
    lines.append("")
    lines.append(format_signal(signal))
    return "\n".join(lines)


def _confidence_from(layers: dict[str, Any]) -> float:
    """Weighted confidence from raw layer results, for the no-signal branch."""
    from telegram_bot.layers import LAYER_NAMES, LAYER_WEIGHTS

    evaluable = [n for n in LAYER_NAMES if layers.get(n) and layers[n].evaluable]
    if not evaluable:
        return 0.0
    weighted = sum(LAYER_WEIGHTS[n] * layers[n].score for n in evaluable)
    available = sum(LAYER_WEIGHTS[n] for n in evaluable)
    return min(1.0, abs(weighted / available)) if available > 0 else 0.0


def _threshold_text(reason: str) -> str:
    """Extract the threshold for display, e.g. ``0.60 threshold``."""
    for token in reason.split():
        if token.replace(".", "").isdigit() and 0.0 < float(token) <= 1.0:
            return f"{float(token):.2f} threshold"
    return "0.60 threshold"


def format_confluence(confluence: Confluence) -> str:
    """Render a confluence alert.

    The header carries the flame icon and the shared direction; the body lists the
    participating timeframes, the representative signal's levels, and a
    timeframe-weighted confidence.
    """
    rep = confluence.representative
    entry = rep.entry
    sl = rep.sl
    tp1 = rep.tp1
    tp2 = rep.tp2

    rr = reward_to_risk(entry, sl, tp2)

    lines = [
        "🔥 Last Confluence Signal",
        SEPARATOR,
        f"🔥 CONFLUENCE {rep.action} — {rep.symbol.upper()}",
        f"Timeframes: {confluence_label(confluence.timeframes)}",
        f"Entry: {_fmt_money(entry)}",
        f"SL:    {_fmt_money(sl)} ({_fmt_offset(sl - entry)})",
        f"TP1:   {_fmt_money(tp1)} ({_fmt_offset(tp1 - entry)})",
        f"TP2:   {_fmt_money(tp2)} ({_fmt_offset(tp2 - entry)})",
        f"RR:    1:{rr:.1f}",
        "",
        f"Confidence: {round(confluence.confidence * 100)}% "
        f"(weighted across {len(confluence.timeframes)} TFs)",
        "",
        f"Time: {_timestamp(rep.timestamp)}",
        BRAND,
    ]
    return "\n".join(lines)


def format_no_confluence() -> str:
    """Rendered when no confluence is on record."""
    return "\n".join(
        [
            "🔥 Last Confluence Signal",
            SEPARATOR,
            "No confluence recorded yet.",
            "A confluence needs two or more timeframes agreeing.",
            "",
            f"Time: {_timestamp(int(datetime.now(tz=UTC).timestamp()))}",
            BRAND,
        ]
    )


def format_orderflow(snapshots: Sequence[tuple[str, OrderFlowSnapshot]]) -> str:
    """Render the live order-flow view for every symbol."""
    lines = ["⚡ Order Flow — Live", SEPARATOR]
    for symbol, snapshot in snapshots:
        delta = snapshot.delta
        side = "buyers" if delta > 0 else ("sellers" if delta < 0 else "flat")
        imbalance = _imbalance_text(float(snapshot.delta), float(snapshot.imbalance_ratio))

        lines.append(f"{symbol.upper()}:")
        lines.append(f"├ Delta:      {delta:+.0f} ({side})")
        lines.append(f"├ CVD:        {snapshot.cvd_trend}")
        lines.append(f"├ Absorption: {snapshot.absorption or 'none'}")
        lines.append(f"└ Imbalance:  {imbalance}")

    lines.append("")
    lines.append(f"Time: {_timestamp(int(datetime.now(tz=UTC).timestamp()))}")
    lines.append(BRAND)
    return "\n".join(lines)


def format_start(symbols: Sequence[str], timeframes: Iterable[str]) -> str:
    """Render ``/start``.

    ``symbols`` is a ``Sequence`` rather than an ``Iterable`` because the last
    entry is marked with a terminator instead of a tee, which needs a length.
    """
    timeframes = list(timeframes)
    header = ", ".join(_user_timeframe(tf) for tf in timeframes)
    lines = [
        "📖 Welcome to Pkay AI Signals",
        SEPARATOR,
        "Auto signals on:",
    ]
    for index, symbol in enumerate(symbols):
        branch = "└" if index == len(symbols) - 1 else "├"
        lines.append(f"{branch} {symbol.upper()}: {header}")
    lines.extend(
        [
            "",
            "Commands:",
            "/help         — all commands",
            "/status       — bot status",
            "/performance  — win rate",
            "/confluence   — last confluence",
            "/orderflow    — live order flow",
        ]
    )
    for symbol in symbols:
        lines.append(f"/agenza-{symbol.lower()} 1mn")
        lines.append(f"/agenza-{symbol.lower()} 5mn")
        lines.append(f"/agenza-{symbol.lower()} 15mn")
        lines.append(f"/agenza-{symbol.lower()} 1h")
    lines.extend(["", BRAND])
    return "\n".join(lines)


def format_help(symbols: Iterable[str]) -> str:
    """Render ``/help``, grouped by instrument."""
    symbols = list(symbols)
    lines = ["📖 Commands", SEPARATOR]
    for symbol in symbols:
        emoji = "🔍" if symbol.upper() == "XAUUSD" else "₿"
        name = "Gold" if symbol.upper() == "XAUUSD" else "Bitcoin"
        lines.append(f"{emoji} {name} ({symbol.upper()}):")
        for tf in ("1mn", "5mn", "15mn", "1h"):
            lines.append(f"/agenza-{symbol.lower()} {tf}")
        lines.append("")

    lines.extend(
        [
            "📊 Info:",
            "/status       — bot status",
            "/performance  — win rate",
            "/confluence   — last confluence",
            "/orderflow    — live order flow",
            "",
            BRAND,
        ]
    )
    return "\n".join(lines)


def format_status(
    *,
    uptime_seconds: int,
    symbols: Sequence[str],
    timeframes_by_symbol: Mapping[str, Sequence[str]],
    last_signal_ages: Sequence[tuple[str, str, int | None]],
    today_signals: int,
    today_wins: int,
    today_avg_rr: float,
    orderflow_enabled: bool,
    mode: str,
    now_ts: int,
) -> str:
    """Render ``/status``.

    Args:
        uptime_seconds: Bot uptime.
        symbols: Configured symbols.
        timeframes_by_symbol: Timeframes per symbol.
        last_signal_ages: ``(symbol, timeframe, age_seconds_or_None)`` triples in
            display order.
        today_signals: Signals sent today.
        today_wins: Resolved wins today.
        today_avg_rr: Mean reward-to-risk today.
        orderflow_enabled: Whether the order-flow layer is active.
        mode: Confidence mode.
        now_ts: Current Unix seconds.

    Returns:
        The status message.
    """
    lines = [
        "🔍 Bot Status",
        SEPARATOR,
        "Status: ✅ Running",
        f"Uptime: {_format_uptime(uptime_seconds)}",
        "",
        "Symbols:",
    ]
    for index, symbol in enumerate(symbols):
        branch = "└" if index == len(symbols) - 1 else "├"
        header = ", ".join(_user_timeframe(tf) for tf in timeframes_by_symbol.get(symbol, []))
        lines.append(f"{branch} {symbol.upper()}: {header}")

    lines.extend(["", "Last signals:"])
    for index, (symbol, timeframe, age) in enumerate(last_signal_ages):
        branch = "└" if index == len(last_signal_ages) - 1 else "├"
        lines.append(f"{branch} {symbol.upper()} {_user_timeframe(timeframe)}: {_format_age(age)}")

    win_rate = (today_wins / today_signals * 100.0) if today_signals else 0.0
    lines.extend(
        [
            "",
            "Today:",
            f"├ Signals: {today_signals}",
            f"├ Wins:   {today_wins} ({win_rate:.1f}%)",
            f"└ Avg RR: {today_avg_rr:.1f}",
            "",
            f"Order Flow: {'✅' if orderflow_enabled else '❌'} "
            f"{'enabled' if orderflow_enabled else 'disabled'}",
            f"Mode: {mode}",
            f"Time: {_timestamp(now_ts)}",
            BRAND,
        ]
    )
    return "\n".join(lines)


def _format_uptime(seconds: int) -> str:
    """Format uptime as ``4d 12h``, ``3h 5m``, ``45s``."""
    seconds = max(0, int(seconds))
    days, remainder = divmod(seconds, 86_400)
    hours, remainder = divmod(remainder, 3_600)
    minutes, secs = divmod(remainder, 60)
    if days:
        return f"{days}d {hours}h"
    if hours:
        return f"{hours}h {minutes}m"
    if minutes:
        return f"{minutes}m {secs}s"
    return f"{secs}s"


def _format_age(age_seconds: int | None) -> str:
    """Humanise an age, e.g. ``3m ago``, ``2h ago``, or ``never``."""
    if age_seconds is None:
        return "never"
    seconds = max(0, int(age_seconds))
    if seconds < 60:
        return f"{seconds}s ago"
    if seconds < 3_600:
        return f"{seconds // 60}m ago"
    if seconds < 86_400:
        return f"{seconds // 3_600}h ago"
    return f"{seconds // 86_400}d ago"


def format_performance(
    *,
    per_pair: Sequence[tuple[str, str, int, int]],
    confluence_rows: Sequence[tuple[str, int, int]],
    total_signals: int,
    total_wins: int,
    avg_rr: float,
    best: tuple[str, float] | None,
    worst: tuple[str, float] | None,
    period_days: int,
    now_ts: int,
) -> str:
    """Render ``/performance``.

    Args:
        per_pair: ``(symbol, timeframe, signals, wins)`` in display order.
        confluence_rows: ``(label, signals, wins)`` for each confluence group.
        total_signals: Total resolved signals.
        total_wins: Total wins.
        avg_rr: Mean reward-to-risk.
        best: ``(label, pnl)`` for the best result, or ``None``.
        worst: ``(label, pnl)`` for the worst, or ``None``.
        period_days: Window length in days.
        now_ts: Current Unix seconds.

    Returns:
        The performance message.
    """
    lines = ["📊 Performance", SEPARATOR]
    label_width = max(
        (len(f"{s.upper()} {_user_timeframe(tf)}") for s, tf, _, _ in per_pair), default=12
    )
    for symbol, timeframe, signals, wins in per_pair:
        rate = (wins / signals * 100.0) if signals else 0.0
        label = f"{symbol.upper()} {_user_timeframe(timeframe)}"
        plural = "signal" if signals == 1 else "signals"
        win_word = "win" if wins == 1 else "wins"
        lines.append(
            f"{label}:".ljust(label_width + 2)
            + f"{signals} {plural}, {wins} {win_word} ({rate:.1f}%)"
        )

    lines.append("")
    lines.append("Confluence:")
    if confluence_rows:
        for index, (label, signals, wins) in enumerate(confluence_rows):
            branch = "└" if index == len(confluence_rows) - 1 else "├"
            plural = "signal" if signals == 1 else "signals"
            win_word = "win" if wins == 1 else "wins"
            lines.append(f"{branch} {label}: {signals} {plural}, {wins} {win_word}")
    else:
        lines.append("└ none recorded")

    rate = (total_wins / total_signals * 100.0) if total_signals else 0.0
    lines.append("")
    total_plural = "signal" if total_signals == 1 else "signals"
    win_plural = "win" if total_wins == 1 else "wins"
    lines.append(f"Total: {total_signals} {total_plural}, {total_wins} {win_plural} ({rate:.1f}%)")
    lines.append(f"Avg RR: {avg_rr:.1f}")
    if best is not None:
        lines.append(f"Best:  {best[0]} {best[1]:+.1f}%")
    if worst is not None:
        lines.append(f"Worst: {worst[0]} {worst[1]:+.1f}%")
    lines.append("")
    lines.append(f"Period: last {period_days} days")
    lines.append(f"Time: {_timestamp(now_ts)}")
    lines.append(BRAND)
    return "\n".join(lines)
