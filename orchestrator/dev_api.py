"""Developer API: run the Pkay TDAI agents on your own data.

These endpoints expose the *agent logic and strategies* only. We do not supply
AI models, market data, or sentiment data: callers send their own OHLC bars,
headlines and account context, and receive the agent signals in return.

All endpoints live under ``/api/v1/agents`` and are stateless.
"""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from agents.decision_maker.agent import DecisionMakerAgent
from agents.news_monitor.llm_sentiment import SentimentResult, build_sentiment_classifier
from agents.risk_manager.agent import RiskContext, RiskManagerAgent
from agents.technical_analyst.strategy import TechnicalParams, evaluate
from shared.config import Settings, get_settings
from shared.logging import get_logger
from shared.schemas.enums import Direction, Impact, Sentiment, Timeframe
from shared.schemas.signals import (
    NewsSignal,
    RiskAssessment,
    TechnicalSignal,
    TradeDecision,
    TradeProposal,
)

_logger = get_logger(__name__)

router = APIRouter(prefix="/api/v1/agents", tags=["developer"])

DISCLAIMER = (
    "Pkay TDAI provides agent logic and trading strategies only. We do not supply "
    "AI models, market data, or sentiment data. You send the inputs and remain "
    "responsible for any decisions or trades."
)

MIN_BARS = 60

_STRATEGIES: tuple[str, ...] = (
    "EMA trend (fast/slow crossover)",
    "MACD momentum",
    "RSI momentum bias",
    "Bollinger mean-reversion",
    "ATR volatility stops",
    "ADX trend filter",
    "Fractional Kelly position sizing",
    "Historical / parametric VaR",
    "Drawdown, correlation and volatility guards",
    "Weighted consensus voting with risk veto",
)


class BarInput(BaseModel):
    """A single OHLCV bar supplied by the caller."""

    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    tick_volume: int = 0


class TechnicalRequest(BaseModel):
    """Run the Technical Analyst on caller-provided candles."""

    symbol: str = Field(min_length=1, max_length=32)
    timeframe: Timeframe = Timeframe.H1
    bars: list[BarInput] = Field(min_length=MIN_BARS)


class NewsRequest(BaseModel):
    """Run the News Monitor on caller-provided headlines or a sentiment value."""

    symbol: str = Field(default="UNKNOWN", max_length=32)
    event: str = Field(default="EXTERNAL", max_length=64)
    impact: Impact = Impact.LOW
    headlines: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)


class RiskRequest(BaseModel):
    """Run the Risk Manager on a caller-provided proposal and account context."""

    symbol: str = Field(min_length=1, max_length=32)
    direction: Direction
    entry_price: float = Field(gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    timeframe: Timeframe = Timeframe.H1
    atr: float | None = Field(default=None, gt=0)
    equity: float = Field(default=100_000.0, gt=0)
    peak_equity: float | None = Field(default=None, gt=0)
    recent_returns: list[float] = Field(default_factory=list)
    correlation: float | None = None
    atr_baseline: float | None = Field(default=None, gt=0)


class DecideRequest(BaseModel):
    """Combine previously produced agent outputs into a final decision."""

    technical: TechnicalSignal
    news: NewsSignal
    risk: RiskAssessment


class AnalyzeRequest(BaseModel):
    """Run the full agent pipeline on caller-provided data in one call."""

    symbol: str = Field(min_length=1, max_length=32)
    timeframe: Timeframe = Timeframe.H1
    bars: list[BarInput] = Field(min_length=MIN_BARS)
    headlines: list[str] = Field(default_factory=list)
    sentiment: Sentiment | None = None
    news_confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    equity: float = Field(default=100_000.0, gt=0)
    peak_equity: float | None = Field(default=None, gt=0)
    recent_returns: list[float] = Field(default_factory=list)
    correlation: float | None = None
    atr_baseline: float | None = Field(default=None, gt=0)


class AnalyzeResponse(BaseModel):
    """The full agent pipeline output for one symbol."""

    symbol: str
    technical: TechnicalSignal
    news: NewsSignal
    risk: RiskAssessment
    decision: TradeDecision
    disclaimer: str = DISCLAIMER


class CapabilitiesResponse(BaseModel):
    """What the developer API offers, and what it does not."""

    agents: list[str]
    strategies: list[str]
    indicators: list[str]
    endpoints: list[str]
    provides: list[str]
    does_not_provide: list[str]
    disclaimer: str = DISCLAIMER


def _frame_from_bars(bars: list[BarInput]) -> pd.DataFrame:
    frame = pd.DataFrame(
        [
            {
                "open_time": bar.open_time,
                "open": bar.open,
                "high": bar.high,
                "low": bar.low,
                "close": bar.close,
                "tick_volume": bar.tick_volume,
            }
            for bar in bars
        ]
    )
    return frame.set_index("open_time").sort_index()


def _technical_signal(request: TechnicalRequest, params: TechnicalParams) -> TechnicalSignal:
    frame = _frame_from_bars(request.bars)
    result = evaluate(frame, params)
    return TechnicalSignal(
        symbol=request.symbol.upper(),
        timeframe=request.timeframe,
        signal=result.signal,
        confidence=result.confidence,
        key_levels=result.key_levels,
        indicators=result.indicators,
        reasoning="; ".join(result.reasons),
        price=result.price,
    )


async def _news_signal(request: NewsRequest, settings: Settings) -> NewsSignal:
    if request.sentiment is not None:
        result = SentimentResult(
            request.sentiment, request.confidence, "sentiment provided by client"
        )
    else:
        classifier = build_sentiment_classifier(settings)
        result = await classifier.classify(request.headlines)
    return NewsSignal(
        event=request.event,
        impact=request.impact,
        affected_symbols=(request.symbol.upper(),),
        sentiment=result.sentiment,
        confidence=result.confidence,
        reasoning=result.rationale,
    )


async def _risk_assessment(
    request: RiskRequest,
    *,
    settings: Settings,
    atr: float | None = None,
) -> RiskAssessment:
    agent = RiskManagerAgent(settings=settings)
    context = RiskContext(
        equity=request.equity,
        peak_equity=request.peak_equity or request.equity,
        atr=atr if atr is not None else (request.atr or request.entry_price * 0.002),
        recent_returns=np.array(request.recent_returns, dtype=float),
        correlation=request.correlation,
        atr_baseline=request.atr_baseline,
    )
    proposal = TradeProposal(
        symbol=request.symbol.upper(),
        direction=request.direction,
        entry_price=request.entry_price,
        confidence=request.confidence,
        timeframe=request.timeframe,
        rationale="Provided by developer API",
    )
    return await agent.assess(proposal, context)


def _neutral_assessment(symbol: str) -> RiskAssessment:
    return RiskAssessment(
        symbol=symbol.upper(),
        approved=True,
        position_size=0.0,
        reasoning="No directional proposal; risk checks not required",
    )


@router.get("/capabilities", response_model=CapabilitiesResponse)
async def capabilities() -> CapabilitiesResponse:
    """List the agents, strategies and endpoints available to developers."""
    return CapabilitiesResponse(
        agents=[
            "technical_analyst",
            "news_monitor",
            "risk_manager",
            "decision_maker",
        ],
        strategies=list(_STRATEGIES),
        indicators=[
            "SMA",
            "EMA",
            "RSI",
            "MACD",
            "ATR",
            "Bollinger Bands",
            "Stochastic",
            "ADX",
        ],
        endpoints=[
            "POST /api/v1/agents/technical",
            "POST /api/v1/agents/news",
            "POST /api/v1/agents/risk",
            "POST /api/v1/agents/decide",
            "POST /api/v1/agents/analyze",
            "GET /api/v1/agents/capabilities",
        ],
        provides=[
            "Rule-based technical analysis on your candles",
            "Lexicon sentiment scoring on your headlines",
            "Risk sizing, stops and veto checks",
            "Weighted consensus decisions",
        ],
        does_not_provide=[
            "AI/ML model weights",
            "Market or price data",
            "News or sentiment data",
            "Broker connectivity",
        ],
    )


@router.post("/technical", response_model=TechnicalSignal)
async def technical(request: TechnicalRequest) -> TechnicalSignal:
    """Score caller-provided candles with the Technical Analyst strategy."""
    try:
        return _technical_signal(request, TechnicalParams())
    except ValueError as exc:
        _logger.warning("dev_api.technical_rejected", error=str(exc))
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc


@router.post("/news", response_model=NewsSignal)
async def news(request: NewsRequest) -> NewsSignal:
    """Score caller-provided headlines (or a supplied sentiment value)."""
    return await _news_signal(request, get_settings())


@router.post("/risk", response_model=RiskAssessment)
async def risk(request: RiskRequest) -> RiskAssessment:
    """Run the Risk Manager on a caller-provided proposal and account context."""
    return await _risk_assessment(request, settings=get_settings())


@router.post("/decide", response_model=TradeDecision)
async def decide(request: DecideRequest) -> TradeDecision:
    """Combine agent outputs into the final weighted decision."""
    agent = DecisionMakerAgent(settings=get_settings())
    return await agent.decide(request.technical, request.news, request.risk)


@router.post("/analyze", response_model=AnalyzeResponse)
async def analyze(request: AnalyzeRequest) -> AnalyzeResponse:
    """Run the full pipeline (technical, news, risk, decision) in one call."""
    settings = get_settings()
    try:
        technical_signal = _technical_signal(
            TechnicalRequest(
                symbol=request.symbol,
                timeframe=request.timeframe,
                bars=request.bars,
            ),
            TechnicalParams(),
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail=str(exc)
        ) from exc

    news_signal = await _news_signal(
        NewsRequest(
            symbol=request.symbol,
            headlines=request.headlines,
            sentiment=request.sentiment,
            confidence=request.news_confidence,
        ),
        settings,
    )

    if technical_signal.signal is Direction.NEUTRAL or technical_signal.price is None:
        risk_assessment = _neutral_assessment(request.symbol)
    else:
        risk_assessment = await _risk_assessment(
            RiskRequest(
                symbol=request.symbol,
                direction=technical_signal.signal,
                entry_price=technical_signal.price,
                confidence=technical_signal.confidence,
                timeframe=request.timeframe,
                atr=technical_signal.indicators.atr,
                equity=request.equity,
                peak_equity=request.peak_equity,
                recent_returns=request.recent_returns,
                correlation=request.correlation,
                atr_baseline=request.atr_baseline,
            ),
            settings=settings,
        )

    decision = await DecisionMakerAgent(settings=settings).decide(
        technical_signal, news_signal, risk_assessment
    )
    return AnalyzeResponse(
        symbol=request.symbol.upper(),
        technical=technical_signal,
        news=news_signal,
        risk=risk_assessment,
        decision=decision,
    )
