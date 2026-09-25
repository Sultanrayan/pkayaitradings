"""Technical Analyst agent.

Pipeline: biquote OHLC → indicator engine → optional ML ensemble → signal.
"""

from __future__ import annotations

from typing import Any

from agents.base_agent import BaseAgent
from agents.technical_analyst.models.ensemble import ModelEnsemble
from agents.technical_analyst.models.features import build_features
from agents.technical_analyst.narrator import SignalNarrator, build_signal_narrator
from agents.technical_analyst.strategy import (
    TechnicalParams,
    evaluate,
    signal_from_composite,
    to_frame,
)
from data_pipeline.biquote_client import BiquoteClient
from shared.schemas.enums import AgentName, Timeframe
from shared.schemas.signals import TechnicalSignal

_STRATEGY_WEIGHT = 0.7
_MODEL_WEIGHT = 0.3


class TechnicalAnalystAgent(BaseAgent):
    """Analyses price action for a symbol/timeframe and emits a signal.

    Args:
        client: Optional biquote REST client (owned by the caller if supplied).
        params: Indicator/strategy parameters.
        ensemble: Optional predictive-model ensemble. When no model is ready the
            agent relies solely on the rule-based strategy.
        bus: Optional message bus.
        settings: Optional settings override.
    """

    name = AgentName.TECHNICAL_ANALYST

    def __init__(
        self,
        *,
        client: BiquoteClient | None = None,
        params: TechnicalParams | None = None,
        ensemble: ModelEnsemble | None = None,
        narrator: SignalNarrator | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self._owns_client = client is None
        self.client = client or BiquoteClient(self.settings)
        self.params = params or TechnicalParams()
        self.ensemble = ensemble or ModelEnsemble()
        self.narrator = narrator or build_signal_narrator(self.settings)

    async def stop(self) -> None:
        """Close the REST client when this agent created it."""
        if self._owns_client:
            await self.client.close()

    async def analyze(
        self,
        symbol: str,
        timeframe: Timeframe = Timeframe.H1,
        *,
        limit: int = 300,
    ) -> TechnicalSignal:
        """Fetch data and produce a :class:`TechnicalSignal` without publishing."""
        series = await self.client.get_ohlc(symbol, interval=timeframe, limit=limit)
        frame = to_frame(series)
        result = evaluate(frame, self.params)

        composite = result.composite
        reasons = list(result.reasons)

        model_probability = self.ensemble.predict(build_features(frame))
        if model_probability is not None:
            model_edge = 2.0 * model_probability - 1.0
            composite = _STRATEGY_WEIGHT * composite + _MODEL_WEIGHT * model_edge
            reasons.append(
                f"ML ensemble P(up)={model_probability:.2f} blended "
                f"({_STRATEGY_WEIGHT:.0%} strategy / {_MODEL_WEIGHT:.0%} model)"
            )

        signal, confidence = signal_from_composite(composite, result.trend_strength, self.params)

        reasoning = await self.narrator.narrate(
            {
                "symbol": symbol.upper(),
                "timeframe": timeframe.value,
                "signal": signal.value,
                "confidence": confidence,
                "price": result.price,
                "key_levels": result.key_levels.model_dump(),
                "indicators": result.indicators.model_dump(),
                "reasoning": "; ".join(reasons),
            }
        )
        self.log.info(
            "technical_analyst.signal",
            symbol=symbol,
            timeframe=timeframe.value,
            signal=signal.value,
            confidence=confidence,
        )
        return TechnicalSignal(
            symbol=symbol.upper(),
            timeframe=timeframe,
            signal=signal,
            confidence=confidence,
            key_levels=result.key_levels,
            indicators=result.indicators,
            reasoning=reasoning,
            price=result.price,
        )

    async def run(
        self,
        symbol: str,
        timeframe: Timeframe = Timeframe.H1,
        *,
        limit: int = 300,
        correlation_id: str | None = None,
    ) -> TechnicalSignal:
        """Analyse ``symbol`` and publish the resulting signal."""
        signal = await self._guarded(
            TechnicalSignal, self.analyze, symbol, timeframe, limit=limit
        )
        await self.publish(signal, kind="technical_signal", correlation_id=correlation_id)
        return signal
