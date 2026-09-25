"""Tests for the Risk Manager agent, VaR calculator and position sizer."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from agents.risk_manager.agent import RiskContext, RiskManagerAgent
from agents.risk_manager.position_sizer import kelly_criterion, plan_position
from agents.risk_manager.var_calculator import (
    conditional_var,
    historical_var,
    max_pairwise_correlation,
    parametric_var,
)
from shared.schemas.enums import Direction, Timeframe
from shared.schemas.signals import TradeProposal


@pytest.fixture
def returns() -> np.ndarray:
    rng = np.random.default_rng(3)
    return rng.normal(0.0, 0.01, 500)


def make_proposal(confidence: float = 0.7) -> TradeProposal:
    return TradeProposal(
        symbol="XAUUSD",
        direction=Direction.BULLISH,
        entry_price=2650.0,
        confidence=confidence,
        timeframe=Timeframe.H1,
    )


def test_historical_var_is_positive_and_ordered(returns: np.ndarray) -> None:
    var95 = historical_var(returns, 0.95)
    var99 = historical_var(returns, 0.99)
    assert var95 > 0
    assert var99 >= var95


def test_conditional_var_at_least_var(returns: np.ndarray) -> None:
    assert conditional_var(returns, 0.95) >= historical_var(returns, 0.95)


def test_parametric_var_positive(returns: np.ndarray) -> None:
    assert parametric_var(returns, 0.95) > 0


def test_historical_var_empty_is_zero() -> None:
    assert historical_var(np.array([])) == 0.0


def test_max_pairwise_correlation() -> None:
    frame = pd.DataFrame({"a": [1, 2, 3, 4], "b": [2, 4, 6, 8], "c": [4, 3, 2, 1]})
    assert max_pairwise_correlation(frame) == pytest.approx(1.0)
    assert max_pairwise_correlation(pd.DataFrame({"a": [1, 2, 3]})) == 0.0


def test_kelly_criterion_bounds() -> None:
    assert kelly_criterion(0.5, 2.0) == pytest.approx(0.25)
    assert kelly_criterion(0.3, 2.0) == 0.0  # negative edge clamps to zero
    with pytest.raises(ValueError):
        kelly_criterion(1.5, 2.0)
    with pytest.raises(ValueError):
        kelly_criterion(0.5, 0.0)


def test_plan_position_bullish_stops() -> None:
    plan = plan_position(
        equity=100_000, price=2650.0, atr=10.0, confidence=0.7, direction=Direction.BULLISH
    )
    assert plan.quantity > 0
    assert plan.stop_loss < 2650.0 < plan.take_profit
    assert plan.allocation <= 0.5 + 1e-9


def test_plan_position_bearish_stops() -> None:
    plan = plan_position(
        equity=100_000, price=2650.0, atr=10.0, confidence=0.7, direction=Direction.BEARISH
    )
    assert plan.stop_loss > 2650.0 > plan.take_profit


def test_plan_position_rejects_neutral() -> None:
    with pytest.raises(ValueError, match="NEUTRAL"):
        plan_position(
            equity=100_000, price=100.0, atr=1.0, confidence=0.5, direction=Direction.NEUTRAL
        )


def test_plan_position_caps_risk_per_trade() -> None:
    plan = plan_position(
        equity=100_000,
        price=100.0,
        atr=50.0,
        confidence=0.99,
        direction=Direction.BULLISH,
        max_risk_per_trade=0.01,
    )
    assert plan.risk_amount <= 100_000 * 0.01 + 1e-6


async def test_risk_manager_approves_healthy_trade(returns: np.ndarray) -> None:
    agent = RiskManagerAgent()
    context = RiskContext(equity=100_000, peak_equity=100_000, atr=10.0, recent_returns=returns)
    assessment = await agent.assess(make_proposal(), context)
    assert assessment.approved is True
    assert assessment.position_size > 0
    assert assessment.stop_loss is not None
    assert all(check.passed for check in assessment.checks)


async def test_risk_manager_vetoes_on_drawdown(returns: np.ndarray) -> None:
    agent = RiskManagerAgent()
    context = RiskContext(equity=90_000, peak_equity=100_000, atr=10.0, recent_returns=returns)
    assessment = await agent.assess(make_proposal(), context)
    assert assessment.approved is False
    assert any(check.name == "max_drawdown" and not check.passed for check in assessment.checks)
    assert assessment.reasoning.startswith("VETO")


async def test_risk_manager_correlation_is_warning_only(returns: np.ndarray) -> None:
    agent = RiskManagerAgent()
    context = RiskContext(
        equity=100_000,
        peak_equity=100_000,
        atr=10.0,
        recent_returns=returns,
        correlation=0.95,
    )
    assessment = await agent.assess(make_proposal(), context)
    assert assessment.approved is True
    correlation_check = next(c for c in assessment.checks if c.name == "correlation")
    assert correlation_check.passed is False
    assert correlation_check.blocking is False


async def test_risk_manager_widens_stop_on_atr_spike(returns: np.ndarray) -> None:
    agent = RiskManagerAgent()
    context = RiskContext(
        equity=100_000,
        peak_equity=100_000,
        atr=30.0,
        atr_baseline=10.0,
        recent_returns=returns,
    )
    assessment = await agent.assess(make_proposal(), context)
    volatility = next(c for c in assessment.checks if c.name == "volatility_atr")
    assert "widened" in volatility.detail
