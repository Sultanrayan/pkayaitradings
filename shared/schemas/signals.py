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
    Strength,
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

    # --- Always-actionable payload ---
    #
    # ``signal`` is always BULLISH or BEARISH. A market with no edge is
    # BULLISH/BEARISH with ``Strength.WEAK`` and low confidence, never
    # ``Direction.NEUTRAL``.
    strength: Strength = Strength.WEAK
    explanation: str = ""
    risk_notes: str = ""
    invalidation: str = ""
    recommendation: str = ""


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

    # --- Always-a-number payload ---
    #
    # ``sentiment_score`` is always populated in ``[-1.0, +1.0]`` and is never
    # ``None``. ``0.0`` means "no news edge", which is a weight of neutral â€” not
    # a reason to withhold a signal. The news monitor never blocks a trade.
    sentiment_score: float = Field(default=0.0, ge=-1.0, le=1.0)
    risk_notes: str = ""


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
    """Output of the Risk Manager agent.

    ``approved=False`` is a veto, and now there is exactly one cause: the
    portfolio **drawdown** limit. That is a loss-limiting control, so it is not
    converted into a smaller position â€” a system that keeps trading through a
    maximum drawdown has no maximum drawdown.

    Every other risk condition is expressed as a *size* and a *stop* adjustment
    instead of a refusal. A risk manager that says "not now" is a risk manager
    that has delegated its judgement to nobody.
    """

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

    # --- Sizing adjustments ---
    #
    # ``position_size_multiplier`` scales the computed allocation:
    # 1.0 normal, 0.25 when risk is high, 0.5 when elevated.
    # ``sl_adjustment`` scales the stop distance: 0.8 tightens it under low
    # volatility, 1.5 widens it under high volatility. It is never 0.
    position_size_multiplier: float = Field(default=1.0, gt=0.0, le=1.0)
    sl_adjustment: float = Field(default=1.0, gt=0.0)
    risk_notes: str = ""
    invalidation: str = ""

    @property
    def failed_checks(self) -> tuple[RiskCheck, ...]:
        """Checks that did not pass."""
        return tuple(check for check in self.checks if not check.passed)

    @property
    def blocking_failures(self) -> tuple[RiskCheck, ...]:
        """Failed checks that actually veto, i.e. the drawdown limit."""
        return tuple(check for check in self.checks if not check.passed and check.blocking)


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
    """Final output of the Decision Maker agent.

    Always actionable: the decision maker publishes ``BUY`` or ``SELL`` on every
    cycle. Weak conviction is expressed through ``strength`` and
    ``position_size``, never by withholding a call.

    The four narrative fields are mandatory and non-empty on every decision:

    * ``recommendation`` â€” what to do, and at what size.
    * ``explanation`` â€” which inputs drove the call and how they combined.
    * ``risk_notes`` â€” the counter-signals and conditions that could break it.
    * ``invalidation`` â€” the specific condition that cancels the signal.

    ``decision`` may still be ``Decision.SKIP`` in exactly one case: the Risk
    Manager's drawdown veto. That is a loss-limiting control rather than a view
    on the market, and it is intentionally not overridden.
    """

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

    # --- Always-actionable payload ---
    #
    # ``entry_price`` is the entry. ``tp1``/``tp2`` are the two targets and
    # ``stop_loss`` the protective stop; all four are populated on every
    # actionable decision so a consumer never has to branch on ``None``.
    tp1: float | None = None
    tp2: float | None = None
    strength: Strength = Strength.WEAK
    recommendation: str = ""
    explanation: str = ""
    risk_notes: str = ""
    invalidation: str = ""

    @property
    def is_actionable(self) -> bool:
        """Whether this decision names a direction and carries complete levels."""
        return self.decision in {Decision.BUY, Decision.SELL} and all(
            level is not None and level > 0
            for level in (self.entry_price, self.tp1, self.tp2, self.stop_loss)
        )

    @property
    def rr_ratio(self) -> float:
        """Reward-to-risk against TP2, or ``0.0`` when levels are incomplete."""
        if not self.is_actionable:
            return 0.0
        entry = float(self.entry_price or 0.0)
        risk = abs(entry - float(self.stop_loss or 0.0))
        if risk <= 0.0:
            return 0.0
        return abs(float(self.tp2 or 0.0) - entry) / risk

