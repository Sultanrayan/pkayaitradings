"""Risk Manager agent.

Evaluates a :class:`TradeProposal` against the configured risk limits and
returns a :class:`RiskAssessment`. A failed *blocking* check is a veto; the
remaining checks auto-adjust size, stops or leverage.
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
        approved = drawdown_check.passed and not no_size

        reasoning = await self.narrator.narrate(
            {
                "symbol": proposal.symbol,
                "approved": approved,
                "allocation": round(plan.allocation, 6),
                "position_size": plan.quantity,
                "stop_loss": plan.stop_loss,
                "take_profit": plan.take_profit,
                "var_95": round(var_value, 6),
                "checks": [check.model_dump() for check in checks],
                "reasoning": _reason(checks, no_size),
            }
        )
        self.log.info(
            "risk_manager.assessment",
            symbol=proposal.symbol,
            approved=approved,
            allocation=plan.allocation,
            drawdown=round(context.drawdown_pct, 4),
        )
        return RiskAssessment(
            symbol=proposal.symbol,
            approved=approved,
            checks=tuple(checks),
            position_size=plan.quantity,
            leverage=round(1.0 / plan.allocation, 4) if plan.allocation > 0 else 1.0,
            stop_loss=plan.stop_loss,
            take_profit=plan.take_profit,
            var_95=round(var_value, 6),
            reasoning=reasoning,
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
