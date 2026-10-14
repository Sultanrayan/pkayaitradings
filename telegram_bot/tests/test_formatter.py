"""Tests for the exact UI format.

These are not smoke tests. The UI is a contract with the user, so the assertions
here are literal: the separator is twenty box-drawing characters, the label column
is twelve wide, the RR reads ``1:2.0``, and every message ends with the brand line.
A cosmetic regression here is a defect the user would actually see.

The reference signal is built from the supplied sample card — entry 4156.23,
SL 4132.10, TP1 4180.36, TP2 4204.49 — because that is the only ground truth for
the format.
"""

from __future__ import annotations

import dataclasses

import pytest

from telegram_bot import formatter as fmt
from telegram_bot.engine import Signal
from telegram_bot.orderflow import OrderFlowSnapshot
from telegram_bot.tests.conftest import ACTIVE_TS

# --------------------------------------------------------------------------- #
# The reference sample
# --------------------------------------------------------------------------- #

#: The prices from the supplied format sample.
SAMPLE = {
    "entry": 4156.23,
    "sl": 4132.10,
    "tp1": 4180.36,
    "tp2": 4204.49,
}

#: The five layers shown on a card, with the scores the sample displays.
SAMPLE_LAYERS = {
    "trend": 0.85,
    "momentum": 0.72,
    "order_flow": 0.90,
    "volume": 0.68,
    "volatility": 0.55,
}


def sample_signal(
    *,
    action: str = "BUY",
    symbol: str = "XAUUSD",
    timeframe: str = "5m",
    confidence: float = 0.72,
) -> Signal:
    """The reference BUY signal from the supplied format sample."""
    snapshot = OrderFlowSnapshot(
        symbol=symbol,
        timeframe=timeframe,
        delta=1_240.0,
        cvd=3_800.0,
        cvd_trend="rising",
        absorption=None,
        imbalance_ratio=1.4,
        large_order=True,
        large_order_ratio=2.4,
        source="proxy",
        bar_ts=ACTIVE_TS,
    )
    return Signal(
        symbol=symbol,
        timeframe=timeframe,
        bar_ts=ACTIVE_TS,
        action=action,
        entry=SAMPLE["entry"],
        sl=SAMPLE["sl"],
        tp1=SAMPLE["tp1"],
        tp2=SAMPLE["tp2"],
        confidence=confidence,
        layers=dict(SAMPLE_LAYERS),
        order_flow=snapshot,
        reason="sample",
    )


def mirrored_signal(action: str = "SELL") -> Signal:
    """A SELL whose geometry is the mirror of the sample BUY."""
    entry = SAMPLE["entry"]
    risk = abs(SAMPLE["entry"] - SAMPLE["sl"])
    return Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=ACTIVE_TS,
        action=action,
        entry=entry,
        sl=entry + risk,
        tp1=entry - abs(SAMPLE["tp1"] - entry),
        tp2=entry - abs(SAMPLE["tp2"] - entry),
        confidence=0.72,
        layers=dict(SAMPLE_LAYERS),
        order_flow=OrderFlowSnapshot(
            "XAUUSD", "5m", -900.0, -2_100.0, "falling", None, 0.8, False, 1.0, "proxy", ACTIVE_TS
        ),
        reason="sample",
    )


# --------------------------------------------------------------------------- #
# Constants
# --------------------------------------------------------------------------- #


def test_the_brand_line_is_exact() -> None:
    assert fmt.BRAND == "Powered by Pkay AI"


def test_the_separator_is_twenty_box_characters() -> None:
    assert fmt.SEPARATOR == "━" * 20
    assert len(fmt.SEPARATOR) == 20


def test_the_label_column_is_twelve_wide() -> None:
    """`Trend:` is 6 plus 6 spaces; `Order Flow:` is 11 plus 1. Any other width misaligns."""
    assert fmt.LABEL_WIDTH == 12
    assert len("Trend:".ljust(fmt.LABEL_WIDTH)) == 12
    assert len("Order Flow:".ljust(fmt.LABEL_WIDTH)) == 12


# --------------------------------------------------------------------------- #
# progress_bar
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("percent", "filled", "empty"),
    [(0, 0, 10), (100, 10, 0), (50, 5, 5), (85, 8, 2), (95, 10, 0)],
)
def test_progress_bar_cell_counts(percent: int, filled: int, empty: int) -> None:
    bar = fmt.progress_bar(percent)
    assert len(bar) == fmt.BAR_WIDTH == 10
    assert bar.count("█") == filled
    assert bar.count("░") == empty


@pytest.mark.parametrize("percent", [-40, -1, 101, 250, 10_000])
def test_progress_bar_clamps_out_of_range_input(percent: int) -> None:
    """A miscomputed percentage must not produce a bar of the wrong length."""
    assert len(fmt.progress_bar(percent)) == 10


# --------------------------------------------------------------------------- #
# The signal card
# --------------------------------------------------------------------------- #


def test_the_card_matches_the_sample_line_for_line() -> None:
    """The reference card, byte for byte."""
    signal = sample_signal()
    text = fmt.format_signal(signal)

    expected = "\n".join(
        [
            "🟢 BUY — XAUUSD 5M",
            "━━━━━━━━━━━━━━━━━━━━",
            "Entry: 4156.23",
            "SL:    4132.10 (-24.13)",
            "TP1:   4180.36 (+24.13)",
            "TP2:   4204.49 (+48.26)",
            "RR:    1:2.0",
            "",
            "Confidence: 72%",
            # 85% draws 8 cells, not 9: Python rounds 8.5 to even. Every bar
            # starts at column 14 — the two-char branch prefix plus the
            # twelve-wide label column.
            "├ Trend:      ████████░░ 85%",
            "├ Momentum:   ███████░░░ 72%",
            "├ Order Flow: █████████░ 90%",
            "├ Volume:     ███████░░░ 68%",
            "└ Volatility: ██████░░░░ 55%",
            "",
            "Order Flow:",
            "├ Delta:      +1240 (buyers)",
            "├ CVD:        rising",
            "├ Absorption: none",
            "└ Imbalance:  bid 1.4x ask",
            "",
            "Time: 2026-10-02 14:00 UTC",
            "Powered by Pkay AI",
        ]
    )
    assert text == expected


def test_the_buy_card_is_green_and_prefixed_buy() -> None:
    text = fmt.format_signal(sample_signal(action="BUY"))
    assert text.splitlines()[0] == "🟢 BUY — XAUUSD 5M"


def test_the_sell_card_is_red_and_prefixed_sell() -> None:
    text = fmt.format_signal(mirrored_signal("SELL"))
    assert text.splitlines()[0] == "🔴 SELL — XAUUSD 5M"


def test_a_sell_shows_mirrored_offset_signs() -> None:
    """SL up, targets down: the mirror of the BUY, not three negative numbers."""
    text = fmt.format_signal(mirrored_signal("SELL"))
    assert "SL:    4180.36 (+24.13)" in text
    assert "TP1:   4132.10 (-24.13)" in text
    assert "TP2:   4107.97 (-48.26)" in text


def test_the_btc_card_uses_no_thousands_separator() -> None:
    """The format shows `95420.00`, not `95,420.00`."""
    signal = Signal(
        symbol="BTCUSD",
        timeframe="1m",
        bar_ts=ACTIVE_TS,
        action="BUY",
        entry=95_420.00,
        sl=94_990.00,
        tp1=95_850.00,
        tp2=96_280.00,
        confidence=0.68,
        layers={},
        order_flow=OrderFlowSnapshot(
            "BTCUSD", "1m", 0.0, 0.0, "flat", None, 1.0, False, 1.0, "proxy", ACTIVE_TS
        ),
        reason="test",
    )
    text = fmt.format_signal(signal)
    assert "Entry: 95420.00" in text
    assert "," not in text


def test_rr_is_measured_against_tp2() -> None:
    """TP1 sits exactly one risk unit away, so only TP2 can produce `1:2.0`."""
    assert "RR:    1:2.0" in fmt.format_signal(sample_signal())


def test_rr_of_the_second_sample_is_also_two() -> None:
    signal = Signal(
        symbol="BTCUSD",
        timeframe="5m",
        bar_ts=ACTIVE_TS,
        action="BUY",
        entry=100.00,
        sl=86.00,
        tp1=100.00,
        tp2=128.00,
        confidence=0.70,
        layers={},
        order_flow=OrderFlowSnapshot(
            "BTCUSD", "5m", 0.0, 0.0, "flat", None, 1.0, False, 1.0, "proxy", ACTIVE_TS
        ),
        reason="test",
    )
    assert "RR:    1:2.0" in fmt.format_signal(signal)


def test_a_zero_risk_signal_reports_zero_rather_than_infinity() -> None:
    """Entry equal to stop is malformed; claiming infinite reward would mislead."""
    signal = Signal(
        symbol="XAUUSD",
        timeframe="5m",
        bar_ts=ACTIVE_TS,
        action="BUY",
        entry=100.0,
        sl=100.0,
        tp1=110.0,
        tp2=120.0,
        confidence=0.7,
        layers={},
        order_flow=OrderFlowSnapshot(
            "XAUUSD", "5m", 0.0, 0.0, "flat", None, 1.0, False, 1.0, "proxy", ACTIVE_TS
        ),
        reason="test",
    )
    assert "RR:    1:0.0" in fmt.format_signal(signal)


def test_the_timeframe_header_is_upper_case() -> None:
    assert fmt.format_signal(sample_signal(timeframe="1h")).startswith(
        "🟢 BUY — XAUUSD 1H"
    )
    assert fmt.format_signal(sample_signal(timeframe="1m")).startswith(
        "🟢 BUY — XAUUSD 1M"
    )


def test_exactly_five_layers_are_displayed() -> None:
    """Seven layers are weighted; the card shows five, as the required format does."""
    from telegram_bot.layers import DISPLAY_LAYERS, LAYER_NAMES

    assert len(DISPLAY_LAYERS) == 5
    assert set(DISPLAY_LAYERS) < set(LAYER_NAMES)

    text = fmt.format_signal(sample_signal())
    for name in DISPLAY_LAYERS:
        assert name.replace("_", " ").title() in text


def test_the_last_layer_uses_a_terminator_not_a_tee() -> None:
    text = fmt.format_signal(sample_signal())
    assert "└ Volatility:" in text
    assert text.count("└") >= 1


def test_a_missing_layer_renders_as_zero_not_as_an_error() -> None:
    signal = dataclasses.replace(sample_signal(), layers={"trend": 0.5})
    text = fmt.format_signal(signal)
    # `Momentum:` is nine characters, so the label column adds exactly three spaces.
    assert "├ Momentum:   ░░░░░░░░░░ 0%" in text


def test_a_layer_score_above_one_is_capped_in_the_display() -> None:
    """A stray score of 1.4 must not draw a bar wider than ten cells."""
    signal = dataclasses.replace(sample_signal(), layers={"trend": 1.4})
    bar_line = next(
        line for line in fmt.format_signal(signal).splitlines() if "Trend:" in line
    )
    assert bar_line.count("█") + bar_line.count("░") == 10
    assert "100%" in bar_line


def test_every_message_ends_with_the_brand() -> None:
    assert fmt.format_signal(sample_signal()).endswith(fmt.BRAND)


def test_the_card_has_no_trailing_newline() -> None:
    """Telegram would show a stray blank line."""
    assert not fmt.format_signal(sample_signal()).endswith("\n")


def test_layer_bars_align_in_the_same_column() -> None:
    """The bar start column must be identical on all five layer lines."""
    starts = {
        line.index("█")
        for line in fmt.format_signal(sample_signal()).splitlines()
        if "█" in line
    }
    assert len(starts) == 1, f"layer bars misalign: columns {sorted(starts)}"
    # Only the five layer rows carry a bar; the order-flow block does not.
    assert len([ln for ln in fmt.format_signal(sample_signal()).splitlines() if "█" in ln]) == 5


def test_levels_can_be_overridden_for_confluence_cards() -> None:
    """Confluence publishes blended levels; the card must accept them."""
    text = fmt.format_signal(
        sample_signal(),
        levels={"entry": 100.0, "sl": 90.0, "tp1": 110.0, "tp2": 120.0},
    )
    assert "Entry: 100.00" in text
    assert "RR:    1:2.0" in text


# --------------------------------------------------------------------------- #
# The order-flow block
# --------------------------------------------------------------------------- #


def test_a_zero_delta_is_reported_as_flat() -> None:
    signal = Signal(
        **{
            **sample_signal().__dict__,
            "order_flow": OrderFlowSnapshot(
                "XAUUSD", "5m", 0.0, 0.0, "flat", None, 1.0, False, 1.0, "proxy", ACTIVE_TS
            ),
        }
    )
    text = fmt.format_signal(signal)
    assert "+0 (flat)" in text
    assert "Imbalance:  balanced" in text


def test_seller_pressure_is_inverted_into_an_ask_ratio() -> None:
    """The ratio is bid-side, so a sell must invert it rather than print `bid 0.8x`."""
    text = fmt.format_signal(mirrored_signal("SELL"))
    assert "Imbalance:  ask 1.2x bid" in text


def test_an_absorbing_level_is_shown_with_its_price() -> None:
    signal = Signal(
        **{
            **sample_signal().__dict__,
            "order_flow": OrderFlowSnapshot(
                "XAUUSD",
                "5m",
                900.0,
                2_000.0,
                "rising",
                "support @ 4150.00",
                1.5,
                True,
                2.0,
                "proxy",
                ACTIVE_TS,
            ),
        }
    )
    assert "Absorption: support @ 4150.00" in fmt.format_signal(signal)


def test_an_infinite_imbalance_does_not_print_infinity() -> None:
    signal = Signal(
        **{
            **sample_signal().__dict__,
            "order_flow": OrderFlowSnapshot(
                "XAUUSD",
                "5m",
                500.0,
                900.0,
                "rising",
                None,
                float("inf"),
                False,
                1.0,
                "proxy",
                ACTIVE_TS,
            ),
        }
    )
    text = fmt.format_signal(signal)
    assert "Imbalance:  bid" in text
    assert "inf" not in text


@pytest.mark.parametrize("ratio", [0.0, 1.0, float("inf"), -1.0, 0.5, 2.0, 1e9])
@pytest.mark.parametrize("delta", [-500.0, 0.0, 500.0])
def test_imbalance_rendering_survives_every_degenerate_value(ratio: float, delta: float) -> None:
    """Regression: a one-sided book reaches a ZeroDivisionError on a live card.

    ``ratio == 0.0`` means no ask at all, so inverting it divides by zero. The
    old guard tested only ``1.0`` and ``inf``, so ``0.0`` passed straight through
    to the division. Every combination is asserted rather than the two that were
    already known.
    """
    snapshot = OrderFlowSnapshot(
        "XAUUSD", "5m", delta, 100.0, "rising", None, ratio, False, 1.0, "proxy", ACTIVE_TS
    )
    text = fmt._imbalance_text(delta, ratio)
    assert text
    assert "inf" not in text.lower()
    assert "nan" not in text.lower()

    # And the full card must render rather than raise.
    signal = Signal(**{**sample_signal().__dict__, "order_flow": snapshot})
    assert fmt.format_signal(signal)


def test_a_zero_imbalance_ratio_is_not_inverted() -> None:
    """``ratio`` is bid/ask, so zero means the bid side is empty: an ask-only book.

    Reading it the intuitive way round ("no ask, therefore a pure bid") would
    invert the meaning of the most extreme value the field can take.
    """
    assert fmt._imbalance_text(-500.0, 0.0) == "ask"
    assert fmt._imbalance_text(500.0, 0.0) == "ask"


def test_the_proxy_source_is_never_presented_as_measured_flow() -> None:
    """A consumer must not be able to mistake the estimate for a tape reading."""
    from telegram_bot.orderflow import SOURCE

    assert SOURCE == "proxy"
    snapshot = OrderFlowSnapshot(
        "XAUUSD", "5m", 1.0, 1.0, "rising", None, 1.0, False, 1.0, "proxy", ACTIVE_TS
    )
    assert snapshot.source == SOURCE
    assert snapshot.to_dict()["source"] == "proxy"


# --------------------------------------------------------------------------- #
# Timestamps
# --------------------------------------------------------------------------- #


def test_timestamps_are_utc_and_readable() -> None:
    assert fmt._timestamp(ACTIVE_TS) == "2026-10-02 14:00 UTC"


# --------------------------------------------------------------------------- #
# The analysis block
# --------------------------------------------------------------------------- #


def test_the_analysis_block_reports_layers_with_detail() -> None:
    from telegram_bot.layers import LayerResult

    layers = {
        "trend": LayerResult(name="trend", score=0.8, evaluable=True, detail="bullish"),
        "momentum": LayerResult(name="momentum", score=-0.3, evaluable=True, detail="RSI 68"),
    }
    text = fmt.format_analysis(
        symbol="XAUUSD", timeframe="5m", layers=layers, signal=None, reason="0.60 threshold", bar_ts=ACTIVE_TS
    )
    assert text.startswith("🔍 Analysis — XAUUSD 5M")
    assert "Trend:" in text and "bullish" in text
    assert "RSI 68" in text


def test_an_unevaluable_layer_shows_na_not_a_bare_zero() -> None:
    from telegram_bot.layers import LayerResult

    text = fmt.format_analysis(
        symbol="XAUUSD",
        timeframe="5m",
        layers={
            "volume": LayerResult(
                name="volume", score=0.0, evaluable=False, detail="no volume"
            )
        },
        signal=None,
        reason="0.60 threshold",
        bar_ts=ACTIVE_TS,
    )
    assert "n/a" in text
    assert "no volume" not in text


def test_the_analysis_block_says_no_signal_and_why() -> None:
    text = fmt.format_analysis(
        symbol="XAUUSD",
        timeframe="5m",
        layers={},
        signal=None,
        reason="confidence 0.41 below 0.60 threshold",
        bar_ts=ACTIVE_TS,
    )
    assert "Signal: ❌ No signal" in text
    assert "Reason: confidence 0.41 below 0.60 threshold" in text
    assert text.endswith(fmt.BRAND)


def test_the_analysis_block_shows_a_fired_signal() -> None:
    text = fmt.format_analysis(
        symbol="XAUUSD",
        timeframe="5m",
        layers={},
        signal=sample_signal(),
        reason="all layers aligned",
        bar_ts=ACTIVE_TS,
    )
    assert "Signal: ✅ BUY" in text
    assert "Confidence: 72%" in text
    assert "🟢 BUY — XAUUSD 5M" in text, "the card must follow the analysis block"


# --------------------------------------------------------------------------- #
# Confluence
# --------------------------------------------------------------------------- #


def _confluence():
    from telegram_bot.confluence import Confluence
    from telegram_bot.tests.test_confluence import _row

    members = (_row(timeframe="5m", row_id=1), _row(timeframe="15m", row_id=2))
    return Confluence(
        symbol="XAUUSD",
        action="BUY",
        timeframes=("5m", "15m"),
        confidence=0.71,
        representative=members[0],
        members=members,
    )


def test_the_confluence_card_names_every_timeframe() -> None:
    text = fmt.format_confluence(_confluence())
    assert text.startswith("🔥 Last Confluence Signal")
    assert "Timeframes: 5mn + 15mn" in text
    assert "CONFLUENCE BUY — XAUUSD" in text


def test_the_confluence_card_shows_the_weighted_confidence() -> None:
    text = fmt.format_confluence(_confluence())
    assert "Confidence: 71% (weighted across 2 TFs)" in text


def test_the_confluence_card_ends_with_the_brand() -> None:
    assert fmt.format_confluence(_confluence()).endswith(fmt.BRAND)


def test_the_empty_confluence_message_explains_what_is_missing() -> None:
    text = fmt.format_no_confluence()
    assert "No confluence recorded yet." in text
    assert "two or more timeframes" in text
    assert text.endswith(fmt.BRAND)


# --------------------------------------------------------------------------- #
# /start and /help
# --------------------------------------------------------------------------- #


def test_start_lists_both_symbols_with_all_four_timeframes() -> None:
    text = fmt.format_start(["XAUUSD", "BTCUSD"], ["1m", "5m", "15m", "1h"])
    assert "XAUUSD: 1mn, 5mn, 15mn, 1h" in text
    assert "BTCUSD: 1mn, 5mn, 15mn, 1h" in text


def test_start_lists_every_agenza_variant() -> None:
    text = fmt.format_start(["XAUUSD", "BTCUSD"], ["1m", "5m", "15m", "1h"])
    for symbol in ("xauusd", "btcusd"):
        for tf in ("1mn", "5mn", "15mn", "1h"):
            assert f"/agenza-{symbol} {tf}" in text


def test_start_uses_a_terminator_on_the_last_symbol() -> None:
    text = fmt.format_start(["XAUUSD", "BTCUSD"], ["1m"])
    assert "├ XAUUSD" in text
    assert "└ BTCUSD" in text


def test_help_groups_commands_by_instrument() -> None:
    text = fmt.format_help(["XAUUSD", "BTCUSD"])
    assert "Gold (XAUUSD):" in text
    assert "Bitcoin (BTCUSD):" in text
    assert "📊 Info:" in text


def test_help_documents_every_info_command() -> None:
    text = fmt.format_help(["XAUUSD"])
    for command in ("/status", "/performance", "/confluence", "/orderflow"):
        assert command in text


# --------------------------------------------------------------------------- #
# /status
# --------------------------------------------------------------------------- #


def _status(**overrides):
    args = {
        "uptime_seconds": 4 * 86_400 + 12 * 3_600,
        "symbols": ["XAUUSD", "BTCUSD"],
        "timeframes_by_symbol": {
            "XAUUSD": ["1m", "5m", "15m", "1h"],
            "BTCUSD": ["1m", "5m", "15m", "1h"],
        },
        "last_signal_ages": [("XAUUSD", "5m", 180), ("BTCUSD", "1h", None)],
        "today_signals": 8,
        "today_wins": 5,
        "today_avg_rr": 1.9,
        "orderflow_enabled": True,
        "mode": "balanced",
        "now_ts": ACTIVE_TS,
    }
    args.update(overrides)
    return fmt.format_status(**args)


def test_status_shows_uptime_symbols_and_todays_numbers() -> None:
    text = _status()
    assert "Status: ✅ Running" in text
    assert "Uptime: 4d 12h" in text
    assert "XAUUSD: 1mn, 5mn, 15mn, 1h" in text
    assert "Signals: 8" in text
    assert "Wins:   5 (62.5%)" in text
    assert "Avg RR: 1.9" in text


def test_status_shows_never_for_a_pair_with_no_signal() -> None:
    assert "BTCUSD 1h: never" in _status()


def test_status_does_not_divide_by_zero_on_a_day_with_no_signals() -> None:
    text = _status(today_signals=0, today_wins=0)
    assert "Signals: 0" in text
    assert "Wins:   0 (0.0%)" in text


def test_status_reports_order_flow_state() -> None:
    assert "Order Flow: ✅ enabled" in _status(orderflow_enabled=True)
    assert "Order Flow: ❌ disabled" in _status(orderflow_enabled=False)


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [(0, "0s"), (45, "45s"), (60, "1m 0s"), (185, "3m 5s"),
     (3_600, "1h 0m"), (11_100, "3h 5m"), (86_400, "1d 0h"), (410_400, "4d 18h")],
)
def test_uptime_formatting(seconds: int, expected: str) -> None:
    assert fmt._format_uptime(seconds) == expected


@pytest.mark.parametrize(
    ("age", "expected"),
    [(None, "never"), (0, "0s ago"), (59, "59s ago"), (60, "1m ago"),
     (3_599, "59m ago"), (7_200, "2h ago"), (172_800, "2d ago")],
)
def test_age_formatting(age: int | None, expected: str) -> None:
    assert fmt._format_age(age) == expected


def test_a_negative_age_does_not_render_a_negative_time() -> None:
    assert fmt._format_age(-50) == "0s ago"


# --------------------------------------------------------------------------- #
# /performance
# --------------------------------------------------------------------------- #


def _performance(**overrides):
    args = {
        "per_pair": [("XAUUSD", "5m", 10, 6), ("BTCUSD", "15m", 4, 1)],
        "confluence_rows": [("5mn + 15mn", 3, 2)],
        "total_signals": 14,
        "total_wins": 7,
        "avg_rr": 1.8,
        "best": ("XAUUSD 5m", 12.4),
        "worst": ("BTCUSD 15m", -8.1),
        "period_days": 7,
        "now_ts": ACTIVE_TS,
    }
    args.update(overrides)
    return fmt.format_performance(**args)


def test_performance_shows_the_overall_totals() -> None:
    text = _performance()
    assert "Total: 14 signals, 7 wins (50.0%)" in text
    assert "Avg RR: 1.8" in text


def test_performance_shows_each_pair() -> None:
    text = _performance()
    # Labels are padded to the widest pair, so the counts line up in one column.
    assert "XAUUSD 5mn:  10 signals, 6 wins (60.0%)" in text
    assert "BTCUSD 15mn: 4 signals, 1 win (25.0%)" in text


def test_performance_shows_the_best_and_worst_with_signs() -> None:
    text = _performance()
    assert "Best:  XAUUSD 5m +12.4%" in text
    assert "Worst: BTCUSD 15m -8.1%" in text


def test_performance_omits_best_and_worst_when_there_is_none() -> None:
    text = _performance(best=None, worst=None)
    assert "Best:" not in text
    assert "Worst:" not in text


def test_performance_reports_the_window() -> None:
    assert "Period: last 7 days" in _performance()


def test_performance_with_no_results_does_not_divide_by_zero() -> None:
    text = _performance(
        per_pair=[], confluence_rows=[], total_signals=0, total_wins=0, avg_rr=0.0
    )
    assert "Total: 0 signals, 0 wins (0.0%)" in text
    assert "└ none recorded" in text


def test_performance_uses_singular_wording_for_one_signal() -> None:
    text = _performance(per_pair=[("XAUUSD", "5m", 1, 1)], total_signals=1, total_wins=1)
    assert "1 signal, 1 win (100.0%)" in text


# --------------------------------------------------------------------------- #
# /orderflow
# --------------------------------------------------------------------------- #


def test_orderflow_lists_one_block_per_symbol() -> None:
    snapshots = [
        (
            "XAUUSD",
            OrderFlowSnapshot(
                "XAUUSD", "5m", 1_240.0, 3_800.0, "rising", None, 1.4, True, 2.0, "proxy", ACTIVE_TS
            ),
        ),
        (
            "BTCUSD",
            OrderFlowSnapshot(
                "BTCUSD", "5m", -300.0, -900.0, "falling", "resistance @ 95000.00", 0.75, False, 1.0, "proxy", ACTIVE_TS
            ),
        ),
    ]
    text = fmt.format_orderflow(snapshots)
    assert "⚡ Order Flow — Live" in text
    assert "XAUUSD:" in text
    assert "BTCUSD:" in text
    assert "+1240 (buyers)" in text
    assert "-300 (sellers)" in text
    assert "resistance @ 95000.00" in text
    assert text.endswith(fmt.BRAND)


# --------------------------------------------------------------------------- #
# Shared invariants
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    "render",
    [
        lambda: fmt.format_signal(sample_signal()),
        lambda: fmt.format_signal(mirrored_signal("SELL")),
        lambda: fmt.format_no_confluence(),
        lambda: fmt.format_start(["XAUUSD"], ["1m"]),
        lambda: fmt.format_help(["XAUUSD"]),
        lambda: _status(),
        lambda: _performance(),
    ],
)
def test_every_message_ends_with_exactly_one_brand_line(render) -> None:
    text = render()
    assert text.count(fmt.BRAND) == 1
    assert text.endswith(fmt.BRAND)


@pytest.mark.parametrize(
    "render",
    [
        lambda: fmt.format_signal(sample_signal()),
        lambda: fmt.format_no_confluence(),
        lambda: fmt.format_start(["XAUUSD"], ["1m"]),
        lambda: fmt.format_help(["XAUUSD"]),
        lambda: _status(),
        lambda: _performance(),
    ],
)
def test_no_message_has_a_trailing_blank_line(render) -> None:
    assert not render().endswith("\n")


@pytest.mark.parametrize(
    "render",
    [
        lambda: fmt.format_signal(sample_signal()),
        lambda: fmt.format_no_confluence(),
        lambda: _status(),
        lambda: _performance(),
    ],
)
def test_every_message_carries_the_separator(render) -> None:
    assert fmt.SEPARATOR in render()
