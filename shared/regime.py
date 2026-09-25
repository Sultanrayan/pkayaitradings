"""Regime detection and adaptive weighting (backend-v2, Problem 4).

Static decision weights (0.45 / 0.25 / 0.30) fail across market regimes. This
module classifies the current regime from the technical indicators and returns
weights tuned per regime:

* **Trending** — price follows a clear directional trend (high ADX): the
  Technical Analyst carries the most weight.
* **Sideways** — range-bound markets (low ADX): news sentiment matters more.
* **Volatile** — an ATR spike is detected: the Risk Manager tightens control.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

_ATR_SPIKE_MULTIPLIER = 1.5
_ADX_TRENDING_THRESHOLD = 25.0


class MarketRegime(StrEnum):
    """High-level market state used to pick decision weights."""

    TRENDING = "trending"
    SIDEWAYS = "sideways"
    VOLATILE = "volatile"


@dataclass(frozen=True)
class RegimeWeights:
    """Decision weights for one regime (must sum to 1.0)."""

    technical: float
    news: float
    risk: float

    def __post_init__(self) -> None:
        if abs(self.technical + self.news + self.risk - 1.0) > 1e-6:
            raise ValueError(f"Regime weights must sum to 1.0, got {self!r}")

    def as_tuple(self) -> tuple[float, float, float]:
        """Return ``(technical, news, risk)`` weights."""
        return (self.technical, self.news, self.risk)


def detect_regime(
    *,
    adx: float | None,
    atr: float | None = None,
    atr_baseline: float | None = None,
    atr_spike_multiplier: float = _ATR_SPIKE_MULTIPLIER,
) -> MarketRegime:
    """Classify the market regime from ADX and ATR inputs.

    A volatility spike (current ATR well above its baseline) takes priority;
    otherwise a high ADX means a trend and anything else is treated as range.
    """
    if atr and atr_baseline and atr_baseline > 0 and atr >= atr_baseline * atr_spike_multiplier:
        return MarketRegime.VOLATILE
    if adx is not None and adx >= _ADX_TRENDING_THRESHOLD:
        return MarketRegime.TRENDING
    return MarketRegime.SIDEWAYS


def adaptive_weights(regime: MarketRegime) -> RegimeWeights:
    """Return the tuned decision weights for ``regime``."""
    return {
        MarketRegime.TRENDING: RegimeWeights(technical=0.60, news=0.20, risk=0.20),
        MarketRegime.SIDEWAYS: RegimeWeights(technical=0.40, news=0.35, risk=0.25),
        MarketRegime.VOLATILE: RegimeWeights(technical=0.35, news=0.30, risk=0.35),
    }[regime]
