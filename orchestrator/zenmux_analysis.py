"""Deterministic technical analysis for the Zenmux analysis card.

Why this module exists
----------------------
The upstream classifier (``/v1/agenza/predict/candles``) returns a probability and
nothing else. It has no concept of market structure, key levels or reasons — the
documented response contains only ``prob_up``, ``prob_down``, ``signal``,
``confidence`` and a little context. The product asks for a card with Market
Structure, Key Reasons, Support and Resistance on it.

So those fields are computed here, from the same M5 candles the classifier scores,
using plain indicators. Every number below is derived from a real bar series:

* EMA(9/20/50) — trend alignment and position
* RSI(14), Wilder-smoothed — momentum and its slope
* ATR(14), Wilder-smoothed — volatility, used to scale level distances
* Fractal swing pivots clustered by ATR tolerance — support and resistance
* Candle-body counts — directional pressure

Nothing here forecasts. These are descriptions of bars that have already closed.
The classifier contributes direction and confidence; this module contributes
structure, reasons and levels. The API labels each field with its source so the
card never implies a single engine produced all of it.

Deliberately dependency-free: numpy is present but the series are a few hundred
floats, and a hand-rolled loop keeps the smoothing conventions explicit and
testable rather than hidden behind a vectorised expression.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from shared.schemas.enums import Timeframe

__all__ = [
    "Bar",
    "KeyLevels",
    "Structure",
    "TechnicalAnalysis",
    "analyse",
    "bars_from_candles",
    "resample",
]

Direction = Literal["BULLISH", "BEARISH", "NEUTRAL"]
Bias = Literal["bullish", "bearish", "neutral"]

#: Aggregate targets this module can build from an M5 series. Deliberately short:
#: the market feed returns roughly three days of M5, which clears the slow-average
#: minimum at M15 but nowhere near it at H1.
_TIMEFRAME_MINUTES: dict[Timeframe, int] = {
    Timeframe.M5: 5,
    Timeframe.M15: 15,
}

#: EMA spans. 50 is the slow leg that separates a trend from a bounce.
_EMA_FAST = 9
_EMA_MID = 20
_EMA_SLOW = 50

_RSI_PERIOD = 14
_ATR_PERIOD = 14

#: Fractal half-width. Two bars either side keeps M5 structure responsive without
#: labelling single-bar spikes as swings.
_SWING_HALF = 2

#: Pivots closer than this fraction of ATR are the same level, not two levels.
_PIVOT_MERGE_ATR = 0.4

#: How many bars of context the pressure count looks over.
_PRESSURE_WINDOW = 12

#: Bars required before the slow EMA is meaningful. Below this the trend read is
#: reported as neutral rather than guessed from a handful of bars.
_MIN_BARS_FOR_TREND = _EMA_SLOW + 5

#: How far the fast average must sit from the slow one, as a multiple of ATR,
#: before an interleaved stack is called a direction rather than noise.
_SIGNIFICANT_SEPARATION = 0.5


@dataclass(frozen=True, slots=True)
class Bar:
    """One closed bar.

    ``time`` is the bar's opening timestamp and is optional: it is only needed to
    aggregate M5 bars into a higher timeframe, and nothing else in this module reads
    it. ``open`` is absent because no indicator here uses it — the moving averages
    and RSI read closes, ATR and the swing pivots read highs and lows.
    """

    high: float
    low: float
    close: float
    time: datetime | None = None


@dataclass(frozen=True, slots=True)
class Structure:
    """A market-structure read."""

    bias: Bias
    detail: str


@dataclass(frozen=True, slots=True)
class KeyLevels:
    """Support and resistance, guaranteed to bracket the last close.

    ``support < close < resistance`` is an invariant, not a hope: the card renders
    these as a ladder, and a reversed or degenerate pair would draw a level on the
    wrong side of price.
    """

    support: float
    resistance: float


@dataclass(frozen=True, slots=True)
class TechnicalAnalysis:
    """Everything the card's non-model fields need."""

    close: float
    atr: float | None
    rsi: float | None
    ema_fast: float | None
    ema_mid: float | None
    ema_slow: float | None
    structure: Structure
    levels: KeyLevels
    reasons: tuple[str, ...] = field(default=())

    @property
    def bias(self) -> Bias:
        """The structural bias, for the card headline."""
        return self.structure.bias


def _ema(values: Sequence[float], period: int) -> float | None:
    """Exponential moving average, seeded with an SMA of the first ``period``.

    Returns ``None`` when there is not enough data, rather than a number derived
    from a partial window — a short EMA seeded from three bars would look like a
    real average and be meaningless.
    """
    if len(values) < period or period < 2:
        return None
    seed = sum(values[:period]) / period
    current = seed
    multiplier = 2.0 / (period + 1.0)
    for value in values[period:]:
        current = (value - current) * multiplier + current
    return current


def _rsi(closes: Sequence[float], period: int = _RSI_PERIOD) -> float | None:
    """Wilder's RSI.

    Wilder smoothing (not a simple average) is what makes the 70/30 bands mean
    anything; a plain mean of the last 14 gains drifts well inside them on a
    trending series and would understate a strong move.
    """
    if len(closes) < period + 1:
        return None
    gains = 0.0
    losses = 0.0
    for index in range(1, period + 1):
        change = closes[index] - closes[index - 1]
        if change >= 0:
            gains += change
        else:
            losses -= change
    avg_gain = gains / period
    avg_loss = losses / period
    for index in range(period + 1, len(closes)):
        change = closes[index] - closes[index - 1]
        gain = change if change > 0 else 0.0
        loss = -change if change < 0 else 0.0
        avg_gain = (avg_gain * (period - 1) + gain) / period
        avg_loss = (avg_loss * (period - 1) + loss) / period
    if avg_loss == 0.0:
        # No downside in the window: RSI is at its ceiling by definition. Reporting
        # 100 rather than dividing by zero keeps the band meaningful.
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _atr(bars: Sequence[Bar], period: int = _ATR_PERIOD) -> float | None:
    """Wilder's Average True Range."""
    if len(bars) < period + 1:
        return None
    ranges: list[float] = []
    for index in range(1, len(bars)):
        previous_close = bars[index - 1].close
        ranges.append(
            max(
                bars[index].high - bars[index].low,
                abs(bars[index].high - previous_close),
                abs(bars[index].low - previous_close),
            )
        )
    value = sum(ranges[:period]) / period
    for current in ranges[period:]:
        value = (value * (period - 1) + current) / period
    return value


def _rsi_series(closes: Sequence[float], period: int = _RSI_PERIOD) -> list[float]:
    """RSI at every point from ``period`` onward, for slope.

    Cheap enough to recompute per bar and avoids carrying a second Wilder state
    through the main calculation.
    """
    series: list[float] = []
    for end in range(period + 1, len(closes) + 1):
        value = _rsi(closes[:end], period)
        if value is not None:
            series.append(value)
    return series


def _swing_pivots(bars: Sequence[Bar], half: int = _SWING_HALF) -> tuple[list[float], list[float]]:
    """Fractal swing highs and lows.

    A bar is a swing high when its high is the strict maximum of the window
    centred on it. Strict, so a flat plateau does not register every bar of the
    plateau as its own pivot.
    """
    highs: list[float] = []
    lows: list[float] = []
    for index in range(half, len(bars) - half):
        window = bars[index - half : index + half + 1]
        high = bars[index].high
        low = bars[index].low
        if all(high > other.high for other in window if other is not bars[index]):
            highs.append(high)
        if all(low < other.low for other in window if other is not bars[index]):
            lows.append(low)
    return highs, lows


def _cluster(levels: Sequence[float], tolerance: float) -> list[tuple[float, int]]:
    """Merge nearby pivots into ``(level, touches)`` pairs.

    Sorts by price and walks, so a cluster's level is the mean of its members —
    the price the market actually defended or rejected most often, rather than the
    single most extreme spike in the group.
    """
    if not levels:
        return []
    ordered = sorted(levels)
    clusters: list[tuple[float, int]] = []
    bucket: list[float] = [ordered[0]]
    for level in ordered[1:]:
        if level - bucket[-1] <= tolerance:
            bucket.append(level)
        else:
            clusters.append((sum(bucket) / len(bucket), len(bucket)))
            bucket = [level]
    clusters.append((sum(bucket) / len(bucket), len(bucket)))
    return clusters


def _pick_levels(
    bars: Sequence[Bar],
    close: float,
    atr: float | None,
) -> KeyLevels:
    """Nearest well-supported support below and resistance above the close.

    Falls back to ATR bands when history is too thin to contain pivots, and always
    returns a bracket around ``close``. The fallback is not a guess dressed as
    analysis: when there is no swing structure there is genuinely no level to
    report, so the card is told a volatility band instead.
    """
    span = atr if atr and atr > 0 else max(close * 0.001, 0.5)
    tolerance = span * _PIVOT_MERGE_ATR

    swing_highs, swing_lows = _swing_pivots(bars)
    resistances = [cluster for cluster in _cluster(swing_highs, tolerance) if cluster[0] > close]
    supports = [cluster for cluster in _cluster(swing_lows, tolerance) if cluster[0] < close]

    # Prefer the level with the most touches; break ties by taking the nearest one,
    # since that is the level price would actually interact with first.
    resistance = min(resistances, key=lambda item: (-item[1], item[0]))[0] if resistances else None
    support = max(supports, key=lambda item: (item[1], item[0]))[0] if supports else None

    if resistance is None:
        resistance = close + span
    if support is None:
        support = close - span

    # Final geometry guard. A pivot that rounded to within a hair of the close, or
    # a degenerate flat series, would otherwise render a level on top of price.
    if resistance <= close:
        resistance = close + max(span, close * 1e-4)
    if support >= close:
        support = close - max(span, close * 1e-4)

    return KeyLevels(support=support, resistance=resistance)


def _describe_structure(
    ema_fast: float | None,
    ema_mid: float | None,
    ema_slow: float | None,
    close: float,
    atr: float | None,
    swing_highs: Sequence[float],
    swing_lows: Sequence[float],
) -> Structure:
    """Combine EMA alignment with swing sequence into one structural read.

    The final fallback compares the fast and slow averages directly, which on a
    flat random walk is a coin flip — EMA9 sits a few cents above EMA50 about half
    the time. So that comparison only counts when the gap is wide enough to be
    meaningful next to the prevailing range; otherwise the read is NEUTRAL. Without
    this, a doji would be labelled "Bullish" roughly half the time.
    """
    if ema_fast is None or ema_mid is None or ema_slow is None:
        return Structure(bias="neutral", detail="Not enough closed bars to read structure")

    stacked_up = ema_fast > ema_mid > ema_slow
    stacked_down = ema_fast < ema_mid < ema_slow

    # Significance gate, applied before any directional verdict.
    #
    # Ordering alone is not evidence. On a flat random walk the three averages land
    # in one of six orders, so a "clean bullish stack" appears roughly a third of
    # the time by luck — and when it does the gap is often a fraction of one bar's
    # range. Requiring the fast/slow separation to be a meaningful multiple of ATR
    # first is what stops a coiling market being labelled trending.
    span = atr if atr and atr > 0 else close * 0.0005
    separation = ema_fast - ema_slow
    if abs(separation) <= span * _SIGNIFICANT_SEPARATION:
        return Structure(
            bias="neutral", detail=f"Price coiling around {close:.2f}, no clear structure"
        )

    # Swing sequence: are the last two pivot highs/lows rising or falling?
    higher_highs = len(swing_highs) >= 2 and swing_highs[-1] > swing_highs[-2]
    lower_highs = len(swing_highs) >= 2 and swing_highs[-1] < swing_highs[-2]
    higher_lows = len(swing_lows) >= 2 and swing_lows[-1] > swing_lows[-2]
    lower_lows = len(swing_lows) >= 2 and swing_lows[-1] < swing_lows[-2]

    if stacked_up and (higher_highs or higher_lows):
        return Structure(bias="bullish", detail="Higher highs and higher lows")
    if stacked_down and (lower_highs or lower_lows):
        return Structure(bias="bearish", detail="Lower highs and lower lows")
    if stacked_up:
        return Structure(bias="bullish", detail="Averages stacked bullish")
    if stacked_down:
        return Structure(bias="bearish", detail="Averages stacked bearish")

    if separation > 0:
        return Structure(bias="bullish", detail="Averages interleaved, mild upward drift")
    return Structure(bias="bearish", detail="Averages interleaved, mild downward drift")


def _describe_reasons(
    bars: Sequence[Bar],
    closes: Sequence[float],
    ema_fast: float | None,
    ema_mid: float | None,
    rsi: float | None,
    rsi_previous: float | None,
    atr: float | None,
    structure: Structure,
) -> tuple[str, ...]:
    """Short, factual statements about the closed bars.

    Each is a claim a reader could verify from the chart, and each carries its own
    numbers. Nothing here asserts a future move.
    """
    reasons: list[str] = []
    close = closes[-1]

    # 1. EMA structure.
    if ema_fast is not None and ema_mid is not None:
        if ema_fast < ema_mid:
            reasons.append(
                f"Fast average is below the medium average ({ema_fast:.2f} vs {ema_mid:.2f})"
            )
        else:
            reasons.append(
                f"Fast average is above the medium average ({ema_fast:.2f} vs {ema_mid:.2f})"
            )

    # 2. Where price sits relative to the medium average.
    if ema_mid is not None:
        side = "below" if close < ema_mid else "above"
        gap = abs(close - ema_mid) / ema_mid * 100 if ema_mid else 0.0
        reasons.append(f"Last close sits {side} the medium average by {gap:.2f}%")

    # 3. RSI level and slope.
    if rsi is not None:
        if rsi >= 70:
            band = "overbought"
        elif rsi <= 30:
            band = "oversold"
        elif rsi >= 55:
            band = "firm"
        elif rsi <= 45:
            band = "soft"
        else:
            band = "neutral"
        if rsi_previous is not None:
            delta = rsi - rsi_previous
            slope = (
                "rising"
                if delta > 0.5
                else "falling" if delta < -0.5 else "flat"
            )
            reasons.append(f"Momentum is {band} at {rsi:.1f} and {slope}")
        else:
            reasons.append(f"Momentum is {band} at {rsi:.1f}")

    # 4. Directional pressure across recent bodies.
    window = bars[-_PRESSURE_WINDOW:]
    if window:
        # Count by where the close sits inside the bar's range rather than
        # close-vs-open, which ``Bar`` does not carry: a bar closing in the top
        # 40% of its range counts as an up bar.
        up = 0
        for bar in window:
            span = bar.high - bar.low
            if span <= 0:
                continue
            if (bar.close - bar.low) / span >= 0.6:
                up += 1
        down = len(window) - up
        if up != down:
            leader, lead = ("Up", up) if up > down else ("Down", down)
            reasons.append(
                f"{leader} bars led {lead} of the last {len(window)} closes"
            )

    # 5. Volatility regime.
    if atr is not None and close:
        percent = atr / close * 100
        regime = "wide" if percent >= 0.15 else "tight" if percent <= 0.05 else "normal"
        reasons.append(f"Range is {regime} at {atr:.2f} per bar ({percent:.2f}%)")

    # 6. Restate the structure so the reason list stands on its own.
    if structure.detail:
        reasons.append(structure.detail)

    return tuple(reasons[:6])


def analyse(bars: Sequence[Bar]) -> TechnicalAnalysis:
    """Run the full indicator set over closed bars.

    Args:
        bars: Closed M5 bars in ascending time order.

    Returns:
        A :class:`TechnicalAnalysis`. With fewer than a handful of bars the
        indicator fields are ``None`` and structure is reported as neutral, which
        the card renders as "insufficient data" rather than a fabricated read.

    Raises:
        ValueError: If ``bars`` is empty.
    """
    if not bars:
        raise ValueError("analyse() requires at least one closed bar")

    closes = [bar.close for bar in bars]
    close = closes[-1]

    ema_fast = _ema(closes, _EMA_FAST)
    ema_mid = _ema(closes, _EMA_MID)
    ema_slow = _ema(closes, _EMA_SLOW) if len(closes) >= _MIN_BARS_FOR_TREND else None

    rsi = _rsi(closes)
    rsi_series = _rsi_series(closes)
    rsi_previous = rsi_series[-2] if len(rsi_series) >= 2 else None

    atr = _atr(bars)
    swing_highs, swing_lows = _swing_pivots(bars)

    structure = _describe_structure(
        ema_fast, ema_mid, ema_slow, close, atr, swing_highs, swing_lows
    )
    levels = _pick_levels(bars, close, atr)
    reasons = _describe_reasons(
        bars, closes, ema_fast, ema_mid, rsi, rsi_previous, atr, structure
    )

    return TechnicalAnalysis(
        close=close,
        atr=atr,
        rsi=rsi,
        ema_fast=ema_fast,
        ema_mid=ema_mid,
        ema_slow=ema_slow,
        structure=structure,
        levels=levels,
        reasons=reasons,
    )


def bars_from_candles(candles: Sequence[dict[str, Any]]) -> list[Bar]:
    """Build bars from the upstream candle contract.

    Args:
        candles: Bars shaped like ``_fetch_candles`` produces, oldest first.

    Returns:
        Bars in the order given. Timestamps are parsed so a resample can align on
        quarter-hour boundaries; an unparseable one becomes ``None`` rather than
        raising, because a bad timestamp should not lose an otherwise usable series.
    """
    out: list[Bar] = []
    for candle in candles:
        out.append(
            Bar(
                high=float(candle["high"]),
                low=float(candle["low"]),
                close=float(candle["close"]),
                time=_parse_time(candle.get("time")),
            )
        )
    return out


def _parse_time(value: Any) -> datetime | None:
    """Parse an ISO-8601 timestamp into an aware UTC datetime, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def resample(bars: Sequence[Bar], target: Timeframe) -> list[Bar]:
    """Aggregate M5 bars into a higher timeframe.

    Buckets are aligned to the wall clock — an M15 bar covers 00, 15, 30 and 45 past
    the hour — rather than chunking the series in threes. Chunking would leave the
    first and last buckets straddling two real M15 bars whenever the series starts
    part-way through one, which quietly shifts every aggregate.

    Open is not tracked, because nothing downstream reads it.

    Args:
        bars: M5 bars, oldest first.
        target: The timeframe to build.

    Returns:
        Aggregated bars, oldest first. Returns the input unchanged for M5.
    """
    if target is Timeframe.M5:
        return list(bars)
    if not bars:
        return []

    minutes = _TIMEFRAME_MINUTES.get(target)
    if minutes is None:
        # An unsupported target is not silently treated as M5, which would report a
        # different timeframe from the one the caller asked for.
        raise ValueError(f"cannot resample M5 bars to {target!r}")

    buckets: dict[datetime, list[Bar]] = {}
    for bar in bars:
        if bar.time is None:
            raise ValueError("resample() requires bars carrying a timestamp")
        floor_minute = (bar.time.minute // minutes) * minutes
        key = bar.time.replace(minute=floor_minute, second=0, microsecond=0)
        buckets.setdefault(key, []).append(bar)

    aggregated: list[Bar] = []
    for key in sorted(buckets):
        group = buckets[key]
        aggregated.append(
            Bar(
                high=max(item.high for item in group),
                low=min(item.low for item in group),
                close=group[-1].close,
                time=key,
            )
        )
    return aggregated
