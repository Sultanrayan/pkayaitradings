"""Feature engineering for the Technical Analyst's predictive models.

Produces a stationary, look-ahead-free feature matrix from an OHLCV frame.
Every feature at row ``t`` uses information available only up to and including
bar ``t``; the label is the sign of the *next* bar's return.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from agents.technical_analyst.indicators import adx, atr, bollinger_bands, ema, macd, rsi

FEATURE_COLUMNS: tuple[str, ...] = (
    "return_1",
    "return_5",
    "rsi",
    "macd_hist_norm",
    "atr_pct",
    "ema_gap",
    "bb_position",
    "adx",
)


def build_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Build the model feature matrix from an OHLCV frame.

    Args:
        frame: OHLCV frame indexed by open time, oldest-first.

    Returns:
        A frame with :data:`FEATURE_COLUMNS`, rows containing NaNs dropped.
    """
    required = {"high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLC frame is missing columns: {sorted(missing)}")

    close = frame["close"]
    features = pd.DataFrame(index=frame.index)
    features["return_1"] = close.pct_change(1)
    features["return_5"] = close.pct_change(5)
    features["rsi"] = rsi(close, 14) / 100.0

    macd_frame = macd(close, 12, 26, 9)
    features["macd_hist_norm"] = macd_frame["histogram"] / close.replace(0.0, np.nan)

    atr_values = atr(frame["high"], frame["low"], close, 14)
    features["atr_pct"] = atr_values / close.replace(0.0, np.nan)

    features["ema_gap"] = (ema(close, 12) - ema(close, 26)) / close.replace(0.0, np.nan)

    bands = bollinger_bands(close, 20, 2.0)
    width = (bands["upper"] - bands["lower"]).replace(0.0, np.nan)
    features["bb_position"] = (close - bands["lower"]) / width

    features["adx"] = adx(frame["high"], frame["low"], close, 14) / 100.0

    return features.replace([np.inf, -np.inf], np.nan).dropna()


def build_labels(frame: pd.DataFrame) -> pd.Series:
    """Binary next-bar direction labels (``1`` up, ``0`` down), aligned to features."""
    forward_return = frame["close"].pct_change(1).shift(-1)
    labels = (forward_return > 0).astype(int)
    labels.name = "target"
    return labels
