"""Tests for the technical indicator engine."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.technical_analyst.indicators import (
    adx,
    atr,
    bollinger_bands,
    ema,
    macd,
    rsi,
    sma,
    stochastic,
)


@pytest.fixture
def ohlc() -> pd.DataFrame:
    rng = np.random.default_rng(42)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 0.5, 200)))
    high = close + rng.uniform(0.1, 1.0, 200)
    low = close - rng.uniform(0.1, 1.0, 200)
    return pd.DataFrame(
        {"open": close.shift(1).fillna(close), "high": high, "low": low, "close": close}
    )


def test_sma_matches_manual_mean() -> None:
    series = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
    result = sma(series, 3)
    assert np.isnan(result.iloc[1])
    assert result.iloc[2] == pytest.approx(2.0)
    assert result.iloc[4] == pytest.approx(4.0)


def test_ema_first_valid_after_period() -> None:
    series = pd.Series(np.arange(1.0, 11.0))
    result = ema(series, 3)
    assert result.iloc[:2].isna().all()
    assert not np.isnan(result.iloc[2])


def test_rsi_is_bounded_and_high_in_uptrend(ohlc: pd.DataFrame) -> None:
    rising = pd.Series(np.arange(1.0, 100.0))
    result = rsi(rising, 14).dropna()
    assert result.between(0.0, 100.0).all()
    assert result.iloc[-1] > 70.0


def test_rsi_flat_series_is_fifty() -> None:
    result = rsi(pd.Series([5.0] * 50), 14).dropna()
    assert (result == 50.0).all()


def test_macd_histogram_is_difference(ohlc: pd.DataFrame) -> None:
    frame = macd(ohlc["close"])
    assert set(frame.columns) == {"macd", "signal", "histogram"}
    diff = (frame["macd"] - frame["signal"]).dropna()
    pd.testing.assert_series_equal(frame["histogram"].dropna(), diff, check_names=False)


def test_atr_is_positive(ohlc: pd.DataFrame) -> None:
    result = atr(ohlc["high"], ohlc["low"], ohlc["close"], 14).dropna()
    assert (result > 0).all()


def test_bollinger_bands_ordering(ohlc: pd.DataFrame) -> None:
    bands = bollinger_bands(ohlc["close"], 20, 2.0).dropna()
    assert (bands["upper"] >= bands["middle"]).all()
    assert (bands["middle"] >= bands["lower"]).all()


def test_adx_bounded(ohlc: pd.DataFrame) -> None:
    result = adx(ohlc["high"], ohlc["low"], ohlc["close"], 14).dropna()
    assert result.between(0.0, 100.0).all()


def test_stochastic_bounded(ohlc: pd.DataFrame) -> None:
    frame = stochastic(ohlc["high"], ohlc["low"], ohlc["close"]).dropna()
    assert frame["k"].between(0.0, 100.0).all()


def test_invalid_period_raises() -> None:
    with pytest.raises(ValueError, match="period"):
        sma(pd.Series([1.0, 2.0]), 1)
