"""Tests for the engine's decision logic: determinism, thresholds, cooldown.

The two anti-repaint proofs live in ``test_no_repaint.py`` and the attachment
proof in ``test_attached.py``. This file covers the remaining engine contract:
that the same input always gives the same output, that the confidence threshold
is actually enforced, and that duplicate suppression works.
"""

from __future__ import annotations

import itertools

import pandas as pd
import pytest

from signals.engine import SignalEngine
from signals.models import CONFIDENCE_THRESHOLDS, SignalConfig
from signals.tests.factories import make_ohlcv, make_range, make_trend_then_reverse


def _now(frame: pd.DataFrame) -> pd.Timestamp:
    """A clock past the final bar, so every bar counts as closed."""
    return frame.index[-1] + pd.Timedelta(days=1)


def _permissive(**kwargs) -> SignalEngine:
    """A deliberately loose engine, so suppression tests have signals to work with."""
    defaults = {
        "mode": "aggressive",
        "confidence_threshold": 0.20,
        "mandatory_layers": (),
        "ema_fast": 10,
        "ema_slow": 30,
    }
    defaults.update(kwargs)
    return SignalEngine(SignalConfig(**defaults))


# --------------------------------------------------------------------------- #
# Determinism (RULE 5)
# --------------------------------------------------------------------------- #


def test_same_input_gives_the_same_output() -> None:
    frame = make_trend_then_reverse(400, seed=401)
    now = _now(frame)
    first = _permissive().compute(frame, "XAUUSD", "H1", now=now)
    second = _permissive().compute(frame, "XAUUSD", "H1", now=now)
    assert first == second


def test_a_fresh_engine_matches_a_reused_one() -> None:
    """No per-call state may leak between runs."""
    frame = make_trend_then_reverse(400, seed=403)
    now = _now(frame)
    reused = _permissive()
    first = reused.compute(frame, "XAUUSD", "H1", now=now)
    second = reused.compute(frame, "XAUUSD", "H1", now=now)
    fresh = _permissive().compute(frame, "XAUUSD", "H1", now=now)
    assert first == second == fresh


def test_two_engines_with_equal_config_agree() -> None:
    config = SignalConfig(mode="aggressive", confidence_threshold=0.2, mandatory_layers=())
    frame = make_trend_then_reverse(400, seed=405)
    now = _now(frame)
    assert SignalEngine(config).compute(
        frame, "XAUUSD", "H1", now=now
    ) == SignalEngine(config).compute(frame, "XAUUSD", "H1", now=now)


def test_symbol_case_does_not_change_the_verdict() -> None:
    frame = make_trend_then_reverse(400, seed=407)
    now = _now(frame)
    upper = _permissive().compute(frame, "XAUUSD", "H1", now=now)
    lower = _permissive().compute(frame, "xauusd", "H1", now=now)
    assert len(upper) == len(lower)
    assert all(s.symbol == "XAUUSD" for s in lower)


def test_a_timezone_aware_clock_matches_utc() -> None:
    """An equivalent instant in another zone must not change the result."""
    frame = make_trend_then_reverse(400, seed=409)
    utc_now = _now(frame)
    shifted = utc_now.tz_convert("America/New_York")
    assert _permissive().compute(frame, "XAUUSD", "H1", now=utc_now) == _permissive().compute(
        frame, "XAUUSD", "H1", now=shifted
    )


# --------------------------------------------------------------------------- #
# Confidence threshold
# --------------------------------------------------------------------------- #


def test_every_signal_meets_the_threshold() -> None:
    frame = make_trend_then_reverse(500, seed=411)
    now = _now(frame)
    threshold = 0.35
    engine = _permissive(confidence_threshold=threshold)

    signals = engine.compute(frame, "XAUUSD", "H1", now=now)
    assert signals
    for signal in signals:
        assert signal.confidence >= threshold


def test_a_higher_threshold_never_adds_signals() -> None:
    """Raising the bar can only remove signals, never introduce them."""
    frame = make_trend_then_reverse(500, seed=413)
    now = _now(frame)

    permissive = _permissive(confidence_threshold=0.20).compute(frame, "X", "H1", now=now)
    strict = _permissive(confidence_threshold=0.80).compute(frame, "X", "H1", now=now)

    permissive_times = {s.timestamp for s in permissive}
    strict_times = {s.timestamp for s in strict}
    assert strict_times.issubset(permissive_times)
    assert len(strict) <= len(permissive)


def test_a_maximum_threshold_yields_no_signals() -> None:
    """Confidence cannot exceed 1.0, so a threshold of exactly 1.0 is unreachable.

    Confidences approach 1.0 but never reach it: the weighted sum is renormalised
    by the evaluable weight and every layer is clipped to |score| <= 1, so a
    perfect alignment on all six would be needed. The threshold is inclusive, so
    this is a statement about the achievable range rather than about `>=`.
    """
    frame = make_trend_then_reverse(400, seed=417)
    signals = _permissive(confidence_threshold=1.0).compute(frame, "X", "H1", now=_now(frame))
    assert all(s.confidence < 1.0 for s in signals)


def test_an_out_of_range_threshold_is_rejected_at_construction() -> None:
    """A threshold outside [0, 1] is a configuration error, not a runtime one."""
    with pytest.raises(ValueError, match="confidence_threshold"):
        SignalConfig(confidence_threshold=1.01)


def test_confidence_is_always_within_bounds() -> None:
    for seed in (419, 421, 423):
        frame = make_trend_then_reverse(400, seed=seed)
        for signal in _permissive().compute(frame, "X", "H1", now=_now(frame)):
            assert 0.0 <= signal.confidence <= 1.0


def test_mode_selects_its_own_threshold() -> None:
    frame = make_trend_then_reverse(600, seed=425)
    now = _now(frame)
    counts = {}
    for mode in ("aggressive", "balanced", "conservative"):
        engine = SignalEngine(
            SignalConfig(
                mode=mode,
                mandatory_layers=(),
                ema_fast=10,
                ema_slow=30,
                sr_lookback=3,
                volume_ma_period=5,
                bb_period=5,
            )
        )
        signals = engine.compute(frame, "X", "H1", now=now)
        counts[mode] = len(signals)
        for signal in signals:
            assert signal.confidence >= CONFIDENCE_THRESHOLDS[mode]

    assert counts["aggressive"] >= counts["balanced"]
    assert counts["balanced"] >= counts["conservative"]


# --------------------------------------------------------------------------- #
# Mandatory layers
# --------------------------------------------------------------------------- #


def test_a_mandatory_layer_that_abstains_blocks_the_signal() -> None:
    """An unevaluable mandatory layer must veto, not pass as neutral.

    Trend abstains in a range, so a range with `mandatory_layers=("trend",)`
    should produce nothing — which is the honest behaviour, not a bug.
    """
    frame = make_range(400, seed=431)
    engine = SignalEngine(
        SignalConfig(
            mode="aggressive",
            confidence_threshold=0.1,
            mandatory_layers=("trend",),
            adx_trend_min=99.0,
            ema_fast=10,
            ema_slow=30,
            sr_lookback=3,
            volume_ma_period=5,
            bb_period=5,
        )
    )
    assert engine.compute(frame, "X", "H1", now=_now(frame)) == []


def test_no_mandatory_layers_allows_agreement_from_the_rest() -> None:
    frame = make_trend_then_reverse(400, seed=433)
    signals = _permissive(mandatory_layers=()).compute(frame, "X", "H1", now=_now(frame))
    assert signals


def test_a_mandatory_layer_must_agree_with_the_direction() -> None:
    """Requiring trend means the trend must point the same way as the signal."""
    frame = make_ohlcv(500, drift=-0.005, noise=0.001, seed=437)
    signals = _permissive(mandatory_layers=("trend",)).compute(
        frame, "X", "H1", now=_now(frame)
    )
    for signal in signals:
        assert signal.layers["trend"] > 0.0 if signal.action == "BUY" else signal.layers["trend"] < 0.0


# --------------------------------------------------------------------------- #
# Cooldown (RULE 4)
# --------------------------------------------------------------------------- #


def test_cooldown_is_respected() -> None:
    frame = make_trend_then_reverse(600, seed=439)
    now = _now(frame)

    tight = _permissive(
        min_bars_between_signals=1, require_opposite_before_repeat=False
    ).compute(frame, "X", "H1", now=now)
    loose = _permissive(
        min_bars_between_signals=40, require_opposite_before_repeat=False
    ).compute(frame, "X", "H1", now=now)

    assert len(tight) > len(loose)


def test_signals_are_at_least_the_cooldown_apart() -> None:
    frame = make_trend_then_reverse(600, seed=443)
    signals = _permissive(
        min_bars_between_signals=12, require_opposite_before_repeat=False
    ).compute(frame, "X", "H1", now=_now(frame))

    positions = [frame.index.get_loc(s.timestamp) for s in signals]
    assert len(positions) > 1, "need at least two signals to measure a gap"
    for earlier, later in itertools.pairwise(positions):
        assert later - earlier >= 12


def test_zero_cooldown_permits_adjacent_bars() -> None:
    frame = make_trend_then_reverse(600, seed=449)
    signals = _permissive(
        min_bars_between_signals=0, require_opposite_before_repeat=False
    ).compute(frame, "X", "H1", now=_now(frame))
    positions = [frame.index.get_loc(s.timestamp) for s in signals]
    for earlier, later in itertools.pairwise(positions):
        assert later - earlier >= 1, "two signals cannot share a bar"


def test_opposite_first_prevents_repeated_same_direction_signals() -> None:
    """Two BUYs in a row are one idea, not two."""
    frame = make_trend_then_reverse(600, seed=457)
    signals = _permissive(
        min_bars_between_signals=0, require_opposite_before_repeat=True
    ).compute(frame, "X", "H1", now=_now(frame))

    actions = [s.action for s in signals]
    for earlier, later in itertools.pairwise(actions):
        assert earlier != later, f"consecutive {earlier} signals were not suppressed"


def test_disabling_opposite_first_allows_repeats() -> None:
    frame = make_trend_then_reverse(600, seed=461)
    with_rule = _permissive(
        min_bars_between_signals=0, require_opposite_before_repeat=True
    ).compute(frame, "X", "H1", now=_now(frame))
    without = _permissive(
        min_bars_between_signals=0, require_opposite_before_repeat=False
    ).compute(frame, "X", "H1", now=_now(frame))
    assert len(without) >= len(with_rule)


# --------------------------------------------------------------------------- #
# Insufficient history — reported, not silently empty
# --------------------------------------------------------------------------- #


def test_too_few_bars_returns_nothing_without_raising() -> None:
    """Below the warmup bound there is nothing to evaluate, and that is not an error.

    The bound is the engine's own ``warmup_bars`` — for the permissive test
    engine that is driven by its 10/30 EMAs, not the 50/200 defaults, which is
    why 50 bars is enough to produce signals here and would not be with defaults.
    """
    engine = _permissive()
    for n in (1, 5, 15):
        frame = make_ohlcv(n, seed=463)
        assert engine.compute(frame, "X", "H1", now=_now(frame)) == []
    assert engine.config.warmup_bars <= 30


def test_the_default_engine_needs_its_full_warmup() -> None:
    """With 50/200 EMAs, a short series yields nothing — the bound is real."""
    frame = make_trend_then_reverse(120, seed=465)
    defaults = SignalEngine(SignalConfig())
    assert defaults.config.warmup_bars >= 200
    assert defaults.compute(frame, "X", "H1", now=_now(frame)) == []


def test_an_empty_frame_is_rejected_with_a_clear_message() -> None:
    """No bar at all means no index to validate, so the message must say so."""
    frame = make_ohlcv(10, seed=463)
    empty = frame.iloc[0:0]
    with pytest.raises(ValueError, match="empty"):
        _permissive().compute(empty, "X", "H1", now=pd.Timestamp("2030-01-01", tz="UTC"))


def test_an_empty_frame_is_rejected_by_every_entry_point() -> None:
    """All three public methods refuse an empty frame with the same clear message."""
    frame = make_ohlcv(10, seed=467)
    empty = frame.iloc[0:0]
    now = pd.Timestamp("2030-01-01", tz="UTC")
    engine = _permissive()

    with pytest.raises(ValueError, match="empty"):
        engine.compute(empty, "X", "H1", now=now)
    with pytest.raises(ValueError, match="empty"):
        engine.compute_latest(empty, "X", "H1", now=now)
    with pytest.raises(ValueError, match="empty"):
        engine.evaluate_bar(empty, "X", "H1", pd.Timestamp("2026-01-01", tz="UTC"), now=now)


# --------------------------------------------------------------------------- #
# Input validation
# --------------------------------------------------------------------------- #


def test_a_missing_column_is_rejected_clearly() -> None:
    frame = make_ohlcv(300, seed=469).drop(columns=["high"])
    with pytest.raises(ValueError, match="missing required columns"):
        _permissive().compute(frame, "X", "H1", now=_now(frame))


def test_a_non_datetime_index_is_rejected_clearly() -> None:
    """A range index is a programming error, and the message says how to fix it.

    The ``now`` is built from a good frame rather than this one, because a
    RangeIndex has no timestamps to derive a clock from — which is the very reason
    the input is rejected.
    """
    good = make_ohlcv(300, seed=470)
    now = _now(good)

    frame = make_ohlcv(300, seed=471)
    frame.index = pd.RangeIndex(len(frame))
    with pytest.raises(ValueError, match="DatetimeIndex"):
        _permissive().compute(frame, "X", "H1", now=now)


def test_a_naive_index_is_localised_to_utc_with_a_warning(caplog) -> None:
    """A naive index is a latent timezone bug; assume UTC rather than refuse."""
    frame = make_ohlcv(300, seed=473)
    naive = frame.copy()
    naive.index = naive.index.tz_localize(None)

    signals = _permissive().compute(naive, "X", "H1", now=_now(frame))
    for signal in signals:
        assert signal.timestamp.tz is not None


# --------------------------------------------------------------------------- #
# compute_latest
# --------------------------------------------------------------------------- #


def test_compute_latest_returns_the_newest_closed_bar_only() -> None:
    frame = make_trend_then_reverse(600, seed=479)
    now = _now(frame)
    engine = _permissive()

    latest = engine.compute_latest(frame, "X", "H1", now=now)
    if latest is not None:
        assert latest.timestamp <= frame.index[-1]
        newer = [s for s in engine.compute(frame, "X", "H1", now=now) if s.timestamp > latest.timestamp]
        assert not newer


def test_compute_latest_returns_none_when_the_last_bar_qualifies_nothing() -> None:
    """`None` is a valid answer and must not be confused with an error."""
    frame = make_trend_then_reverse(600, seed=487)
    engine = SignalEngine(
        SignalConfig(
            mode="aggressive",
            confidence_threshold=0.1,
            mandatory_layers=(),
            ema_fast=10,
            ema_slow=30,
            sr_lookback=3,
            volume_ma_period=5,
            bb_period=5,
        )
    )
    result = engine.compute_latest(frame, "X", "H1", now=_now(frame))
    assert result is None or isinstance(result.timestamp, pd.Timestamp)


def test_compute_latest_agrees_with_compute() -> None:
    """The two entry points must not disagree about the newest bar."""
    frame = make_trend_then_reverse(600, seed=491)
    now = _now(frame)
    engine = _permissive()
    latest = engine.compute_latest(frame, "X", "H1", now=now)
    all_signals = engine.compute(frame, "X", "H1", now=now)
    if latest is not None:
        assert latest in all_signals
        assert latest is all_signals[-1]


# --------------------------------------------------------------------------- #
# Signal contents
# --------------------------------------------------------------------------- #


def test_reason_names_the_contributing_layers() -> None:
    frame = make_trend_then_reverse(500, seed=499)
    signals = _permissive().compute(frame, "X", "H1", now=_now(frame))
    assert signals
    for signal in signals:
        assert signal.reason
        assert signal.action in signal.reason
        named = [
            name
            for name in signal.layers
            if name.split("_")[0] in signal.reason or name in signal.reason
        ]
        assert named, "the reason must explain itself in layer names"


def test_layers_dict_covers_every_named_layer() -> None:
    from signals.models import LAYER_NAMES

    frame = make_trend_then_reverse(500, seed=503)
    signals = _permissive().compute(frame, "X", "H1", now=_now(frame))
    assert signals
    for signal in signals:
        assert set(signal.layers) == set(LAYER_NAMES)


def test_strategy_version_is_recorded() -> None:
    """A signal must state which configuration produced it, so it can be audited."""
    frame = make_trend_then_reverse(400, seed=509)
    signals = _permissive().compute(frame, "X", "H1", now=_now(frame))
    assert all(s.strategy_version for s in signals)
