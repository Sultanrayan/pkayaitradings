"""Position sizing and stop placement for the Risk Manager.

Sizing follows the documented ``Kelly x 0.25`` rule, then applies two hard caps:

1. notional exposure may not exceed ``max_position_fraction`` of equity;
2. the capital at risk to the ATR stop may not exceed ``max_risk_per_trade``.
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.schemas.enums import Direction

#: Smallest allocation expressed as a fraction of equity, used when Kelly returns
#: zero. A tenth of a percent is small enough to be irrelevant and large enough
#: that the position is real.
_MIN_ALLOCATION = 0.001


@dataclass(frozen=True)
class PositionPlan:
    """A concrete, risk-bounded trade plan."""

    quantity: float
    notional: float
    allocation: float
    stop_loss: float
    take_profit: float
    risk_amount: float
    kelly: float


def kelly_criterion(win_prob: float, reward_risk: float) -> float:
    """Fractional Kelly fraction for a binary bet, clamped to ``[0, 1]``.

    Args:
        win_prob: Probability of a win in ``[0, 1]``.
        reward_risk: Reward-to-risk ratio (e.g. ``2.0`` for 2:1).
    """
    if not 0.0 <= win_prob <= 1.0:
        raise ValueError("win_prob must be within [0, 1]")
    if reward_risk <= 0:
        raise ValueError("reward_risk must be positive")
    edge = win_prob - (1.0 - win_prob) / reward_risk
    return max(0.0, min(1.0, edge))


def plan_position(
    *,
    equity: float,
    price: float,
    atr: float,
    confidence: float,
    direction: Direction,
    kelly_fraction: float = 0.25,
    atr_stop_mult: float = 2.0,
    reward_risk: float = 2.0,
    max_position_fraction: float = 0.5,
    max_risk_per_trade: float = 0.02,
) -> PositionPlan:
    """Compute a risk-bounded position plan.

    Args:
        equity: Account equity in quote currency.
        price: Entry price.
        atr: Average True Range used for stop distance.
        confidence: Model confidence used as the win probability.
        direction: Trade direction. ``NEUTRAL`` is accepted and mapped to the bearish
            geometry, because the agents no longer emit it and a sizer that
            refuses to size a neutral direction would turn a labelling gap into a
            crash.
        kelly_fraction: Fraction of full Kelly to allocate.
        atr_stop_mult: ATR multiple for the stop distance.
        reward_risk: Take-profit distance as a multiple of stop distance.
        max_position_fraction: Cap on notional exposure as a fraction of equity.
        max_risk_per_trade: Cap on capital at risk as a fraction of equity.

    Raises:
        ValueError: On non-positive equity, price or ATR. These are data faults
            rather than trading judgements — there is no meaningful position size
            without them, and guessing one would put real money at risk on a
            number invented at runtime.
    """
    if equity <= 0:
        raise ValueError("equity must be positive")
    if price <= 0:
        raise ValueError("price must be positive")
    if atr <= 0:
        raise ValueError("atr must be positive")

    kelly = kelly_criterion(confidence, reward_risk)
    allocation = min(kelly * kelly_fraction, max_position_fraction)

    stop_distance = atr * atr_stop_mult
    quantity = (equity * allocation) / price

    max_risk_amount = equity * max_risk_per_trade
    risk_amount = quantity * stop_distance
    if risk_amount > max_risk_amount and stop_distance > 0:
        quantity = max_risk_amount / stop_distance
        risk_amount = max_risk_amount

    # A Kelly allocation of zero (a coin-flip confidence) used to produce a zero
    # quantity, which the caller read as "no trade". Floor it at a small
    # fraction of equity so a weak call is still expressible; the caller's
    # strength-based sizing decides how much of it to actually risk.
    if quantity <= 0:
        quantity = (equity * _MIN_ALLOCATION) / price

    notional = quantity * price
    allocation = notional / equity if equity else 0.0

    if direction is Direction.BULLISH:
        stop_loss = price - stop_distance
        take_profit = price + stop_distance * reward_risk
    else:
        stop_loss = price + stop_distance
        take_profit = price - stop_distance * reward_risk

    return PositionPlan(
        quantity=round(quantity, 8),
        notional=round(notional, 2),
        allocation=round(allocation, 6),
        stop_loss=round(stop_loss, 6),
        take_profit=round(take_profit, 6),
        risk_amount=round(risk_amount, 2),
        kelly=round(kelly, 6),
    )
