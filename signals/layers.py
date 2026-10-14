"""Six confirmation layers.

Each layer answers one question about a single bar and returns a
:class:`~signals.models.LayerScore` with a directional score in ``[-1, 1]``.
Positive favours BUY, negative favours SELL, zero means no opinion.

Two design rules run through all six:

**A layer that cannot be evaluated says so.** During indicator warmup the inputs
are NaN. Rather than returning ``0.0`` and being counted as a neutral vote, a
layer returns ``evaluable=False`` and is excluded from the confidence sum. This
is what keeps RULE 3 honest: the spec forbids over-filtering, but a layer voting
"neutral" because it has no data is a fabricated vote, and a mandatory layer
failing that way must block the signal rather than pass it.

**Direction comes from the current bar, comparison from the previous one.** A
cross is "the current bar is on the other side of the threshold from the previous
bar", which reads bar ``i - 1`` — never bar ``i + 1``.

Every function is pure: same frame in, same scores out. No clock, no state, no
I/O. The engine is therefore deterministic by construction (RULE 5).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from signals.indicators import (
    adx,
    atr,
    bollinger_bands,
    confirmed_swing_highs,
    confirmed_swing_lows,
    ema,
    macd,
    rsi,
    stochastic,
    supertrend,
)
from signals.indicators import (
    bb_width as _bb_width,
)
from signals.indicators import (
    volume_ma as _volume_ma,
)
from signals.models import SignalConfig

__all__ = [
    "build_features",
    "score_all",
    "score_momentum",
    "score_price_action",
    "score_support_resistance",
    "score_trend",
    "score_volatility",
    "score_volume",
]

#: Columns :func:`build_features` appends to the OHLCV frame. Listed so callers
#: can assert on the frame's shape without re-deriving the list.
FEATURE_COLUMNS: tuple[str, ...] = (
    "ema_fast",
    "ema_slow",
    "adx",
    "atr",
    "rsi",
    "macd",
    "macd_signal",
    "macd_hist",
    "stoch_k",
    "stoch_d",
    "supertrend_line",
    "supertrend_dir",
    "bb_width",
    "volume_ma",
    "swing_high_pos",
    "swing_high_confirm",
    "swing_high_price",
    "swing_low_pos",
    "swing_low_confirm",
    "swing_low_price",
)


def build_features(frame: pd.DataFrame, config: SignalConfig) -> pd.DataFrame:
    """Compute every indicator once, in a single vectorised pass.

    Why this exists
    ---------------
    Scoring each bar independently would recompute the EMA-200 for every one of
    400 bars — O(n²) work, and minutes of wall time for a single symbol. Computing
    once and reading by position is O(n).

    Why it is not a shortcut that breaks the no-repaint guarantee
    -----------------------------------------------------------
    Every indicator this module uses is *streaming*: its value at bar ``i`` is a
    function of bars ``0..i`` only. That property is asserted directly in
    ``tests/test_indicators.py::test_indicators_have_no_lookahead``, which
    recomputes each indicator on truncated frames and compares the shared prefix.
    Because a streaming indicator's value does not depend on later bars, computing
    it over the full frame and reading position ``i`` gives byte-identical results
    to computing it over ``frame.iloc[:i+1]``.

    The one exception is the swing pivots, which are inherently defined by
    following bars. They are handled by storing the **confirmation** position and
    requiring consumers to filter on it — see :func:`score_support_resistance`.

    Args:
        frame: OHLCV frame indexed by bar close time in UTC.
        config: Active configuration, supplying every lookback.

    Returns:
        A copy of ``frame`` with the :data:`FEATURE_COLUMNS` appended. The input
        is never mutated.
    """
    out = frame.copy()
    close = out["close"]

    out["ema_fast"] = ema(close, config.ema_fast)
    out["ema_slow"] = ema(close, config.ema_slow)
    out["adx"] = adx(out["high"], out["low"], close, config.adx_period)
    out["atr"] = atr(out["high"], out["low"], close, config.atr_period)
    out["rsi"] = rsi(close, config.rsi_period)

    macd_frame = macd(close)
    out["macd"] = macd_frame["macd"]
    out["macd_signal"] = macd_frame["signal"]
    out["macd_hist"] = macd_frame["histogram"]

    stoch = stochastic(out["high"], out["low"], close)
    out["stoch_k"] = stoch["k"]
    out["stoch_d"] = stoch["d"]

    supertrend_frame = supertrend(
        out["high"], out["low"], close, config.atr_period, 3.0
    )
    out["supertrend_line"] = supertrend_frame["line"]
    out["supertrend_dir"] = supertrend_frame["direction"]

    out["bb_width"] = _bb_width(close, config.bb_period, config.bb_std)

    if "volume" in out.columns:
        out["volume_ma"] = _volume_ma(out["volume"], config.volume_ma_period)
    else:
        out["volume_ma"] = np.nan

    # Swings carry a confirmation position; consumers must gate on it. Broadcast
    # per-bar so each bar sees the most recent *already confirmed* pivot in O(1),
    # rather than re-filtering a pivot frame for every bar.
    n_bars = len(out)
    highs = confirmed_swing_highs(out["high"], config.sr_lookback)
    lows = confirmed_swing_lows(out["low"], config.sr_lookback)
    for side, pivots in (("high", highs), ("low", lows)):
        out[f"swing_{side}_pos"] = _broadcast_pivot(pivots, n_bars, "pivot_pos")
        out[f"swing_{side}_confirm"] = _broadcast_pivot(pivots, n_bars, "confirm_pos")
        out[f"swing_{side}_price"] = _broadcast_pivot(pivots, n_bars, "price")

    return out


def _broadcast_pivot(
    pivots: pd.DataFrame,
    n_bars: int,
    column: str,
) -> np.ndarray:
    """Broadcast a pivot attribute across bars from each pivot's confirmation onward.

    A pivot becomes knowable at its ``confirm_pos``, so the attribute is written
    into every bar from that index to the end. Reading it earlier is precisely the
    look-ahead the confirmation position exists to prevent, and the fact that this
    function fills forward rather than backward is what enforces that.

    Args:
        pivots: Output of :func:`~signals.indicators.confirmed_swing_highs` or
            its low-side mirror. An empty frame yields all-NaN.
        n_bars: Length of the frame being annotated.
        column: Attribute to broadcast: ``pivot_pos``, ``confirm_pos`` or ``price``.

    Returns:
        Float array of length ``n_bars``.
    """
    values = np.full(n_bars, np.nan)
    if pivots.empty:
        return values
    for confirm, value in zip(
        pivots["confirm_pos"].to_numpy(dtype="float64"),
        pivots[column].to_numpy(dtype="float64"),
        strict=True,
    ):
        index = int(confirm)
        if 0 <= index < n_bars:
            values[index:] = value
    return values

#: A directional score's magnitude is clipped here. Without a cap, an indicator
#: ratio could dominate the weighted sum and make the total exceed [-1, 1].
_SCORE_CLIP = 1.0


def _clip(value: float) -> float:
    """Clamp a raw score into ``[-1, 1]``, mapping NaN to 0.0."""
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return 0.0
    return float(np.clip(value, -_SCORE_CLIP, _SCORE_CLIP))


def _is_finite(value: object) -> bool:
    """Whether ``value`` is a real, finite number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value)





# --------------------------------------------------------------------------- #
# Layer 1 — trend
# --------------------------------------------------------------------------- #


def score_trend(frame: pd.DataFrame, config: SignalConfig, pos: int) -> tuple[float, bool, str]:
    """Score the trend layer on the bar at positional index ``pos``.

    Reads the EMA relationship and an optional Supertrend, and gates on ADX so
    that a ranging market is not scored as a trend. ADX is a *gate*, not a
    vote: a weak trend makes the layer unevaluable rather than bearish, because
    "there is no trend" is not the same claim as "the trend is down".

    Returns:
        ``(score, evaluable, detail)``.
    """
    fast_now = frame["ema_fast"].iloc[pos]
    slow_now = frame["ema_slow"].iloc[pos]
    adx_now = frame["adx"].iloc[pos]

    if not (_is_finite(fast_now) and _is_finite(slow_now)):
        return 0.0, False, f"EMA warmup incomplete (needs {config.ema_slow} bars)"
    if not _is_finite(adx_now):
        return 0.0, False, "ADX warmup incomplete"

    if adx_now < config.adx_trend_min:
        # Below the ADX floor there is no trend to have an opinion about. Reporting
        # this as unevaluable is what lets `trend` stay a mandatory layer honestly:
        # a ranging market cannot produce a trend-confirmed signal.
        return 0.0, False, f"ADX {adx_now:.1f} below floor {config.adx_trend_min:.1f} (ranging)"

    atr_now = frame["atr"].iloc[pos]
    if not _is_finite(atr_now) or atr_now <= 0.0:
        return 0.0, False, "ATR unavailable"

    trend_strength = float((fast_now - slow_now) / slow_now)
    # Normalise the gap to ATR so the score is comparable across instruments and
    # volatility regimes; a 1% EMA gap means something very different for gold at
    # 4,000 than for a low-priced pair.
    normalised = trend_strength * float(frame["close"].iloc[pos]) / atr_now
    score = _clip(normalised / 2.0)

    detail = (
        f"EMA{config.ema_fast}={fast_now:.2f} vs EMA{config.ema_slow}={slow_now:.2f}, "
        f"ADX={adx_now:.1f}"
    )

    st_dir = frame["supertrend_dir"].iloc[pos]
    if _is_finite(st_dir):
        st_vote = 1.0 if float(st_dir) > 0 else -1.0
        # Supertrend is the stronger of the two when they disagree, because it is
        # an ATR-banded structure rather than a pair of averages.
        score = (
            st_vote
            if np.sign(score) != st_vote
            else _clip(0.5 * score + 0.5 * st_vote)
        )
        detail += f", Supertrend={'up' if st_vote > 0 else 'down'}"

    return score, True, detail


# --------------------------------------------------------------------------- #
# Layer 2 — momentum
# --------------------------------------------------------------------------- #


def score_momentum(frame: pd.DataFrame, config: SignalConfig, pos: int) -> tuple[float, bool, str]:
    """Score RSI position, MACD histogram and a stochastic cross.

    Three sub-signals are averaged. A cross is detected between bars ``pos - 1``
    and ``pos``, which is the only legitimate way to time a cross: comparing bar
    ``pos`` with bar ``pos + 1`` would be look-ahead.

    Returns:
        ``(score, evaluable, detail)``.
    """
    if pos < 1:
        return 0.0, False, "not enough bars for a cross comparison"

    votes: list[float] = []
    details: list[str] = []

    rsi_now = frame["rsi"].iloc[pos]
    if not _is_finite(rsi_now):
        return 0.0, False, "RSI warmup incomplete"
    # Oversold favours a bounce (BUY), overbought favours a fade (SELL). The
    # reading is scaled by how far into the extreme it is, so a marginal oversold
    # is a weak vote rather than a full one.
    if rsi_now <= config.rsi_oversold:
        span = config.rsi_overbought - config.rsi_oversold
        depth = (config.rsi_oversold - rsi_now) / max(span, 1.0)
        votes.append(_clip(0.5 + min(depth, 1.0)))
        details.append(f"RSI {rsi_now:.1f} oversold")
    elif rsi_now >= config.rsi_overbought:
        span = config.rsi_overbought - config.rsi_oversold
        depth = (rsi_now - config.rsi_overbought) / max(span, 1.0)
        votes.append(_clip(-0.5 - min(depth, 1.0)))
        details.append(f"RSI {rsi_now:.1f} overbought")
    else:
        # Mid-range: lean with distance from 50 so the layer is never silent.
        votes.append(_clip((rsi_now - 50.0) / 50.0))
        details.append(f"RSI {rsi_now:.1f}")

    hist_now = frame["macd_hist"].iloc[pos]
    if not _is_finite(hist_now):
        return 0.0, False, "MACD warmup incomplete"
    # Histogram slope between the last two bars: a sign change is a cross.
    prev_hist = frame["macd_hist"].iloc[pos - 1]
    slope = hist_now - float(prev_hist) if _is_finite(prev_hist) else hist_now
    reference = float(frame["close"].iloc[pos])
    votes.append(_clip(slope / (reference * 0.002)))
    details.append(f"MACD hist {hist_now:+.4f}")

    k_now = frame["stoch_k"].iloc[pos]
    d_now = frame["stoch_d"].iloc[pos]
    if _is_finite(k_now) and _is_finite(d_now):
        cross = 1.0 if k_now > d_now else -1.0
        votes.append(0.3 * cross)
        details.append(f"%K {k_now:.1f} {'>' if cross > 0 else '<'} %D")

    if not votes:
        return 0.0, False, "no momentum input available"
    return _clip(float(np.mean(votes))), True, "; ".join(details)


# --------------------------------------------------------------------------- #
# Layer 3 — volume
# --------------------------------------------------------------------------- #


def score_volume(frame: pd.DataFrame, config: SignalConfig, pos: int) -> tuple[float, bool, str]:
    """Score volume confirmation.

    Two components: the current bar's volume against its moving average, and
    whether volume is rising into the bar. Both require a ``volume`` column; when
    the feed does not supply one the layer is unevaluable rather than assumed
    positive, because "volume confirmed" is a factual claim about data the engine
    does not have.

    Returns:
        ``(score, evaluable, detail)``.
    """
    if "volume" not in frame.columns:
        return 0.0, False, "no volume column in feed"
    if pos == 0:
        return 0.0, False, "no previous bar"

    current = frame["volume"].iloc[pos]
    baseline = frame["volume_ma"].iloc[pos]

    if not (_is_finite(current) and _is_finite(baseline)):
        return 0.0, False, "volume MA warmup incomplete"
    if float(baseline) <= 0.0:
        return 0.0, False, "volume MA is zero"

    ratio = float(current) / float(baseline)
    if ratio < config.volume_mult:
        # Below the threshold volume is not confirming anything. That is a real
        # observation, so the layer votes zero rather than abstaining.
        return 0.0, True, f"volume {ratio:.2f}x MA below {config.volume_mult:.2f}x"

    magnitude = _clip((ratio - 1.0) / (config.volume_mult - 1.0 + 1e-9))
    previous = frame["volume"].iloc[pos - 1]
    rising = _is_finite(previous) and float(current) > float(previous)
    direction = (
        1.0
        if float(frame["close"].iloc[pos]) >= float(frame["close"].iloc[pos - 1])
        else -1.0
    )
    score = _clip(magnitude * (1.0 if rising else 0.6) * direction)
    return score, True, f"volume {ratio:.2f}x MA, {'rising' if rising else 'flat'}"


# --------------------------------------------------------------------------- #
# Layer 4 — price action
# --------------------------------------------------------------------------- #


def score_price_action(
    frame: pd.DataFrame, config: SignalConfig, pos: int
) -> tuple[float, bool, str]:
    """Score candlestick patterns on the bar at ``pos``.

    Engulfing and pin-bar detection read only the current bar and its immediate
    predecessor. No pattern here is "confirmed over the next N bars" — those are
    excluded deliberately, because a confirmed pattern definition requires
    future bars and would repaint.

    Returns:
        ``(score, evaluable, detail)``.
    """
    if pos < 1:
        return 0.0, False, "no previous bar"

    current = frame.iloc[pos]
    previous = frame.iloc[pos - 1]

    o, h, low, c = (
        float(current["open"]),
        float(current["high"]),
        float(current["low"]),
        float(current["close"]),
    )
    p_o, p_c = float(previous["open"]), float(previous["close"])

    body = abs(c - o)
    span = h - low
    if span <= 0.0:
        return 0.0, True, "zero-range bar"
    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - low

    scores: list[float] = []
    details: list[str] = []

    # Engulfing: a real body that fully covers the prior body, in a direction
    # opposite to the prior bar.
    prev_body = abs(p_c - p_o)
    if (
        body > prev_body > 0.0
        and ((o <= p_c and c >= p_o) or (o >= p_c and c <= p_o))
        and (c > o) != (p_c > p_o)
    ):
        scores.append(1.0 if c > o else -1.0)
        details.append("engulfing")

    # Hammer / shooting star: a small body with a long rejection wick. The wick
    # must be at least twice the body, which is the standard threshold.
    if body > 0.0:
        if lower_wick >= 2.0 * body and upper_wick < body:
            scores.append(1.0)
            details.append("hammer")
        elif upper_wick >= 2.0 * body and lower_wick < body:
            scores.append(-1.0)
            details.append("shooting star")
    else:
        # A doji at a range extreme is weak evidence; treat it as neutral rather
        # than inventing a direction from an absence of movement.
        details.append("doji")

    if not scores:
        return 0.0, True, "no qualifying pattern"

    score = float(np.mean(scores))
    return _clip(score), True, "; ".join(details)


# --------------------------------------------------------------------------- #
# Layer 5 — volatility
# --------------------------------------------------------------------------- #


def score_volatility(
    frame: pd.DataFrame, config: SignalConfig, pos: int
) -> tuple[float, bool, str]:
    """Score whether volatility conditions are tradeable.

    This layer is a *gate with an opinion*, not a direction. It votes with the
    bar's own direction when volatility is inside the configured band (conditions
    are workable), and abstains outside it. A squeeze release additionally
    strengthens the vote.

    Returns:
        ``(score, evaluable, detail)``.
    """
    if pos < 1:
        return 0.0, False, "no previous bar"

    atr_now = frame["atr"].iloc[pos]
    close_now = float(frame["close"].iloc[pos])
    if not _is_finite(atr_now) or close_now <= 0.0:
        return 0.0, False, "ATR warmup incomplete"

    ratio = atr_now / close_now
    if not (config.atr_min_ratio <= ratio <= config.atr_max_ratio):
        return 0.0, False, (
            f"ATR/close {ratio:.4f} outside "
            f"[{config.atr_min_ratio}, {config.atr_max_ratio}]"
        )

    direction = 1.0 if close_now >= float(frame["close"].iloc[pos - 1]) else -1.0
    strength = 0.5

    # Squeeze release: band width at its recent minimum. The threshold comes from a
    # quantile of the *preceding* widths only — the slice ends at `pos - 1`, so the
    # comparison is made with information available at this bar and not after it.
    width_now = frame["bb_width"].iloc[pos]
    if _is_finite(width_now) and pos >= 40:
        history = frame["bb_width"].iloc[max(0, pos - 40) : pos].dropna()
        if not history.empty and width_now <= float(history.quantile(0.2)):
            return (
                _clip(direction * 0.8),
                True,
                f"ATR/close {ratio:.4f} in band; BB squeeze ({width_now:.4f})",
            )

    return _clip(direction * strength), True, f"ATR/close {ratio:.4f} in band"


# --------------------------------------------------------------------------- #
# Layer 6 — support / resistance
# --------------------------------------------------------------------------- #


def score_support_resistance(
    frame: pd.DataFrame, config: SignalConfig, pos: int
) -> tuple[float, bool, str]:
    """Score proximity to a confirmed swing level.

    Only pivots whose *confirmation bar* is at or before ``pos`` are considered.
    :func:`~signals.indicators.confirmed_swing_highs` returns the confirmation
    position alongside each pivot precisely so this filter can be applied — using
    an unconfirmed pivot would be the single easiest way to introduce look-ahead
    into the engine.

    Returns:
        ``(score, evaluable, detail)``.
    """
    if pos < config.sr_lookback:
        return 0.0, False, "too few bars for confirmed swings"

    atr_now = frame["atr"].iloc[pos]
    close_now = float(frame["close"].iloc[pos])
    if not _is_finite(atr_now) or atr_now <= 0.0:
        return 0.0, False, "ATR unavailable"

    distance = config.sr_atr_mult * atr_now
    levels: list[tuple[float, str]] = []

    # The swing columns are broadcast from each pivot's confirmation bar onward, so
    # a non-NaN value here is by construction a pivot that was already knowable at
    # `pos`. That is the entire look-ahead defence, and it lives in
    # `build_features` rather than in a filter repeated at every call site.
    resistance = frame["swing_high_price"].iloc[pos]
    if _is_finite(resistance):
        levels.append((float(resistance), "resistance"))
    support = frame["swing_low_price"].iloc[pos]
    if _is_finite(support):
        levels.append((float(support), "support"))

    if not levels:
        return 0.0, False, "no confirmed swing level yet"

    nearest_price, kind = min(levels, key=lambda item: abs(item[0] - close_now))
    gap = abs(close_now - nearest_price)
    if gap > distance:
        return 0.0, True, f"no level within {config.sr_atr_mult:.1f}x ATR"

    # At support the level is a floor, so a nearby test favours BUY; at
    # resistance it favours SELL. Proximity scales the vote.
    direction = 1.0 if kind == "support" else -1.0
    closeness = 1.0 - (gap / distance)
    return _clip(direction * max(closeness, 0.3)), True, f"{kind} {nearest_price:.2f} within {gap:.2f}"


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #

_LAYER_FUNCTIONS = {
    "trend": score_trend,
    "momentum": score_momentum,
    "volume": score_volume,
    "price_action": score_price_action,
    "volatility": score_volatility,
    "support_resistance": score_support_resistance,
}


def score_all(
    frame: pd.DataFrame,
    config: SignalConfig,
    pos: int,
) -> dict[str, tuple[float, bool, str]]:
    """Score every layer on the bar at positional index ``pos``.

    Args:
        frame: OHLCV frame. Only rows up to ``pos`` are visible to any layer.
        config: Active configuration.
        pos: Absolute positional index of the bar being scored, used for the
            "previous bar" comparisons.

    Returns:
        Mapping of layer name to ``(score, evaluable, detail)``, covering every
        layer in :data:`~signals.models.LAYER_NAMES`.
    """
    results: dict[str, tuple[float, bool, str]] = {}
    for name, function in _LAYER_FUNCTIONS.items():
        results[name] = function(frame, config, pos)
    return results


def bollinger(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.DataFrame:
    """Re-export of :func:`~signals.indicators.bollinger_bands` for callers.

    Present so the layers module exposes a complete indicator surface without
    every caller importing two modules.
    """
    return bollinger_bands(close, period, num_std)
