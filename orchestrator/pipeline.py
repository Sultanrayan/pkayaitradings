"""End-to-end analysis pipeline orchestrating the four agents.

One cycle for a symbol runs:

1. Technical Analyst produces a signal for each requested timeframe.
2. News Monitor produces a macro/sentiment signal.
3. The Decision Maker's proposal is risk-checked by the Risk Manager.
4. The Decision Maker votes and (if approved) executes via the order manager.

All agent outputs are published on the message bus under a shared correlation
id so downstream consumers can group a cycle.
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass

import numpy as np
import pandas as pd

from agents.decision_maker.agent import DecisionMakerAgent
from agents.news_monitor.agent import NewsMonitorAgent
from agents.risk_manager.agent import RiskContext, RiskManagerAgent
from agents.technical_analyst.agent import TechnicalAnalystAgent
from data_pipeline.biquote_client import BiquoteClient
from execution.broker_api import Broker, PaperBroker
from execution.order_manager import OrderManager
from orchestrator.store import SignalStore
from shared.config import Settings, get_settings
from shared.cross_checks import confirm_timeframes
from shared.hmm_regime import HMMRegimeDetector, build_regime_features
from shared.logging import get_logger
from shared.messaging import MessageBus, create_message_bus
from shared.order_flow import analyze_order_flow
from shared.regime import MarketRegime, detect_regime
from shared.schemas.enums import Direction, Timeframe
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
    TradeProposal,
)

_logger = get_logger(__name__)

_ATR_BASELINE_BARS = 100
_RETURNS_LOOKBACK = 90


@dataclass
class CycleResult:
    """The complete output of one analysis cycle for a symbol."""

    symbol: str
    correlation_id: str
    technical_signals: dict[Timeframe, TechnicalSignal]
    primary: TechnicalSignal
    news: NewsSignal
    risk: RiskAssessment
    decision: TradeDecision

    @property
    def traded(self) -> bool:
        """Whether the cycle resulted in an executed order."""
        return self.decision.executed


@dataclass
class _EquityTracker:
    """Tracks the high-water mark used for drawdown checks."""

    peak: float = 0.0

    def update(self, equity: float) -> None:
        self.peak = max(self.peak, equity)


class AnalysisPipeline:
    """Wires agents, data and execution into a single analysis flow.

    Args:
        technical: Technical Analyst agent.
        news: News Monitor agent.
        risk: Risk Manager agent.
        decision: Decision Maker agent.
        client: Shared biquote REST client.
        settings: Optional settings override.
    """

    def __init__(
        self,
        *,
        technical: TechnicalAnalystAgent,
        news: NewsMonitorAgent,
        risk: RiskManagerAgent,
        decision: DecisionMakerAgent,
        client: BiquoteClient,
        settings: Settings | None = None,
        store: SignalStore | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.technical = technical
        self.news = news
        self.risk = risk
        self.decision = decision
        self.client = client
        self.store = store or SignalStore()
        self._equity = _EquityTracker()

    @classmethod
    async def build(
        cls,
        settings: Settings | None = None,
        *,
        bus: MessageBus | None = None,
        broker: Broker | None = None,
        store: SignalStore | None = None,
    ) -> AnalysisPipeline:
        """Construct a fully wired pipeline with default dependencies."""
        settings = settings or get_settings()
        bus = bus or await create_message_bus(settings)
        client = BiquoteClient(settings)
        broker = broker or PaperBroker(settings.paper_initial_balance)
        executor = OrderManager(broker)
        return cls(
            technical=TechnicalAnalystAgent(client=client, bus=bus, settings=settings),
            news=NewsMonitorAgent(client=client, bus=bus, settings=settings),
            risk=RiskManagerAgent(bus=bus, settings=settings),
            decision=DecisionMakerAgent(executor=executor, bus=bus, settings=settings),
            client=client,
            settings=settings,
            store=store,
        )

    async def run_cycle(
        self,
        symbol: str,
        timeframes: list[Timeframe] | None = None,
    ) -> CycleResult:
        """Run one full analysis cycle for ``symbol``."""
        timeframes = timeframes or list(self.settings.analysis_timeframes)
        correlation_id = uuid.uuid4().hex
        symbol = symbol.upper()

        technical_signals = await self._analyze_timeframes(symbol, timeframes, correlation_id)
        primary = _select_primary(technical_signals, self.settings.primary_timeframe)
        news_signal = await self.news.run(symbol, correlation_id=correlation_id)
        mtf = confirm_timeframes(technical_signals, primary)

        if primary.signal is Direction.NEUTRAL:
            risk_assessment = _neutral_assessment(symbol)
            regime = _detect_regime_from(primary)
            order_flow = None
        else:
            proposal = TradeProposal(
                symbol=symbol,
                direction=primary.signal,
                entry_price=primary.price or 0.0,
                confidence=primary.confidence,
                timeframe=primary.timeframe,
                rationale=primary.reasoning,
            )
            context = await self._build_risk_context(symbol, primary)
            regime = _regime_from_context(context, primary)
            order_flow = context.order_flow
            risk_assessment = await self.risk.run(proposal, context, correlation_id=correlation_id)

        decision = await self.decision.run(
            primary,
            news_signal,
            risk_assessment,
            regime=regime,
            mtf=mtf,
            order_flow=order_flow,
            correlation_id=correlation_id,
        )
        self.store.record_cycle(
            symbol=symbol,
            correlation_id=correlation_id,
            technical=primary,
            news=news_signal,
            risk=risk_assessment,
            decision=decision,
        )
        _logger.info(
            "pipeline.cycle_complete",
            symbol=symbol,
            decision=decision.decision.value,
            score=decision.final_score,
            traded=decision.executed,
            correlation_id=correlation_id,
        )
        return CycleResult(
            symbol=symbol,
            correlation_id=correlation_id,
            technical_signals=technical_signals,
            primary=primary,
            news=news_signal,
            risk=risk_assessment,
            decision=decision,
        )

    async def run_all(self, symbols: list[str] | None = None) -> list[CycleResult]:
        """Run a cycle for every configured symbol."""
        symbols = symbols or list(self.settings.trading_symbols)
        results: list[CycleResult] = []
        for symbol in symbols:
            try:
                results.append(await self.run_cycle(symbol))
            except Exception:
                _logger.exception("pipeline.symbol_failed", symbol=symbol)
        return results

    async def close(self) -> None:
        """Close agents and the shared REST client."""
        await self.technical.stop()
        await self.news.stop()
        await self.client.close()

    async def _analyze_timeframes(
        self, symbol: str, timeframes: list[Timeframe], correlation_id: str
    ) -> dict[Timeframe, TechnicalSignal]:
        # Run the timeframes concurrently: each analysis performs its own LLM
        # narration, which is slow, so doing them serially made a cycle hang
        # for minutes.
        results = await asyncio.gather(
            *(
                self.technical.run(symbol, timeframe, correlation_id=correlation_id)
                for timeframe in timeframes
            ),
            return_exceptions=True,
        )
        signals: dict[Timeframe, TechnicalSignal] = {}
        for timeframe, result in zip(timeframes, results, strict=True):
            if isinstance(result, BaseException):
                _logger.warning(
                    "pipeline.timeframe_failed",
                    symbol=symbol,
                    timeframe=timeframe.value,
                    error=repr(result),
                )
                continue
            signals[timeframe] = result
        if not signals:
            raise RuntimeError(f"No technical signal could be produced for {symbol}")
        return signals

    async def _build_risk_context(self, symbol: str, primary: TechnicalSignal) -> RiskContext:
        equity = await self._current_equity()
        self._equity.update(equity)

        returns = np.array([])
        atr_baseline: float | None = None
        order_flow = None
        hmm_features = None
        try:
            series = await self.client.get_ohlc(
                symbol, interval=Timeframe.D1, limit=_RETURNS_LOOKBACK
            )
            frame = pd.DataFrame(
                {
                    "open": [bar.open for bar in series.bars],
                    "high": [bar.high for bar in series.bars],
                    "low": [bar.low for bar in series.bars],
                    "close": [bar.close for bar in series.bars],
                    "tick_volume": [bar.tick_volume for bar in series.bars],
                }
            )
            returns = frame["close"].pct_change().dropna().to_numpy()
            atr_baseline = _mean_true_range(frame, _ATR_BASELINE_BARS)
            if self.settings.order_flow_enabled:
                order_flow = analyze_order_flow(frame)
            if self.settings.hmm_regime_enabled:
                hmm_features = build_regime_features(frame)
        except Exception as exc:
            _logger.warning("pipeline.returns_unavailable", symbol=symbol, error=repr(exc))

        return RiskContext(
            equity=equity,
            peak_equity=self._equity.peak or equity,
            atr=primary.indicators.atr or 0.0,
            recent_returns=returns,
            atr_baseline=atr_baseline,
            order_flow=order_flow,
            hmm_features=hmm_features,
        )

    async def _current_equity(self) -> float:
        broker = getattr(self.decision, "executor", None)
        if broker is None:
            return self.settings.paper_initial_balance
        try:
            return float(await broker.equity())
        except Exception:
            return self.settings.paper_initial_balance


async def run_analysis_cycle(
    symbol: str,
    timeframes: list[Timeframe] | None = None,
    *,
    pipeline: AnalysisPipeline | None = None,
    settings: Settings | None = None,
) -> CycleResult:
    """Convenience helper to run a single cycle, building a pipeline if needed.

    Args:
        symbol: Instrument ticker, e.g. ``XAUUSD``.
        timeframes: Timeframes to analyse; defaults to configured values.
        pipeline: Optional pre-built pipeline (reused if supplied).
        settings: Optional settings override when building a pipeline.

    Returns:
        The completed :class:`CycleResult`.
    """
    owns_pipeline = pipeline is None
    pipeline = pipeline or await AnalysisPipeline.build(settings)
    try:
        return await pipeline.run_cycle(symbol, timeframes)
    finally:
        if owns_pipeline:
            await pipeline.close()


def _select_primary(
    signals: dict[Timeframe, TechnicalSignal], preferred: Timeframe
) -> TechnicalSignal:
    if preferred in signals:
        return signals[preferred]
    return next(iter(signals.values()))


def _detect_regime_from(
    primary: TechnicalSignal, *, atr_baseline: float | None = None
) -> MarketRegime:
    """Classify the market regime from the primary signal's indicators."""
    return detect_regime(
        adx=primary.indicators.adx,
        atr=primary.indicators.atr,
        atr_baseline=atr_baseline,
    )


def _regime_from_context(context: RiskContext, primary: TechnicalSignal) -> MarketRegime:
    """Classify the regime, preferring the Gaussian HMM when features exist."""
    features = context.hmm_features
    if features is not None and len(features) >= 30:
        try:
            detector = HMMRegimeDetector()
            detection = detector.detect(features)
            return detection.regime
        except Exception as exc:
            _logger.warning("pipeline.hmm_regime_failed", error=repr(exc))
    return _detect_regime_from(primary, atr_baseline=context.atr_baseline)


def _neutral_assessment(symbol: str) -> RiskAssessment:
    return RiskAssessment(
        symbol=symbol,
        approved=True,
        position_size=0.0,
        reasoning="No directional proposal; risk checks not required",
    )


def _mean_true_range(frame: pd.DataFrame, lookback: int) -> float | None:
    if len(frame) < 2:
        return None
    previous_close = frame["close"].shift(1)
    ranges = pd.concat(
        [
            frame["high"] - frame["low"],
            (frame["high"] - previous_close).abs(),
            (frame["low"] - previous_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    window = ranges.tail(lookback).dropna()
    if window.empty:
        return None
    return float(window.mean())
