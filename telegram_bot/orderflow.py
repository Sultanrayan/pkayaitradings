"""Order-flow estimation from OHLC and tick counts.

WHAT THIS IS NOT — read before trusting a number
------------------------------------------------
The upstream feed (biquote) is a **CFD broker feed**. Its own schema documents
this: ``last`` and ``volume`` are always ``0`` and must not be used
(``shared/schemas/market.py``). There is therefore:

* no trade-level tape,
* no aggressor side (who crossed the spread),
* no per-trade size,
* no bid or ask **size** — only bid and ask prices,
* no exchange-reported volume. ``tickVolume`` is a *count of ticks*, not volume.

Every genuine order-flow metric — delta, CVD, absorption, bid/ask imbalance,
large-order detection — is defined in terms of data the feed does not carry. They
cannot be computed. Any implementation that reports them as facts is fabricating
them.

WHAT THIS IS
------------
A **documented estimator**. It classifies each bar's tick count into buyer- and
seller-initiated buckets using a sign rule derived from the bar's own OHLC, then
aggregates. This is the standard approach when only bar data is available, and it
is a real technique with known biases — but it is an estimate, and it is
materially weaker than a real tape.

Consequences the caller must respect:

* The magnitude is not comparable to a real delta. Treat it as a *direction and
  relative strength* signal, not an absolute flow figure.
* It cannot detect absorption the way a tape does, because absorption is defined
  by large passive fills against aggressive orders — neither of which is visible.
  What is detected here is the weaker footprint: a large directional delta that
  fails to move price, which is consistent with absorption but not proof of it.
* Every snapshot carries ``source="proxy"`` so a consumer can tell an estimate
  from a measurement.

If a real tape becomes available, replace :func:`compute_order_flow` and nothing
else needs to change — the shape of :class:`OrderFlowSnapshot` is already what a
real feed would produce.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Literal

import numpy as np
import pandas as pd

__all__ = [
    "OrderFlowSnapshot",
    "classify_bar_delta",
    "compute_order_flow",
    "detect_absorption",
    "large_order_threshold",
]

#: Marks every snapshot as an estimate rather than a measurement.
SOURCE = "proxy"

CvdTrend = Literal["rising", "falling", "flat"]


def _cvd_trend(value: object) -> CvdTrend:
    """Narrow an arbitrary stored value to a :data:`CvdTrend`.

    An unrecognised trend becomes ``flat`` rather than propagating: a snapshot
    written by a future version must not be able to put an undeclared value into
    a Telegram message.
    """
    text = str(value)
    if text == "rising":
        return "rising"
    if text == "falling":
        return "falling"
    return "flat"


@dataclass(frozen=True)
class OrderFlowSnapshot:
    """One bar's estimated order-flow state.

    Attributes:
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        delta: Estimated buy-minus-sell pressure for this bar, in tick units.
        cvd: Cumulative estimated delta over the window.
        cvd_trend: Whether the cumulative line is ``rising``, ``falling`` or ``flat``.
        absorption: ``support @ price``, ``resistance @ price``, or ``None``.
        imbalance_ratio: Estimated bid-side share relative to ask, e.g. ``1.8``
            means 1.8x more buyer-initiated than seller-initiated on this bar.
        large_order: Whether this bar's tick count exceeds the 95th percentile.
        large_order_ratio: Bar tick count divided by that percentile.
        source: Always ``"proxy"``. Present so a consumer can distinguish an
            estimate from a measured figure.
        bar_ts: Unix seconds of the bar this snapshot describes.
    """

    symbol: str
    timeframe: str
    delta: float
    cvd: float
    cvd_trend: CvdTrend
    absorption: str | None
    imbalance_ratio: float
    large_order: bool
    large_order_ratio: float
    source: str
    bar_ts: int

    def to_dict(self) -> dict[str, Any]:
        """JSON-ready representation for storage and for the bus."""
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> OrderFlowSnapshot:
        """Rebuild a snapshot, tolerating missing optional keys."""
        return cls(
            symbol=str(payload.get("symbol", "")),
            timeframe=str(payload.get("timeframe", "")),
            delta=float(payload.get("delta", 0.0)),
            cvd=float(payload.get("cvd", 0.0)),
            cvd_trend=_cvd_trend(payload.get("cvd_trend", "flat")),
            absorption=payload.get("absorption"),
            imbalance_ratio=float(payload.get("imbalance_ratio", 1.0)),
            large_order=bool(payload.get("large_order", False)),
            large_order_ratio=float(payload.get("large_order_ratio", 1.0)),
            source=str(payload.get("source", SOURCE)),
            bar_ts=int(payload.get("bar_ts", 0)),
        )


def classify_bar_delta(
    open_: pd.Series,
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    ticks: pd.Series,
) -> pd.Series:
    """Estimate each bar's buyer- versus seller-initiated pressure.

    The rule is a signed tick allocation:

    * Close above the open → all ticks attributed to buyers.
    * Close below the open → all ticks attributed to sellers.
    * Close exactly at the open → fall back to the change from the previous close
      (a doji carries information about where price came from).

    Attributes:
        open_: Open prices.
        high: High prices. Accepted for interface symmetry and range checks.
        low: Low prices.
        close: Close prices.
        ticks: Tick counts per bar.

    Returns:
        Series of estimated delta. Bars with no ticks contribute 0.

    Raises:
        ValueError: If the OHLC columns and tick counts are not the same length.
    """
    lengths = {len(open_), len(high), len(low), len(close), len(ticks)}
    if len(lengths) != 1:
        raise ValueError(f"order-flow inputs must align, got lengths {sorted(lengths)}")

    open_ = pd.to_numeric(open_, errors="coerce")
    close = pd.to_numeric(close, errors="coerce")
    ticks = pd.to_numeric(ticks, errors="coerce").fillna(0.0).clip(lower=0.0)

    move = close - open_
    # A flat bar is resolved by the direction of travel into it.
    direction = np.where(move > 0, 1.0, np.where(move < 0, -1.0, np.sign(close.diff().fillna(0.0))))
    return pd.Series(direction, index=close.index) * ticks


def detect_absorption(
    delta: float,
    close: float,
    previous_close: float,
    *,
    price_move_threshold: float,
    delta_threshold: float,
) -> tuple[str | None, float]:
    """Flag the footprint of a passive side absorbing an aggressive flow.

    Large directional delta that fails to produce a proportional price move is
    *consistent with* absorption. It is not proof: on a CFD feed with no tape,
    a quiet market and a thin feed look identical.

    Args:
        delta: This bar's estimated delta.
        close: This bar's close.
        previous_close: The prior bar's close.
        price_move_threshold: Absolute price move treated as "no reaction".
        delta_threshold: Absolute delta treated as "significant pressure".

    Returns:
        ``(label, price)`` where label is ``"support @ price"``,
        ``"resistance @ price"`` or ``None``.
    """
    if abs(delta) < delta_threshold:
        return None, 0.0

    move = abs(close - previous_close)
    if move >= price_move_threshold:
        # Flow moved price. Whatever absorbed it, it was not here.
        return None, 0.0

    # Flow arrived but price did not move: buyers met sellers, or vice versa.
    if delta > 0:
        return f"support @ {previous_close:.2f}", previous_close
    return f"resistance @ {previous_close:.2f}", previous_close


def large_order_threshold(ticks: pd.Series, percentile: float = 95.0) -> float:
    """Tick count at or above which a bar counts as a large-order bar.

    Args:
        ticks: Tick counts.
        percentile: Percentile to use.

    Returns:
        The threshold, or ``0.0`` when the series is empty or all-NaN.
    """
    clean = pd.to_numeric(ticks, errors="coerce").dropna()
    if clean.empty:
        return 0.0
    return float(clean.quantile(percentile / 100.0))


def compute_order_flow(
    frame: pd.DataFrame,
    *,
    symbol: str,
    timeframe: str,
    position: int = -1,
    cvd_window: int = 50,
    absorption_lookback: int = 20,
    large_percentile: float = 95.0,
) -> OrderFlowSnapshot:
    """Estimate the order-flow state at one bar.

    Args:
        frame: OHLCV frame with a ``tick_volume`` column, indexed by bar close
            time (UTC), oldest-first. Closed bars only.
        symbol: Instrument ticker.
        timeframe: Internal timeframe.
        position: Positional index of the bar to describe. ``-1`` is the last.
        cvd_window: Bars over which the cumulative delta is summed.
        absorption_lookback: Bars used to scale the price-move threshold.
        large_percentile: Percentile defining a large-order bar.

    Returns:
        A snapshot marked ``source="proxy"``.

    Note:
        When ``tick_volume`` is absent or entirely zero — which is what a feed
        without volume looks like — every estimate collapses to 0.0 rather than
        fabricating a value. The snapshot is still returned so callers can render
        it and the UI can show a neutral reading.
    """
    if len(frame) == 0:
        return _empty_snapshot(symbol, timeframe)

    pos = position if position >= 0 else len(frame) + position
    pos = max(0, min(pos, len(frame) - 1))

    ticks = (
        frame["tick_volume"]
        if "tick_volume" in frame.columns
        else pd.Series(0.0, index=frame.index)
    )
    deltas = classify_bar_delta(
        frame["open"], frame["high"], frame["low"], frame["close"], ticks
    )

    delta = float(deltas.iloc[pos])

    start = max(0, pos - cvd_window + 1)
    cvd = float(deltas.iloc[start : pos + 1].sum())

    # Trend from the recent slope of the cumulative line, not from its sign: a
    # cumulative value that is positive but flattening is not "rising".
    window = deltas.iloc[start : pos + 1]
    cvd_trend: CvdTrend = "flat"
    if len(window) >= 3:
        cumulative = window.cumsum()
        slope = float(cumulative.iloc[-1] - cumulative.iloc[max(0, len(cumulative) - 3)])
        scale = float(window.abs().mean()) or 1.0
        if slope > scale * 0.5:
            cvd_trend = "rising"
        elif slope < -scale * 0.5:
            cvd_trend = "falling"

    close_now = float(frame["close"].iloc[pos])
    previous_close = float(frame["close"].iloc[pos - 1]) if pos > 0 else close_now

    # Threshold scales with the bar's own range, so the same rule works for gold
    # at 4,000 and bitcoin at 95,000 without a per-symbol constant.
    recent = frame["high"].iloc[max(0, pos - absorption_lookback) : pos + 1] - frame[
        "low"
    ].iloc[max(0, pos - absorption_lookback) : pos + 1]
    typical_range = float(recent.mean()) if not recent.empty else 0.0
    price_move_threshold = typical_range * 0.15

    tick_window = pd.to_numeric(ticks, errors="coerce").iloc[: pos + 1].dropna()
    threshold = large_order_threshold(tick_window, large_percentile)
    current_ticks = float(pd.to_numeric(ticks, errors="coerce").iloc[pos] or 0.0)
    ratio = (current_ticks / threshold) if threshold > 0.0 else 1.0

    absorption, _price = detect_absorption(
        delta,
        close_now,
        previous_close,
        price_move_threshold=max(price_move_threshold, 1e-9),
        delta_threshold=max(threshold * 0.8, 1.0),
    )

    buyers = max(delta, 0.0)
    sellers = max(-delta, 0.0)
    if sellers == 0.0 and buyers == 0.0:
        imbalance = 1.0
    elif sellers == 0.0:
        imbalance = float("inf")
    else:
        imbalance = buyers / sellers

    return OrderFlowSnapshot(
        symbol=symbol.upper(),
        timeframe=timeframe,
        delta=delta,
        cvd=cvd,
        cvd_trend=cvd_trend,
        absorption=absorption,
        imbalance_ratio=imbalance,
        large_order=bool(threshold > 0.0 and current_ticks >= threshold),
        large_order_ratio=ratio,
        source=SOURCE,
        bar_ts=int(frame.index[pos].timestamp()),
    )


def _empty_snapshot(symbol: str, timeframe: str) -> OrderFlowSnapshot:
    """A neutral snapshot for an empty frame."""
    return OrderFlowSnapshot(
        symbol=symbol.upper(),
        timeframe=timeframe,
        delta=0.0,
        cvd=0.0,
        cvd_trend="flat",
        absorption=None,
        imbalance_ratio=1.0,
        large_order=False,
        large_order_ratio=1.0,
        source=SOURCE,
        bar_ts=0,
    )
