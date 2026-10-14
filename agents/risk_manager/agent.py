"""Risk Manager agent.

Evaluates a :class:`TradeProposal` against the configured risk limits and
returns a :class:`RiskAssessment`.

There is exactly one veto: the portfolio **drawdown** limit. Everything else —
volatility, correlation, VaR, a Kelly allocation that rounds to zero — is
expressed as a size and a stop adjustment. A risk manager that answers "not now"
has delegated its judgement to nobody, so it answers with a smaller position
instead.

The drawdown veto is deliberately *not* converted into a smaller size. A system
that keeps opening quarter-size positions while it is losing money at its maximum
tolerance does not have a maximum drawdown limit; it has a slower bleed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from agents.base_agent import BaseAgent
from agents.risk_manager.narrator import RiskNarrator, build_risk_narrator
from agents.risk_manager.position_sizer import plan_position
from agents.risk_manager.var_calculator import historical_var
from shared.order_flow import OrderFlowSignal
from shared.schemas.enums import AgentName
from shared.schemas.messages import Position
from shared.schemas.signals import RiskAssessment, RiskCheck, TradeProposal

_ATR_SPIKE_MULTIPLIER = 1.5
_ATR_FALLBACK_PCT = 0.002

#: Multipliers applied to the computed allocation by regime. Keyed by the
#: qualitative regime rather than by a raw threshold so the policy is readable in
#: one place.
SIZE_MULTIPLIERS: dict[str, float] = {
    "high": 0.25,
    "elevated": 0.50,
    "normal": 1.00,
    "low": 1.00,
}

#: Multipliers applied to the stop distance. A wider stop under high volatility
#: avoids being noise-stopped; a tighter stop under low volatility avoids paying
#: for risk that is not there. Never zero — a zero stop is not a small stop.
SL_ADJUSTMENTS: dict[str, float] = {
    "high": 1.5,
    "elevated": 1.2,
    "normal": 1.0,
    "low": 0.8,
}


def risk_regime(
    *, drawdown_pct: float, atr: float, atr_baseline: float | None, correlation: float | None
) -> str:
    """Classify portfolio and market risk into a named regime.

    Args:
        drawdown_pct: Current drawdown as a positive fraction.
        atr: Live ATR.
        atr_baseline: Trailing ATR baseline, or ``None`` when unavailable.
        correlation: Absolute portfolio correlation, or ``None``.

    Returns:
        One of ``high``, ``elevated``, ``normal`` or ``low``.
    """
    if drawdown_pct >= 0.10:
        return "high"
    volatility_spike = (
        atr_baseline is not None and atr_baseline > 0 and atr > atr_baseline * _ATR_SPIKE_MULTIPLIER
    )
    if drawdown_pct >= 0.05 or volatility_spike:
        return "elevated"
    if volatility_spike is False and atr > 0 and atr_baseline and atr < atr_baseline * 0.6:
        return "low"
    return "normal"


@dataclass(frozen=True)
class RiskContext:
    """Portfolio and market state needed to evaluate a proposal."""

    equity: float
    peak_equity: float
    atr: float
    recent_returns: pd.Series | np.ndarray = field(default_factory=lambda: np.array([]))
    correlation: float | None = None
    atr_baseline: float | None = None
    open_positions: tuple[Position, ...] = ()
    order_flow: OrderFlowSignal | None = None
    hmm_features: np.ndarray | None = None

    @property
    def drawdown_pct(self) -> float:
        """Current drawdown from peak equity as a positive fraction."""
        if self.peak_equity <= 0:
            return 0.0
        return max(0.0, (self.peak_equity - self.equity) / self.peak_equity)

    @property
    def gross_exposure(self) -> float:
        """Sum of open position notionals."""
        return sum(position.quantity * position.entry_price for position in self.open_positions)


class RiskManagerAgent(BaseAgent):
    """Enforces portfolio risk limits and holds veto power.

    Args:
        bus: Optional message bus.
        settings: Optional settings override.
    """

    name = AgentName.RISK_MANAGER

    def __init__(
        self,
        *,
        narrator: RiskNarrator | None = None,
        **kwargs: Any,
    ) -> None:
        super().__init__(**kwargs)
        self.narrator = narrator or build_risk_narrator(self.settings)

    async def assess(
        self,
        proposal: TradeProposal,
        context: RiskContext,
    ) -> RiskAssessment:
        """Evaluate ``proposal`` against the risk limits.

        Returns:
            A :class:`RiskAssessment`; ``approved`` is ``False`` when any
            blocking check fails, which vetoes the trade.
        """
        settings = self.settings
        checks: list[RiskCheck] = []

        drawdown_check = _check_drawdown(context, settings.max_drawdown_pct)
        checks.append(drawdown_check)

        atr = context.atr if context.atr > 0 else proposal.entry_price * _ATR_FALLBACK_PCT
        var_value = historical_var(context.recent_returns, settings.var_confidence)
        var_cap = settings.var_limit_pct / var_value if var_value > 0 else float("inf")
        effective_max_position = min(settings.max_position_size, var_cap)

        atr_stop_mult, volatility_check = _volatility_guard(context, atr)
        checks.append(volatility_check)

        plan = plan_position(
            equity=context.equity,
            price=proposal.entry_price,
            atr=atr,
            confidence=proposal.confidence,
            direction=proposal.direction,
            kelly_fraction=settings.kelly_fraction,
            atr_stop_mult=atr_stop_mult,
            max_position_fraction=effective_max_position,
            max_risk_per_trade=settings.max_position_size * 0.1,
        )

        position_check = RiskCheck(
            name="position_size",
            passed=plan.allocation <= settings.max_position_size + 1e-9,
            blocking=False,
            value=round(plan.allocation, 6),
            threshold=settings.max_position_size,
            detail=f"Kelly fraction {plan.kelly:.3f}, notional {plan.notional:.2f}",
        )
        checks.append(position_check)

        position_var = plan.allocation * var_value
        var_check = RiskCheck(
            name="var_95",
            passed=position_var <= settings.var_limit_pct + 1e-9,
            blocking=False,
            value=round(position_var, 6),
            threshold=settings.var_limit_pct,
            detail=f"1-day {settings.var_confidence:.0%} VaR on position",
        )
        checks.append(var_check)

        checks.append(_check_correlation(context, settings.correlation_warn_threshold))

        no_size = plan.quantity <= 0

        # Regime drives both the size and the stop. Computed before the veto so
        # the assessment can still explain itself when the veto fires.
        regime = risk_regime(
            drawdown_pct=context.drawdown_pct,
            atr=atr,
            atr_baseline=context.atr_baseline,
            correlation=context.correlation,
        )
        size_multiplier = SIZE_MULTIPLIERS[regime]
        sl_adjustment = SL_ADJUSTMENTS[regime]

        # --- The one veto: portfolio drawdown. ---
        #
        # Deliberately not softened into a smaller size. Every other condition
        # that used to produce ``approved=False`` now produces a scaled position.
        approved = drawdown_check.passed

        if not approved:
            quantity = 0.0
        else:
            floor_qty = _floor_quantity(context.equity, proposal.entry_price)
            quantity = max(plan.quantity * size_multiplier, floor_qty)

        reasoning = await self.narrator.narrate(
            {
                "symbol": proposal.symbol,
                "approved": approved,
                "allocation": round(plan.allocation, 6),
                "position_size": quantity,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "var_95": round(var_value, 6),
                "regime": regime,
                "size_multiplier": size_multiplier,
                "sl_adjustment": sl_adjustment,
                "checks": [check.model_dump() for check in checks],
                "reasoning": _reason(checks, no_size),
            }
        )
        self.log.info(
            "risk_manager.assessment",
            symbol=proposal.symbol,
            approved=approved,
            regime=regime,
            allocation=plan.allocation,
            position_size=quantity,
            size_multiplier=size_multiplier,
            drawdown=round(context.drawdown_pct, 4),
        )
        return RiskAssessment(
            symbol=proposal.symbol,
            approved=approved,
            checks=tuple(checks),
            position_size=quantity,
            leverage=round(1.0 / plan.allocation, 4) if plan.allocation > 0 else 1.0,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            var_95=round(var_value, 6),
            reasoning=reasoning,
            position_size_multiplier=size_multiplier,
            sl_adjustment=sl_adjustment,
            risk_notes=_risk_notes(
                regime=regime,
                context=context,
                atr=atr,
                checks=checks,
                size_multiplier=size_multiplier,
                sl_adjustment=sl_adjustment,
            ),
            invalidation=_invalidation(plan.stop_loss, atr, sl_adjustment),
        )

    async def run(
        self,
        proposal: TradeProposal,
        context: RiskContext,
        *,
        correlation_id: str | None = None,
    ) -> RiskAssessment:
        """Assess ``proposal`` and publish the resulting assessment."""
        assessment = await self._guarded(RiskAssessment, self.assess, proposal, context)
        await self.publish(assessment, kind="risk_assessment", correlation_id=correlation_id)
        return assessment


def _floor_quantity(equity: float, price: float) -> float:
    """Smallest non-zero position, so a weak call still has a size.

    A zero-Kelly allocation used to mean "no trade". It now means "the smallest
    trade the account can express", because refusing to size is the same as
    refusing to decide — and the decision maker has already made one.

    Sized as a small fraction of equity rather than an absolute unit count, so it
    behaves the same on a 1k account and a 100k account.
    """
    if equity <= 0 or price <= 0:
        return 0.0
    return (equity * 0.001) / price


def _risk_notes(
    *,
    regime: str,
    context: RiskContext,
    atr: float,
    checks: list[RiskCheck],
    size_multiplier: float,
    sl_adjustment: float,
) -> str:
    """What could go wrong, from live risk state rather than boilerplate."""
    notes: list[str] = []

    if context.drawdown_pct > 0:
        notes.append(f"Drawdown {context.drawdown_pct:.2%}")
    if regime in {"high", "elevated"}:
        notes.append(
            f"Risk regime {regime}: size cut to {size_multiplier:.2f}x, "
            f"stop widened {sl_adjustment:.2f}x"
        )
    if regime == "low":
        notes.append(f"Compressed volatility: stop tightened to {sl_adjustment:.2f}x ATR")
    if context.correlation is not None and abs(context.correlation) > 0.6:
        notes.append(
            f"Portfolio correlation {context.correlation:+.2f} — positions move together"
        )
    if context.atr_baseline and atr > 0:
        ratio = atr / context.atr_baseline
        if ratio > _ATR_SPIKE_MULTIPLIER:
            notes.append(f"ATR {ratio:.2f}x its baseline — expect noise inside the stop")
        elif ratio < 0.6:
            notes.append(f"ATR only {ratio:.2f}x baseline — quiet tape, breakout risk")

    for check in checks:
        if not check.passed and check.blocking:
            notes.append(f"BLOCKING: {check.detail}")
        elif not check.passed:
            notes.append(f"Warning: {check.detail}")

    if not notes:
        return "No active risk conditions; all checks passed at normal size."
    return "; ".join(notes) + "."


def _invalidation(stop_loss: float | None, atr: float, sl_adjustment: float) -> str:
    """The condition that cancels the trade, from the stop and ATR."""
    parts: list[str] = []
    if stop_loss is not None and stop_loss > 0:
        parts.append(f"Stop at {stop_loss:.2f} is hit")
    if atr > 0:
        parts.append(f"or a {atr * sl_adjustment:.2f} adverse move (ATR x {sl_adjustment:.2f})")
    parts.append("or the drawdown limit being reached")
    return ", ".join(parts) + "."


def _check_drawdown(context: RiskContext, limit: float) -> RiskCheck:
    drawdown = context.drawdown_pct
    return RiskCheck(
        name="max_drawdown",
        passed=drawdown <= limit,
        blocking=True,
        value=round(drawdown, 6),
        threshold=limit,
        detail=f"Drawdown {drawdown:.2%} vs limit {limit:.2%}",
    )


def _check_correlation(context: RiskContext, threshold: float) -> RiskCheck:
    correlation = abs(context.correlation) if context.correlation is not None else 0.0
    return RiskCheck(
        name="correlation",
        passed=correlation <= threshold,
        blocking=False,
        value=round(correlation, 4),
        threshold=threshold,
        detail="Portfolio correlation warning"
        if correlation > threshold
        else "Correlation within limits",
    )


def _volatility_guard(context: RiskContext, atr: float) -> tuple[float, RiskCheck]:
    """Return the ATR stop multiple, widening it when volatility spikes."""
    baseline = context.atr_baseline
    spike = baseline is not None and baseline > 0 and atr > baseline * _ATR_SPIKE_MULTIPLIER
    check = RiskCheck(
        name="volatility_atr",
        passed=True,
        blocking=False,
        value=round(atr, 6),
        threshold=round(baseline, 6) if baseline else None,
        detail=(
            "ATR spike detected - stop widened to 3x ATR"
            if spike
            else "Volatility within normal range"
        ),
    )
    return (3.0 if spike else 2.0), check


def _reason(checks: list[RiskCheck], no_size: bool) -> str:
    if no_size:
        return "VETO: computed position size is zero"
    failed = [check for check in checks if not check.passed]
    blocking = [check for check in failed if check.blocking]
    if blocking:
        return "VETO: " + "; ".join(check.detail for check in blocking)
    if failed:
        return "APPROVED with warnings: " + "; ".join(check.detail for check in failed)
    return "APPROVED: all risk checks passed"
