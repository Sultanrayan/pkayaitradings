"""Gaussian HMM regime detector (backend-v2, Problem 9).

Replaces the crude ADX/ATR heuristic with a small Gaussian HMM (diagonal
covariance) trained with Baum-Welch EM. Features are per-bar returns, rolling
volatility, ATR and a volume ratio; hidden states are mapped to regimes:

* high-volatility state  → ``HIGH_VOL``   → :data:`MarketRegime.VOLATILE`
* positive-return state  → ``BULL_TREND`` → :data:`MarketRegime.TRENDING`
* negative-return state  → ``BEAR_TREND`` → :data:`MarketRegime.TRENDING`
* otherwise              → ``RANGE``      → :data:`MarketRegime.SIDEWAYS`

The implementation is dependency-free (numpy only) so it runs in the slim
production image; a ``hmmlearn``-backed path can be added later behind the same
interface.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from shared.regime import MarketRegime

_TWO_PI = 2.0 * math.pi
_MIN_LOG_PDF = -1e9


@dataclass(frozen=True)
class RegimeDetection:
    """Result of classifying the current market regime."""

    regime: MarketRegime
    label: str
    state: int
    confidence: float
    state_means: tuple[float, ...]


class GaussianHMM:
    """Gaussian HMM (diagonal covariance) trained with Baum-Welch EM.

    Args:
        n_states: Number of hidden states.
        n_iter: Maximum EM iterations.
        tol: Convergence tolerance on the log-likelihood.
        seed: RNG seed for deterministic initialisation.
    """

    def __init__(
        self,
        *,
        n_states: int,
        n_iter: int = 50,
        tol: float = 1e-4,
        seed: int = 0,
    ) -> None:
        if n_states < 2:
            raise ValueError("n_states must be >= 2")
        self.n_states = n_states
        self.n_iter = n_iter
        self.tol = tol
        self._rng = np.random.default_rng(seed)

        self.pi: np.ndarray | None = None
        self.transition: np.ndarray | None = None
        self.means: np.ndarray | None = None
        self.variances: np.ndarray | None = None

    def fit(self, observations: np.ndarray) -> float:
        """Train on ``observations`` (``T x D``) and return the log-likelihood."""
        data = observation_values(observations)
        if data.ndim != 2 or data.shape[0] < 2:
            raise ValueError("Observations must be a 2D array with at least 2 rows")

        variance_floor = max(np.var(data, axis=0).mean() * 1e-3, 1e-9)
        self._initialise(data)
        return self._run_em(data, variance_floor)

    def _initialise(self, data: np.ndarray) -> None:
        dimension = data.shape[1]
        self.pi = np.full(self.n_states, 1.0 / self.n_states)
        transition = self._rng.random((self.n_states, self.n_states))
        transition = np.eye(self.n_states) * 4.0 + transition  # self-transition bias
        self.transition = transition / transition.sum(axis=1, keepdims=True)

        # Spread the initial means across the observed range per dimension so
        # EM can separate states instead of starting from random overlaps.
        minima = data.min(axis=0)
        maxima = data.max(axis=0)
        span = np.where(maxima - minima == 0.0, 1.0, maxima - minima)
        fractions = (
            np.linspace(0.0, 1.0, self.n_states)
            if self.n_states > 1
            else np.array([0.5])
        )
        means = np.array(
            [minima + fraction * span for fraction in fractions], dtype=float
        )
        means += self._rng.normal(0.0, 0.01, size=means.shape)
        self.means = means
        self.variances = np.full(
            (self.n_states, dimension), np.var(data, axis=0) + 1e-6
        )

    def _run_em(self, data: np.ndarray, variance_floor: float) -> float:
        previous_ll = -math.inf
        for _ in range(self.n_iter):
            _alpha, _beta, log_likelihood = self._forward_backward(data)
            if abs(log_likelihood - previous_ll) < self.tol:
                return log_likelihood
            previous_ll = log_likelihood
            self._m_step(data, variance_floor)
        return self._log_likelihood(data)

    def _gaussian_log_pdf(
        self, x: np.ndarray, mean: np.ndarray, variance: np.ndarray
    ) -> float:
        if variance.min() <= 0:
            return _MIN_LOG_PDF
        log_pdf = float(
            -0.5
            * (
                x.shape[0] * math.log(_TWO_PI)
                + float(np.sum(np.log(variance)))
                + float(np.sum(((x - mean) ** 2) / variance))
            )
        )
        return max(log_pdf, _MIN_LOG_PDF)

    def _forward_backward(
        self, data: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray, float]:
        means = self.means
        variances = self.variances
        transition = self.transition
        pi = self.pi
        if means is None or variances is None or transition is None or pi is None:
            raise RuntimeError("GaussianHMM must be fit before inference")

        alpha = np.zeros((len(data), self.n_states))
        beta = np.zeros((len(data), self.n_states))
        scales = np.zeros(len(data))

        for state in range(self.n_states):
            alpha[0, state] = pi[state] * math.exp(
                self._gaussian_log_pdf(data[0], means[state], variances[state])
            )
        scales[0] = alpha[0].sum()
        alpha[0] = alpha[0] / scales[0] if scales[0] > 0 else alpha[0]

        for t in range(1, len(data)):
            for state in range(self.n_states):
                prior = float(np.dot(alpha[t - 1], transition[:, state]))
                alpha[t, state] = prior * math.exp(
                    self._gaussian_log_pdf(data[t], means[state], variances[state])
                )
            scales[t] = alpha[t].sum()
            alpha[t] = alpha[t] / scales[t] if scales[t] > 0 else alpha[t]

        beta[-1] = 1.0
        for t in range(len(data) - 2, -1, -1):
            for state in range(self.n_states):
                forward = sum(
                    transition[state, next_state]
                    * math.exp(
                        self._gaussian_log_pdf(
                            data[t + 1], means[next_state], variances[next_state]
                        )
                    )
                    * beta[t + 1, next_state]
                    for next_state in range(self.n_states)
                )
                beta[t, state] = forward / scales[t + 1] if scales[t + 1] > 0 else forward

        log_likelihood = float(np.sum(np.log(scales[scales > 0])))
        return alpha, beta, log_likelihood

    def _m_step(self, data: np.ndarray, floor: float) -> None:
        means = self.means
        variances = self.variances
        transition = self.transition
        pi = self.pi
        if means is None or variances is None or transition is None or pi is None:
            raise RuntimeError("GaussianHMM must be fit before inference")

        alpha, beta, _ = self._forward_backward(data)
        gamma = alpha * beta
        gamma_sum = gamma.sum(axis=0)
        gamma_sum = np.where(gamma_sum > 0, gamma_sum, 1.0)

        self.pi = gamma[0] / gamma_sum

        xi = np.zeros((len(data) - 1, self.n_states, self.n_states))
        for t in range(len(data) - 1):
            for state in range(self.n_states):
                for next_state in range(self.n_states):
                    xi[t, state, next_state] = (
                        alpha[t, state]
                        * transition[state, next_state]
                        * math.exp(
                            self._gaussian_log_pdf(
                                data[t + 1], means[next_state], variances[next_state]
                            )
                        )
                        * beta[t + 1, next_state]
                    )
            denominator = xi[t].sum()
            if denominator > 0:
                xi[t] = xi[t] / denominator

        transition_new = xi.sum(axis=0)
        transition_new = transition_new / transition_new.sum(axis=1, keepdims=True)
        transition_new = np.where(np.isfinite(transition_new), transition_new, transition)
        self.transition = transition_new

        means_new = (gamma.T @ data) / gamma_sum[:, None]
        squared = np.zeros_like(variances)
        for state in range(self.n_states):
            diff = data - means_new[state]
            squared[state] = (gamma[:, state][:, None] * (diff**2)).sum(axis=0)
        variances_new = squared / gamma_sum[:, None]
        variances_new = np.maximum(variances_new, floor)

        self.means = means_new
        self.variances = variances_new

    def _log_likelihood(self, data: np.ndarray) -> float:
        _alpha, _beta, log_likelihood = self._forward_backward(data)
        return log_likelihood

    def posterior(self, observations: np.ndarray) -> np.ndarray:
        """Smoothed state posteriors (``T x S``) for ``observations``."""
        data = observation_values(observations)
        alpha, beta, _ = self._forward_backward(data)
        gamma = alpha * beta
        totals = gamma.sum(axis=1, keepdims=True)
        return np.asarray(gamma / np.where(totals > 0, totals, 1.0))

    def decode(self, observations: np.ndarray) -> tuple[np.ndarray, float]:
        """Return the Viterbi state path and its log-likelihood."""
        data = observation_values(observations)
        means = self.means
        variances = self.variances
        transition = self.transition
        pi = self.pi
        if means is None or variances is None or transition is None or pi is None:
            raise RuntimeError("GaussianHMM must be fit before inference")

        log_transition = np.log(transition + 1e-300)
        delta = np.zeros((len(data), self.n_states))
        psi = np.zeros((len(data), self.n_states), dtype=int)

        for state in range(self.n_states):
            delta[0, state] = math.log(pi[state] + 1e-300) + self._gaussian_log_pdf(
                data[0], means[state], variances[state]
            )

        for t in range(1, len(data)):
            for state in range(self.n_states):
                scores = delta[t - 1] + log_transition[:, state]
                psi[t, state] = int(np.argmax(scores))
                delta[t, state] = self._gaussian_log_pdf(
                    data[t], means[state], variances[state]
                ) + scores[psi[t, state]]

        path = np.zeros(len(data), dtype=int)
        path[-1] = int(np.argmax(delta[-1]))
        for t in range(len(data) - 2, -1, -1):
            path[t] = psi[t + 1, path[t + 1]]
        return path, float(delta[-1, path[-1]])


class HMMRegimeDetector:
    """Fits a Gaussian HMM on regime features and maps states to regimes."""

    def __init__(
        self,
        *,
        n_states: int = 4,
        n_iter: int = 50,
        n_restarts: int = 3,
        seed: int = 0,
        high_vol_quantile: float = 0.70,
    ) -> None:
        self.n_states = n_states
        self.n_iter = n_iter
        self.n_restarts = n_restarts
        self.seed = seed
        self.high_vol_quantile = high_vol_quantile

    def detect(self, features: np.ndarray) -> RegimeDetection:
        """Classify the regime from a ``T x 4`` feature matrix.

        Columns must be ``[returns, volatility, atr_pct, volume_ratio]`` (see
        :func:`build_regime_features`).
        """
        data = observation_values(features)
        if data.ndim != 2 or len(data) < 5:
            raise ValueError("Not enough observations to detect a regime")

        best_model: GaussianHMM | None = None
        best_ll = -math.inf
        for restart in range(self.n_restarts):
            model = GaussianHMM(
                n_states=self.n_states, n_iter=self.n_iter, seed=self.seed + restart
            )
            log_likelihood = model.fit(data)
            if log_likelihood > best_ll:
                best_ll = log_likelihood
                best_model = model

        assert best_model is not None
        path, _ = best_model.decode(data)
        state = int(path[-1])

        means = best_model.means
        assert means is not None
        state_means = tuple(round(float(value), 4) for value in means[:, 0])

        volatility_threshold = float(np.quantile(data[:, 1], self.high_vol_quantile))
        mean_return = float(means[state, 0])
        mean_volatility = float(means[state, 1])

        if mean_volatility >= volatility_threshold:
            label, regime = "HIGH_VOL", MarketRegime.VOLATILE
        elif mean_return > 0.0:
            label, regime = "BULL_TREND", MarketRegime.TRENDING
        elif mean_return < 0.0:
            label, regime = "BEAR_TREND", MarketRegime.TRENDING
        else:
            label, regime = "RANGE", MarketRegime.SIDEWAYS

        posterior = best_model.posterior(data)
        total = float(posterior[-1].sum())
        confidence = float(posterior[-1, state] / total) if total > 0 else 0.0
        return RegimeDetection(
            regime=regime,
            label=label,
            state=state,
            confidence=round(confidence, 4),
            state_means=state_means,
        )


def build_regime_features(frame: pd.DataFrame) -> np.ndarray:
    """Build the ``[returns, volatility, atr_pct, volume_ratio]`` feature matrix.

    Rows containing NaNs/infinities are dropped. ``tick_volume`` is optional;
    when absent the volume-ratio column is ``0``.
    """
    required = {"open", "high", "low", "close"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"OHLC frame is missing columns: {sorted(missing)}")

    close = frame["close"].astype(float)
    high = frame["high"].astype(float)
    low = frame["low"].astype(float)

    features = pd.DataFrame(index=frame.index)
    returns = close.pct_change()
    features["returns"] = returns
    features["volatility"] = returns.rolling(10).std()
    features["atr_pct"] = _atr(high, low, close, 14) / close.replace(0.0, np.nan)

    if "tick_volume" in frame.columns:
        volume = frame["tick_volume"].fillna(0.0).astype(float)
        baseline = volume.rolling(10).mean().replace(0.0, np.nan)
        features["volume_ratio"] = (volume / baseline) - 1.0
    else:
        features["volume_ratio"] = 0.0

    matrix = features.replace([np.inf, -np.inf], np.nan).dropna()
    return matrix.to_numpy(dtype=float)


def observation_values(values: np.ndarray) -> np.ndarray:
    """Return a finite 2D copy of ``values``, dropping non-finite rows."""
    array = np.asarray(values, dtype=float)
    if array.ndim == 1:
        array = array.reshape(-1, 1)
    finite = np.isfinite(array).all(axis=1)
    return array[finite]


def _atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int) -> pd.Series:
    previous_close = close.shift(1)
    ranges = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return ranges.ewm(alpha=1.0 / period, adjust=False).mean()
