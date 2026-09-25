"""Value-at-Risk and correlation calculations for the Risk Manager."""

from __future__ import annotations

from statistics import NormalDist

import numpy as np
import pandas as pd


def historical_var(returns: pd.Series | np.ndarray, confidence: float = 0.95) -> float:
    """Historical (empirical) Value-at-Risk as a positive loss fraction.

    Args:
        returns: Periodic simple returns.
        confidence: Confidence level, e.g. ``0.95`` for 95% VaR.

    Returns:
        The loss at the ``confidence`` quantile (positive number), or ``0.0``
        when there is insufficient data.
    """
    values = _as_array(returns)
    if values.size == 0:
        return 0.0
    quantile = float(np.quantile(values, 1.0 - confidence))
    return max(0.0, -quantile)


def conditional_var(returns: pd.Series | np.ndarray, confidence: float = 0.95) -> float:
    """Expected Shortfall (CVaR): mean loss beyond the VaR quantile."""
    values = _as_array(returns)
    if values.size == 0:
        return 0.0
    threshold = np.quantile(values, 1.0 - confidence)
    tail = values[values <= threshold]
    if tail.size == 0:
        return 0.0
    return max(0.0, -float(tail.mean()))


def parametric_var(returns: pd.Series | np.ndarray, confidence: float = 0.95) -> float:
    """Parametric (normal) VaR assuming zero mean."""
    values = _as_array(returns)
    if values.size < 2:
        return 0.0
    z_score = _z_score(confidence)
    return max(0.0, float(z_score * values.std(ddof=1)))


def portfolio_var(
    returns: pd.Series | np.ndarray,
    weight: float,
    confidence: float = 0.95,
) -> float:
    """Scale a single-asset VaR to a portfolio weight (fraction of equity)."""
    return historical_var(returns, confidence) * abs(weight)


def correlation_matrix(returns: pd.DataFrame) -> pd.DataFrame:
    """Pearson correlation matrix of a returns frame (empty frame if <2 columns)."""
    if returns.shape[1] < 2:
        return pd.DataFrame()
    return returns.corr()


def max_pairwise_correlation(returns: pd.DataFrame) -> float:
    """Maximum absolute off-diagonal correlation in a returns frame."""
    matrix = correlation_matrix(returns)
    if matrix.empty:
        return 0.0
    mask = ~np.eye(len(matrix), dtype=bool)
    off_diagonal = matrix.to_numpy()[mask]
    if off_diagonal.size == 0:
        return 0.0
    return float(np.nanmax(np.abs(off_diagonal)))


def _as_array(returns: pd.Series | np.ndarray) -> np.ndarray:
    values = np.asarray(returns, dtype=float)
    return values[np.isfinite(values)]


def _z_score(confidence: float) -> float:
    """Inverse standard-normal CDF (the VaR z-score)."""
    if not 0.5 < confidence < 1.0:
        raise ValueError("confidence must be between 0.5 and 1.0")
    return float(NormalDist().inv_cdf(confidence))
