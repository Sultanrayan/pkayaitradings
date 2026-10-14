"""Deterministic OHLCV fixtures for the signal engine's tests.

Every series is generated from a seeded generator, so a test that fails today
fails for a real reason and not because a random draw changed. The generators
build *shaped* data — a trend, a reversal, a range — rather than noise, because a
signal engine needs recognisable structure to be testable at all.

The index is bar CLOSE time in UTC, matching the engine's contract. ``make_series``
produces the biquote-shaped input (open-time indexed, with an ``is_open`` flag) so
``frame_from_series`` is exercised on the same path production uses.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import numpy as np
import pandas as pd

from shared.schemas.market import OhlcBar, OhlcSeries

#: Base bar time for generated series. Fixed so timestamps are reproducible.
_BASE = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)


def make_ohlcv(
    n: int = 400,
    *,
    start: float = 2_000.0,
    drift: float = 0.0004,
    noise: float = 0.0025,
    volume: float = 1_000.0,
    timeframe_seconds: int = 3_600,
    seed: int = 7,
    base: datetime = _BASE,
) -> pd.DataFrame:
    """A seeded OHLCV frame with a mild upward drift.

    Args:
        n: Number of bars.
        start: First close.
        drift: Per-bar log drift.
        noise: Per-bar return noise.
        volume: Constant volume, or scaled if ``volume`` is a sequence.
        timeframe_seconds: Bar duration driving the index spacing.
        seed: RNG seed. The same seed always produces the same series.
        base: Timestamp of the first bar's CLOSE.

    Returns:
        Frame indexed by UTC close time with the standard OHLCV columns.
    """
    rng = np.random.default_rng(seed)
    steps = rng.normal(drift, noise, size=n)
    closes = start * np.exp(np.cumsum(steps))

    opens = np.empty(n)
    opens[0] = start
    opens[1:] = closes[:-1]
    highs = np.maximum(opens, closes) * (1.0 + rng.uniform(0.0, 0.0012, size=n))
    lows = np.minimum(opens, closes) * (1.0 - rng.uniform(0.0, 0.0012, size=n))

    index = pd.DatetimeIndex(
        [base + timedelta(seconds=timeframe_seconds * i) for i in range(n)],
        name="close_time",
    )
    return pd.DataFrame(
        {
            "open": opens,
            "high": highs,
            "low": lows,
            "close": closes,
            "volume": np.full(n, float(volume)),
        },
        index=index,
    )


def make_trend_then_reverse(
    n: int = 400,
    *,
    up_bars: int | None = None,
    start: float = 2_000.0,
    seed: int = 11,
    timeframe_seconds: int = 3_600,
) -> pd.DataFrame:
    """A sustained uptrend followed by a sustained downtrend.

    ``n`` is the **total** bar count, split between the two legs, so a caller
    asking for 400 bars gets 400 bars and can index position 300 without a
    surprise. (An earlier version treated ``n`` as the length of the first leg,
    which silently halved the output and made callers' bar indices out of range.)

    The reversal gives multi-layer agreement a realistic opportunity: price
    action, momentum and the EMA relationship can line up on the same side for
    several bars, which is the condition a signal needs.
    """
    if up_bars is None:
        up_bars = n // 2
    elif up_bars >= n:
        raise ValueError(f"up_bars ({up_bars}) must be smaller than n ({n})")
    up = make_ohlcv(
        n=up_bars,
        start=start,
        drift=0.004,
        noise=0.0012,
        seed=seed,
        timeframe_seconds=timeframe_seconds,
    )
    # The down leg must continue from where the up leg ended, not restart from the
    # same base timestamp. Both legs default to `base`, so concatenating them
    # naively overlaps every timestamp and de-duplication silently halves the
    # output — which is how a 400-bar request once produced 200 bars.
    down_start = up.index[-1] + pd.Timedelta(seconds=timeframe_seconds)
    down = make_ohlcv(
        n=n - up_bars,
        start=float(up["close"].iloc[-1]),
        drift=-0.004,
        noise=0.0012,
        seed=seed + 1,
        timeframe_seconds=timeframe_seconds,
        base=down_start,
    )
    combined = pd.concat([up, down])
    # A duplicated boundary timestamp would make bar positions ambiguous.
    return combined[~combined.index.duplicated(keep="last")]


def make_range(
    n: int = 400,
    *,
    start: float = 2_000.0,
    seed: int = 13,
    timeframe_seconds: int = 3_600,
) -> pd.DataFrame:
    """An oscillating series with no directional drift."""
    rng = np.random.default_rng(seed)
    steps = rng.normal(0.0, 0.003, size=n)
    closes = start + start * 0.05 * np.sin(np.cumsum(steps) * 6.0)
    opens = np.empty(n)
    opens[0] = start
    opens[1:] = closes[:-1]
    span = np.abs(closes - opens) + start * 0.001
    index = pd.DatetimeIndex(
        [
            _BASE + timedelta(seconds=timeframe_seconds * i) for i in range(n)
        ],
        name="close_time",
    )
    return pd.DataFrame(
        {
            "open": opens,
            "high": np.maximum(opens, closes) + span,
            "low": np.minimum(opens, closes) - span,
            "close": closes,
            "volume": np.full(n, 1_000.0),
        },
        index=index,
    )


def make_series(
    frame: pd.DataFrame,
    *,
    interval: str = "1h",
    include_open_bar: bool = False,
) -> OhlcSeries:
    """Wrap an engine frame back into an :class:`OhlcSeries`.

    Used to exercise ``frame_from_series`` against data the engine itself made,
    so the conversion is tested in the direction production uses (series → frame)
    without depending on a live feed.
    """
    seconds = int(
        (frame.index[1] - frame.index[0]).total_seconds() if len(frame) > 1 else 3_600
    )
    last_close = float(frame["close"].iloc[-1]) if len(frame) else 0.0
    last_high = float(frame["high"].iloc[-1]) if len(frame) else 0.0
    last_low = float(frame["low"].iloc[-1]) if len(frame) else 0.0

    bars = []
    for timestamp, row in frame.iterrows():
        open_time = timestamp - pd.Timedelta(seconds=seconds)
        bars.append(
            OhlcBar(
                openTime=open_time.to_pydatetime(),
                open=float(row["open"]),
                high=float(row["high"]),
                low=float(row["low"]),
                close=float(row["close"]),
                volume=float(row.get("volume", 0.0)),
                tickVolume=int(row.get("volume", 0.0)),
                isOpen=False,
            )
        )

    if include_open_bar:
        # A genuinely extra bar: it starts where the last closed bar closed and
        # closes one interval later, which is the shape a live feed produces.
        bars.append(
            OhlcBar(
                openTime=(
                    frame.index[-1] - pd.Timedelta(seconds=seconds)
                ).to_pydatetime(),
                open=last_close,
                high=max(last_close, last_high) * 1.0005,
                low=min(last_close, last_low) * 0.9995,
                close=last_close * 1.001,
                volume=float(frame["volume"].iloc[-1]) if len(frame) else 0.0,
                tickVolume=1,
                isOpen=True,
            )
        )
    return OhlcSeries(symbol="TEST", interval=interval, bars=tuple(bars))


def with_open_bar(frame: pd.DataFrame, *, mutate: float = 0.02) -> pd.DataFrame:
    """Append an unclosed bar above the last close.

    Models the live situation: the newest bar exists but is still forming, so its
    close will move. A correct engine ignores it; an incorrect one signals on it.
    """
    out = frame.copy()
    last = out.iloc[-1]
    seconds = int((out.index[-1] - out.index[-2]).total_seconds())
    new_close = float(last["close"]) * (1.0 + mutate)
    new_row = pd.DataFrame(
        {
            "open": [float(last["close"])],
            "high": [max(float(last["high"]), new_close) * 1.001],
            "low": [min(float(last["low"]), new_close) * 0.999],
            "close": [new_close],
            "volume": [float(last["volume"])],
        },
        index=pd.DatetimeIndex([out.index[-1] + pd.Timedelta(seconds=seconds)]),
    )
    return pd.concat([out, new_row])


def without_last(frame: pd.DataFrame) -> pd.DataFrame:
    """The frame minus its final bar."""
    return frame.iloc[:-1].copy()


def bar_close_times(frame: pd.DataFrame, timeframe_seconds: int = 3_600) -> list[pd.Timestamp]:
    """Close times of every bar, for building a ``now`` argument."""
    return list(frame.index)
