"""Optional predictive-model ensemble for the Technical Analyst.

The system is designed to run *without* any ML dependencies installed: the
:class:`ModelEnsemble` simply returns ``None`` and the agent falls back to its
rule-based strategy. When ``xgboost`` / ``torch`` and trained artifacts are
present, their probabilities are blended in.

Models are loaded lazily and never at import time, so the core package stays
light.
"""

from __future__ import annotations

from pathlib import Path
from typing import Protocol, runtime_checkable

import pandas as pd

from agents.technical_analyst.models.features import FEATURE_COLUMNS
from shared.logging import get_logger

_logger = get_logger(__name__)


@runtime_checkable
class PredictiveModel(Protocol):
    """A binary up/down classifier returning the probability of an up move."""

    @property
    def is_ready(self) -> bool:
        """Whether the model is loaded and usable."""

    def predict_proba(self, features: pd.DataFrame) -> float:
        """Return ``P(up)`` in ``[0, 1]`` for the latest feature row."""


class XGBoostModel:
    """Thin wrapper around an XGBoost binary classifier.

    Args:
        model_path: Path to a serialized ``.json``/``.ubj`` booster.
    """

    def __init__(self, model_path: Path | str) -> None:
        self._path = Path(model_path)
        self._booster: object | None = None

    @property
    def is_ready(self) -> bool:
        """Whether the model file exists and xgboost is importable."""
        if self._booster is None:
            self._load()
        return self._booster is not None

    def _load(self) -> None:
        if not self._path.exists():
            _logger.info("ensemble.xgboost_missing", path=str(self._path))
            return
        try:
            import xgboost as xgb

            booster = xgb.Booster()
            booster.load_model(str(self._path))
            self._booster = booster
            _logger.info("ensemble.xgboost_loaded", path=str(self._path))
        except Exception as exc:
            _logger.warning("ensemble.xgboost_load_failed", error=repr(exc))

    def predict_proba(self, features: pd.DataFrame) -> float:
        """Return ``P(up)`` from the XGBoost booster."""
        if not self.is_ready:
            raise RuntimeError("XGBoost model is not ready")
        import xgboost as xgb

        matrix = xgb.DMatrix(features[list(FEATURE_COLUMNS)].tail(1))
        prediction = self._booster.predict(matrix)  # type: ignore[union-attr]
        return float(prediction[0])


class LSTMModel:
    """Wrapper around a PyTorch LSTM classifier with a saved state dict.

    Args:
        model_path: Path to a ``state_dict`` checkpoint.
        input_size: Number of input features per timestep.
        hidden_size: LSTM hidden dimension.
    """

    def __init__(
        self,
        model_path: Path | str,
        *,
        input_size: int = len(FEATURE_COLUMNS),
        hidden_size: int = 64,
    ) -> None:
        self._path = Path(model_path)
        self._input_size = input_size
        self._hidden_size = hidden_size
        self._model: object | None = None

    @property
    def is_ready(self) -> bool:
        """Whether the checkpoint exists and torch is importable."""
        if self._model is None:
            self._load()
        return self._model is not None

    def _load(self) -> None:
        if not self._path.exists():
            _logger.info("ensemble.lstm_missing", path=str(self._path))
            return
        try:
            import torch

            model = torch.nn.Sequential(
                torch.nn.LSTM(self._input_size, self._hidden_size, batch_first=True),
                _LastStep(),
                torch.nn.Linear(self._hidden_size, 1),
                torch.nn.Sigmoid(),
            )
            model.load_state_dict(torch.load(str(self._path), map_location="cpu"))
            model.eval()
            self._model = model
            _logger.info("ensemble.lstm_loaded", path=str(self._path))
        except Exception as exc:
            _logger.warning("ensemble.lstm_load_failed", error=repr(exc))

    def predict_proba(self, features: pd.DataFrame) -> float:
        """Return ``P(up)`` from the LSTM."""
        if not self.is_ready:
            raise RuntimeError("LSTM model is not ready")
        model = self._model
        if model is None:  # pragma: no cover - guarded by is_ready
            raise RuntimeError("LSTM model is not ready")
        import torch

        window = features[list(FEATURE_COLUMNS)].tail(60)
        if len(window) < 2:
            raise ValueError("Not enough feature rows for an LSTM window")
        tensor = torch.tensor(window.to_numpy(dtype="float32")).unsqueeze(0)
        with torch.no_grad():
            output = model(tensor)  # type: ignore[operator]
        return float(output.item())


class ModelEnsemble:
    """Averages the probabilities of every ready model.

    Args:
        models: Candidate models. Unready models are skipped silently.
    """

    def __init__(self, models: list[PredictiveModel] | None = None) -> None:
        self._models = models or []

    @property
    def available(self) -> bool:
        """Whether at least one model is ready to predict."""
        return any(model.is_ready for model in self._models)

    def predict(self, features: pd.DataFrame) -> float | None:
        """Return the mean ``P(up)`` across ready models, or ``None``."""
        if features.empty:
            return None
        probabilities: list[float] = []
        for model in self._models:
            if not model.is_ready:
                continue
            try:
                probabilities.append(model.predict_proba(features))
            except Exception as exc:
                _logger.warning(
                    "ensemble.predict_failed", model=type(model).__name__, error=repr(exc)
                )
        if not probabilities:
            return None
        return sum(probabilities) / len(probabilities)


class _LastStep:
    """Extract the final timestep output from an LSTM layer."""

    def __call__(self, lstm_output: tuple[object, object]) -> object:
        sequence, _ = lstm_output
        return sequence[:, -1, :]  # type: ignore[index]
