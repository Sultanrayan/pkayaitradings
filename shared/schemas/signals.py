"""Agent output schemas: signals, risk assessments and trade decisions."""

from __future__ import annotations

from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field

from shared.schemas.enums import (
    AgentName,
    AlertLevel,
    Decision,
    Direction,
    Impact,
    Sentiment,
    Timeframe,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class KeyLevels(BaseModel):
    """Support/resistance levels derived from recent price action."""

    model_config = ConfigDict(frozen=True)

    support: float | None = None
    resistance: float | None = None


class IndicatorSnapshot(BaseModel):
    """Snapshot of the indicator values behind a technical signal."""

    model_config = ConfigDict(frozen=True, extra="allow")

    rsi: float | None = None
    macd_histogram: float | None = None
    macd_cross: str | None = None
    ema_fast: float | None = None
    ema_slow: float | None = None
    ema_cross: str | None = None
    atr: float | None = None
    adx: float | None = None
    bb_upper: float | None = None
    bb_lower: float | None = None


class TechnicalSignal(BaseModel):
    """Output of the Technical Analyst agent."""

    model_config = ConfigDict(frozen=True)

    agent: AgentName = AgentName.TECHNICAL_ANALYST
    symbol: str
    timeframe: Timeframe
    signal: Direction
    confidence: float = Field(ge=0.0, le=1.0)
    key_levels: KeyLevels = Field(default_factory=KeyLevels)
    indicators: IndicatorSnapshot = Field(default_factory=IndicatorSnapshot)
    reasoning: str = ""
    price: float | None = None
    generated_at: datetime = Field(default_factory=_utcnow)


class HistoricalReaction(BaseModel):
    """Historically observed move for a symbol around an event."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    percent_move: float


class NewsSignal(BaseModel):
    """Output of the News Monitor agent."""

    model_config = ConfigDict(frozen=True)

    agent: AgentName = AgentName.NEWS_MONITOR
    event: str
    impact: Impact = Impact.LOW
    affected_symbols: tuple[str, ...] = ()
    sentiment: Sentiment = Sentiment.NEUTRAL
    confidence: float = Field(default=0.5, ge=0.0, le=1.0)
    time_until_event: str | None = None
    historical_reaction: tuple[HistoricalReaction, ...] = ()
    alert: AlertLevel = AlertLevel.NONE
    reasoning: str = ""
    generated_at: datetime = Field(default_factory=_utcnow)


class RiskCheck(BaseModel):
    """A single named risk rule evaluation.

    A failed check only vetoes the trade when ``blocking`` is ``True``; the
    remaining checks auto-adjust size/stops or emit warnings.
    """

    model_config = ConfigDict(frozen=True)

    name: str
    passed: bool
    blocking: bool = True
    value: float | None = None
    threshold: float | None = None
    detail: str = ""


class RiskAssessment(BaseModel):
    """Output of the Risk Manager agent. ``approved=False`` is a veto."""

    model_config = ConfigDict(frozen=True)

    agent: AgentName = AgentName.RISK_MANAGER
    symbol: str
    approved: bool
    checks: tuple[RiskCheck, ...] = ()
    position_size: float = Field(default=0.0, ge=0.0)
    leverage: float = Field(default=1.0, ge=0.0)
    stop_loss: float | None = None
    take_profit: float | None = None
    var_95: float | None = None
    reasoning: str = ""
    generated_at: datetime = Field(default_factory=_utcnow)

    @property
    def failed_checks(self) -> tuple[RiskCheck, ...]:
        """Checks that did not pass."""
        return tuple(check for check in self.checks if not check.passed)


class TradeProposal(BaseModel):
    """A candidate trade passed from the decision maker to the risk manager."""

    model_config = ConfigDict(frozen=True)

    symbol: str
    direction: Direction
    entry_price: float = Field(gt=0)
    confidence: float = Field(ge=0.0, le=1.0)
    requested_size: float = Field(default=0.0, ge=0.0)
    timeframe: Timeframe
    rationale: str = ""


class TradeDecision(BaseModel):
    """Final output of the Decision Maker agent."""

    model_config = ConfigDict(frozen=True)

    agent: AgentName = AgentName.DECISION_MAKER
    symbol: str
    decision: Decision
    final_score: float = Field(ge=0.0, le=1.0)
    technical_score: float = Field(ge=0.0, le=1.0)
    news_score: float = Field(ge=0.0, le=1.0)
    risk_score: float = Field(ge=0.0, le=1.0)
    risk_approved: bool = False
    position_size: float = 0.0
    entry_price: float | None = None
    stop_loss: float | None = None
    take_profit: float | None = None
    reasoning: str = ""
    executed: bool = False
    order_id: str | None = None
    generated_at: datetime = Field(default_factory=_utcnow)
