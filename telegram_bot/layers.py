"""Seven-layer scoring engine for the Telegram bot.

Weighting (exactly as specified):

============================  =======
Layer                          Weight
============================  =======
trend                           0.20
momentum                        0.20
order_flow                      0.20
volume                          0.10
volatility                      0.10
price_action                    0.10
support_resistance              0.10
============================  =======

Each layer returns a directional score in ``[-1, 1]``. Positive favours BUY,
negative favours SELL. Confidence is the weighted magnitude of agreement, so a
signal requires the layers to *agree*, not merely to sum.

Abstention
----------
A layer that cannot be evaluated — indicator warmup, no tick volume, no confirmed
swing — reports ``evaluable=False`` and contributes nothing. The remaining
weight is renormalised so confidence stays in ``[0, 1]``. A layer reporting a
confident ``0.0`` because it lacks data would be a fabricated vote.

Non-repainting
--------------
Scoring happens on closed bars only, and every indicator here is streaming, so
signals are computed once for the full frame and read by position. ``engine.py``
owns the closed-bar gate; this module's contract is that it never reads a bar
after the one it is asked about.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from telegram_bot import indicators as ind
from telegram_bot.orderflow import OrderFlowSnapshot, compute_order_flow

__all__ = [
    "LAYER_NAMES",
    "LAYER_WEIGHTS",
    "LayerResult",
    "LayerScores",
    "build_features",
    "compute_layers",
]

#: Layer name -> weight. Sums to 1.0.
LAYER_WEIGHTS: dict[str, float] = {
    "trend": 0.20,
    "momentum": 0.20,
    "order_flow": 0.20,
    "volume": 0.10,
    "volatility": 0.10,
    "price_action": 0.10,
    "support_resistance": 0.10,
}

#: Reporting order for the confidence block.
LAYER_NAMES: tuple[str, ...] = (
    "trend",
    "momentum",
    "order_flow",
    "volume",
    "volatility",
    "price_action",
    "support_resistance",
)

#: The five layers shown in the message header, per the required UI. Price action
#: and support/resistance are computed and contribute to confidence but are not
#: listed, matching the format the messages must match exactly.
DISPLAY_LAYERS: tuple[str, ...] = ("trend", "momentum", "order_flow", "volume", "volatility")


@dataclass(frozen=True)
class LayerResult:
    """One layer's verdict on one bar.

    Attributes:
        name: Layer name.
        score: Directional score in ``[-1, 1]``.
        evaluable: Whether the layer had data to form an opinion.
        detail: Short clause for the analysis block, e.g. ``"RSI 28"``.
    """

    name: str
    score: float
    evaluable: bool
    detail: str = ""


@dataclass(frozen=True)
class LayerScores:
    """All seven layer results for one bar, plus the order-flow snapshot.

    Attributes:
        results: Per-layer results keyed by name.
        order_flow: The order-flow snapshot for the bar.
    """

    results: dict[str, LayerResult]
    order_flow: OrderFlowSnapshot

    def score(self, name: str) -> float:
        """Layer score, or 0.0 when absent."""
        result = self.results.get(name)
        return result.score if result is not None else 0.0

    def percent(self, name: str) -> int:
        """Layer score as a 0-100 display percentage."""
        result = self.results.get(name)
        if result is None or not result.evaluable:
            return 0
        return min(100, round(abs(result.score) * 100))


def _clip(value: float) -> float:
    """Clamp to ``[-1, 1]``, mapping NaN to 0.0."""
    if value is None or not np.isfinite(value):
        return 0.0
    return float(np.clip(value, -1.0, 1.0))


def _finite(value: Any) -> bool:
    """Whether ``value`` is a real, finite number."""
    return isinstance(value, (int, float)) and not isinstance(value, bool) and np.isfinite(value)


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Compute every indicator the seven layers need, in one pass.

    Doing this once and reading by position is what keeps a scan fast enough to
    run eight pairs every minute. It does not weaken the no-repaint guarantee,
    because every indicator used here is streaming — see
    ``signals/tests/test_indicators.py::test_indicators_have_no_lookahead`` for
    the property asserted directly.

    Args:
        frame: OHLCV frame with ``tick_volume``.

    Returns:
        A copy with the feature columns appended.
    """
    out = frame.copy()
    close = out["close"]

    out["ema50"] = ind.ema(close, 50)
    out["ema200"] = ind.ema(close, 200)
    out["adx"] = ind.adx(out["high"], out["low"], close, 14)
    out["atr"] = ind.atr(out["high"], out["low"], close, 14)

    macd_frame = ind.macd(close)
    out["macd"] = macd_frame["macd"]
    out["macd_signal"] = macd_frame["signal"]
    out["macd_hist"] = macd_frame["histogram"]

    stoch = ind.stochastic(out["high"], out["low"], close, 14, 3)
    out["stoch_k"] = stoch["k"]
    out["stoch_d"] = stoch["d"]

    st = ind.supertrend(out["high"], out["low"], close, 10, 3.0)
    out["st_line"] = st["line"]
    out["st_dir"] = st["direction"]

    bb = ind.bollinger_bands(close, 20, 2.0)
    out["bb_upper"] = bb["upper"]
    out["bb_lower"] = bb["lower"]
    out["bb_middle"] = bb["middle"]

    kc = ind.keltner_channels(out["high"], out["low"], close, period=20, multiplier=1.5)
    out["kc_upper"] = kc["upper"]
    out["kc_lower"] = kc["lower"]
    out["kc_middle"] = kc["middle"]

    out["obv"] = ind.obv(close, _volume_series(out))
    out["mfi"] = ind.mfi(out["high"], out["low"], close, _volume_series(out), 14)

    swings = ind.swing_levels(out["high"], out["low"], lookback=10)
    out["swing_high_price"] = swings["high_price"]
    out["swing_low_price"] = swings["low_price"]

    fib = ind.fibo_levels(out["high"], out["low"], lookback=50)
    for column in ("fib_236", "fib_382", "fib_500", "fib_618", "fib_786"):
        out[column] = fib[column]

    pivots = ind.pivot_points(out["high"], out["low"], close)
    for column in ("pivot", "r1", "s1", "r2", "s2"):
        out[column] = pivots[column]

    return out


def _volume_series(frame: pd.DataFrame) -> pd.Series:
    """Volume for indicator purposes.

    Prefers real ``volume``, falls back to ``tick_volume``. When neither exists or
    both are zero the series is all zeros, which makes the volume and order-flow
    layers abstain rather than invent a reading.
    """
    for column in ("volume", "tick_volume"):
        if column in frame.columns:
            series = pd.to_numeric(frame[column], errors="coerce").fillna(0.0)
            if float(series.abs().sum()) > 0.0:
                return series
    return pd.Series(0.0, index=frame.index)


def _has_volume(frame: pd.DataFrame) -> bool:
    """Whether any volume-like column carries non-zero data."""
    return float(_volume_series(frame).abs().sum()) > 0.0


# --------------------------------------------------------------------------- #
# Layer 1 — trend
# --------------------------------------------------------------------------- #


def _trend(features: pd.DataFrame, pos: int) -> LayerResult:
    """EMA relationship, Supertrend direction and an ADX gate.

    ADX is a gate rather than a vote: a weak trend means the layer has no opinion,
    not that the trend is bearish.
    """
    fast = features["ema50"].iloc[pos]
    slow = features["ema200"].iloc[pos]
    adx_value = features["adx"].iloc[pos]

    if not (_finite(fast) and _finite(slow)):
        return LayerResult("trend", 0.0, False, "warmup")
    if not _finite(adx_value):
        return LayerResult("trend", 0.0, False, "warmup")
    if adx_value <= 20.0:
        return LayerResult("trend", 0.0, False, f"ADX {adx_value:.0f} (no trend)")

    atr_value = features["atr"].iloc[pos]
    if not _finite(atr_value) or atr_value <= 0.0:
        return LayerResult("trend", 0.0, False, "ATR unavailable")

    close_now = float(features["close"].iloc[pos])
    gap = (float(fast) - float(slow)) / float(slow)
    normalised = gap * close_now / float(atr_value)
    score = _clip(normalised / 2.0)

    st_dir = features["st_dir"].iloc[pos]
    direction_word = "bullish"
    if _finite(st_dir):
        st_vote = 1.0 if float(st_dir) > 0 else -1.0
        score = (
            st_vote if np.sign(score) != st_vote else _clip(0.5 * score + 0.5 * st_vote)
        )
        direction_word = "bullish" if st_vote > 0 else "bearish"

    return LayerResult("trend", score, True, direction_word)


# --------------------------------------------------------------------------- #
# Layer 2 — momentum
# --------------------------------------------------------------------------- #


def _momentum(features: pd.DataFrame, pos: int) -> LayerResult:
    """RSI extremes, MACD slope and a stochastic cross."""
    if pos < 2:
        return LayerResult("momentum", 0.0, False, "warmup")

    rsi_frame = ind.rsi(features["close"].iloc[: pos + 1], 14)
    rsi_value = float(rsi_frame.iloc[-1])
    if not np.isfinite(rsi_value):
        return LayerResult("momentum", 0.0, False, "warmup")

    if rsi_value <= 30.0:
        rsi_vote = _clip(0.5 + (30.0 - rsi_value) / 40.0)
    elif rsi_value >= 70.0:
        rsi_vote = _clip(-0.5 - (rsi_value - 70.0) / 40.0)
    else:
        rsi_vote = _clip((rsi_value - 50.0) / 50.0)

    hist_now = features["macd_hist"].iloc[pos]
    hist_prev = features["macd_hist"].iloc[pos - 1]
    if not (_finite(hist_now) and _finite(hist_prev)):
        return LayerResult("momentum", 0.0, False, "warmup")
    close_now = float(features["close"].iloc[pos])
    slope = (float(hist_now) - float(hist_prev)) / (close_now * 0.002)
    macd_vote = _clip(slope)

    k_now = features["stoch_k"].iloc[pos]
    d_now = features["stoch_d"].iloc[pos]
    stoch_vote = 0.0
    if _finite(k_now) and _finite(d_now):
        stoch_vote = 0.3 if float(k_now) > float(d_now) else -0.3

    score = _clip(float(np.mean([rsi_vote, macd_vote, stoch_vote])))
    return LayerResult("momentum", score, True, f"RSI {rsi_value:.0f}")


# --------------------------------------------------------------------------- #
# Layer 3 — order flow
# --------------------------------------------------------------------------- #


def _order_flow(
    snapshot: OrderFlowSnapshot, features: pd.DataFrame, pos: int
) -> LayerResult:
    """Score the estimated order-flow snapshot.

    Abstains when the feed carried no tick data, because "no flow" and "no data"
    are different claims and only one of them is a trade decision.
    """
    # No ticks at all: the estimator has nothing to work from, and reporting a
    # neutral 0.0 would be indistinguishable from "genuinely no pressure".
    if snapshot.delta == 0.0 and snapshot.cvd == 0.0:
        return LayerResult("order_flow", 0.0, False, "no tick data")

    if snapshot.delta == 0.0:
        return LayerResult("order_flow", 0.0, True, "delta 0")

    scale = max(abs(snapshot.delta), 1.0)
    flow = _clip(snapshot.delta / (scale * 2.0))

    # CVD trend confirms or contradicts the bar's own delta.
    if snapshot.cvd_trend == "rising":
        flow = _clip(flow * 1.2 if flow > 0 else flow * 0.8)
    elif snapshot.cvd_trend == "falling":
        flow = _clip(flow * 1.2 if flow < 0 else flow * 0.8)

    if snapshot.large_order:
        flow = _clip(flow * 1.3)

    return LayerResult("order_flow", flow, True, f"delta {snapshot.delta:+.0f}")


# --------------------------------------------------------------------------- #
# Layer 4 — volume
# --------------------------------------------------------------------------- #


def _volume(features: pd.DataFrame, pos: int) -> LayerResult:
    """Volume against its average, OBV slope and MFI position."""
    if pos < 21:
        return LayerResult("volume", 0.0, False, "warmup")
    if not _has_volume(features):
        return LayerResult("volume", 0.0, False, "no volume data")

    volume = _volume_series(features)
    average = volume.rolling(20, min_periods=20).mean().iloc[pos]
    current = float(volume.iloc[pos])
    if not (_finite(average) and average > 0.0):
        return LayerResult("volume", 0.0, False, "warmup")

    ratio = current / float(average)
    magnitude = _clip((ratio - 1.0) / 0.2)
    close_now = float(features["close"].iloc[pos])
    direction = 1.0 if close_now >= float(features["close"].iloc[pos - 1]) else -1.0
    volume_vote = _clip(magnitude * direction)

    obv_now = features["obv"].iloc[pos]
    obv_prev = features["obv"].iloc[pos - 1]
    obv_vote = 0.0
    if _finite(obv_now) and _finite(obv_prev):
        change = float(obv_now) - float(obv_prev)
        obv_vote = _clip(np.sign(change) * min(abs(change) / max(current, 1.0), 1.0))

    mfi_value = features["mfi"].iloc[pos]
    mfi_vote = 0.0
    if _finite(mfi_value):
        mfi_vote = _clip((float(mfi_value) - 50.0) / 50.0)

    score = _clip(float(np.mean([volume_vote, obv_vote, mfi_vote])))
    return LayerResult("volume", score, True, f"{ratio:.1f}x avg")


# --------------------------------------------------------------------------- #
# Layer 5 — volatility
# --------------------------------------------------------------------------- #


def _volatility(features: pd.DataFrame, pos: int) -> LayerResult:
    """Vote with the bar's direction when volatility is workable.

    A gate with an opinion, not a direction source: wide stops make a trade risky,
    not bearish.
    """
    if pos < 2:
        return LayerResult("volatility", 0.0, False, "warmup")

    atr_value = features["atr"].iloc[pos]
    close_now = float(features["close"].iloc[pos])
    if not _finite(atr_value) or close_now <= 0.0:
        return LayerResult("volatility", 0.0, False, "warmup")

    ratio = float(atr_value) / close_now
    if ratio < 0.0002 or ratio > 0.08:
        return LayerResult("volatility", 0.0, False, f"ATR {ratio:.3f}")

    direction = 1.0 if close_now >= float(features["close"].iloc[pos - 1]) else -1.0
    strength = 0.5

    upper = features["bb_upper"].iloc[pos]
    lower = features["bb_lower"].iloc[pos]
    middle = features["bb_middle"].iloc[pos]
    if _finite(upper) and _finite(lower) and _finite(middle) and middle > 0:
        width = (float(upper) - float(lower)) / float(middle)
        history = (
            ((features["bb_upper"] - features["bb_lower"]) / features["bb_middle"])
            .iloc[max(0, pos - 40) : pos]
            .dropna()
        )
        if not history.empty and width <= float(history.quantile(0.2)):
            strength = 0.8  # squeeze: conditions are coiled

    return LayerResult("volatility", _clip(direction * strength), True, f"ATR {atr_value:.2f}")


# --------------------------------------------------------------------------- #
# Layer 6 — price action
# --------------------------------------------------------------------------- #


def _price_action(features: pd.DataFrame, pos: int) -> LayerResult:
    """Engulfing, pin bar and inside-bar breakout, read from two bars only."""
    if pos < 2:
        return LayerResult("price_action", 0.0, False, "warmup")

    current = features.iloc[pos]
    previous = features.iloc[pos - 1]
    previous2 = features.iloc[pos - 2]

    o, h, low, c = (float(current[k]) for k in ("open", "high", "low", "close"))
    p_o, p_c = float(previous["open"]), float(previous["close"])

    body = abs(c - o)
    span = h - low
    votes: list[float] = []
    labels: list[str] = []

    if span <= 0.0:
        return LayerResult("price_action", 0.0, True, "flat bar")

    prev_body = abs(p_c - p_o)
    if (
        body > prev_body > 0.0
        and ((o <= p_c and c >= p_o) or (o >= p_c and c <= p_o))
        and (c > o) != (p_c > p_o)
    ):
        votes.append(1.0 if c > o else -1.0)
        labels.append("engulfing")

    upper_wick = h - max(o, c)
    lower_wick = min(o, c) - low
    if body > 0.0:
        if lower_wick >= 2.0 * body and upper_wick < body:
            votes.append(1.0)
            labels.append("pin bar")
        elif upper_wick >= 2.0 * body and lower_wick < body:
            votes.append(-1.0)
            labels.append("pin bar")

    # Inside bar: bar 0 is contained by bar -1, so a break of bar -1's extreme
    # resolves the compression.
    if (
        float(previous["high"]) <= float(previous2["high"])
        and float(previous["low"]) >= float(previous2["low"])
    ):
        if h > float(previous["high"]):
            votes.append(1.0)
            labels.append("breakout")
        elif low < float(previous["low"]):
            votes.append(-1.0)
            labels.append("breakout")

    if not votes:
        return LayerResult("price_action", 0.0, True, "no pattern")
    return LayerResult("price_action", _clip(float(np.mean(votes))), True, labels[0])


# --------------------------------------------------------------------------- #
# Layer 7 — support / resistance
# --------------------------------------------------------------------------- #


def _support_resistance(features: pd.DataFrame, pos: int) -> LayerResult:
    """Proximity to a confirmed swing, a pivot level, or a Fibonacci band."""
    close_now = float(features["close"].iloc[pos])
    atr_value = features["atr"].iloc[pos]
    if not _finite(atr_value) or atr_value <= 0.0:
        return LayerResult("support_resistance", 0.0, False, "warmup")

    distance = atr_value
    candidates: list[tuple[float, float]] = []  # (price, direction)

    for column, direction in (
        ("swing_low_price", 1.0),
        ("swing_high_price", -1.0),
        ("pivot", 0.0),
        ("s1", 1.0),
        ("r1", -1.0),
        ("fib_618", 1.0),
        ("fib_382", -1.0),
    ):
        value = features[column].iloc[pos]
        if _finite(value):
            candidates.append((float(value), direction))

    if not candidates:
        return LayerResult("support_resistance", 0.0, False, "no levels")

    nearest, direction = min(candidates, key=lambda item: abs(item[0] - close_now))
    gap = abs(close_now - nearest)
    if gap > distance:
        return LayerResult("support_resistance", 0.0, True, "no level nearby")

    if direction == 0.0:
        # A pivot is neutral; proximity to it is mildly informative but has no
        # side, so it votes weakly rather than pretending to know which way.
        return LayerResult("support_resistance", 0.0, True, f"pivot {nearest:.2f}")

    closeness = 1.0 - (gap / distance)
    return LayerResult(
        "support_resistance",
        _clip(direction * max(closeness, 0.3)),
        True,
        f"{'support' if direction > 0 else 'resistance'} {nearest:.2f}",
    )


# --------------------------------------------------------------------------- #
# Dispatcher
# --------------------------------------------------------------------------- #


def compute_layers(
    raw_frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    position: int = -1,
) -> LayerScores:
    """Score all seven layers on one bar.

    Args:
        raw_frame: OHLCV frame with ``tick_volume``, closed bars only.
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        position: Positional index of the bar to score. ``-1`` is the last.

    Returns:
        A :class:`LayerScores` holding every layer's result and the order-flow
        snapshot the order-flow layer read.
    """
    features = build_features(raw_frame)
    pos = position if position >= 0 else len(features) + position
    pos = max(0, min(pos, len(features) - 1))

    snapshot = compute_order_flow(
        raw_frame, symbol=symbol, timeframe=timeframe, position=pos
    )

    results = {
        "trend": _trend(features, pos),
        "momentum": _momentum(features, pos),
        "order_flow": _order_flow(snapshot, features, pos),
        "volume": _volume(features, pos),
        "volatility": _volatility(features, pos),
        "price_action": _price_action(features, pos),
        "support_resistance": _support_resistance(features, pos),
    }
    return LayerScores(results=results, order_flow=snapshot)
