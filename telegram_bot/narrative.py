"""Derive the four narrative fields from the bot's own indicator data.

**This module has no relationship to the four-agent AI system.** The bot in
``telegram_bot/`` is a separate engine: it reads biquote OHLCV, keeps its own
SQLite database, and computes its own seven-layer signal. It never imports
``agents``, ``orchestrator``, or any agent schema, and nothing here does either.
``tests/test_bot_imports.py`` enforces that structurally.

Everything below is derived from the bot's own seven layers, its own ATR-derived
levels and its own structural levels:

* ``strength`` — banded from the bot's own weighted confidence.
* ``recommendation`` — the bot's direction and the size that band implies.
* ``explanation`` — the layer scores that produced the signal, with each layer's
  own ``detail`` string so the text names what actually fired.
* ``risk_notes`` — counter-signals the bot can see for itself: disagreement
  between layers, an exhausted move, an extreme imbalance, a wide stop.
* ``invalidation`` — the bot's own stop, and the nearest structural level from its
  swing/fibonacci work.
"""

from __future__ import annotations

from typing import Any

__all__ = [
    "STRONG_CONFIDENCE",
    "WEAK_CONFIDENCE",
    "band_strength",
    "build_explanation",
    "build_invalidation",
    "build_recommendation",
    "build_risk_notes",
    "position_size_for",
]

#: Band edges, matching the AI system's ``Strength`` thresholds so a user reading
#: both surfaces sees the same word for the same number. Defined locally rather
#: than imported: sharing the enum would be exactly the schema coupling this
#: module exists to avoid.
WEAK_CONFIDENCE = 0.30
STRONG_CONFIDENCE = 0.70

#: Position size per band. A weak call is still shown, at a size that reflects
#: how little there is behind it.
_SIZES = {"WEAK": 0.25, "MODERATE": 0.60, "STRONG": 1.00}


def band_strength(confidence: float) -> str:
    """Band the bot's own confidence into WEAK / MODERATE / STRONG.

    Args:
        confidence: The bot's weighted confidence in ``[0, 1]``.

    Returns:
        ``WEAK`` below 0.30, ``MODERATE`` up to 0.70, ``STRONG`` above.
    """
    value = max(0.0, min(1.0, float(confidence)))
    if value < WEAK_CONFIDENCE:
        return "WEAK"
    if value <= STRONG_CONFIDENCE:
        return "MODERATE"
    return "STRONG"


def position_size_for(strength: str) -> float:
    """Recommended size for a band."""
    return _SIZES.get(strength, 0.25)


def _pct(score: float | None) -> int:
    """Layer score as a 0-100 display percentage."""
    if score is None:
        return 0
    return round(min(1.0, abs(float(score))) * 100)


def build_recommendation(action: str, strength: str, confidence: float) -> str:
    """Actionable advice naming the direction, the band and the size."""
    size = position_size_for(strength)
    side = "long" if action == "BUY" else "short"
    band = strength or "UNBANDED"
    if strength == "STRONG":
        return (
            f"Enter {side} at full size ({size:.2f}). Strength {band}. "
            f"Confidence {confidence:.2f}."
        )
    if strength == "MODERATE":
        return (
            f"Enter {side} at {size:.2f} size. Strength {band}. "
            f"Confidence {confidence:.2f}."
        )
    return (
        f"Weak {side} lean — {size:.2f} size only, or wait for a confirming close. "
        f"Strength {band}. Confidence {confidence:.2f}."
    )


def build_explanation(
    *,
    action: str,
    confidence: float,
    layers: dict[str, float],
    details: dict[str, str],
    evaluable: dict[str, bool],
) -> str:
    """Name each layer that fired, with its own detail string.

    Only evaluable layers are listed. A layer that abstained has no opinion, and
    claiming it agreed would overstate the evidence.
    """
    fired: list[str] = []
    for name, score in layers.items():
        if not evaluable.get(name, True):
            continue
        detail = details.get(name, "").strip()
        label = name.replace("_", " ").title()
        if detail:
            fired.append(f"{label} {_pct(score)}% ({detail})")
        else:
            fired.append(f"{label} {_pct(score)}%")

    direction = "bullish" if action == "BUY" else "bearish"
    head = f"{direction} signal at weighted confidence {confidence:.2f}."
    if fired:
        return head + " " + ", ".join(fired) + "."
    return head + " No layer produced an evaluable reading."


def build_risk_notes(
    *,
    action: str,
    layers: dict[str, float],
    details: dict[str, str],
    order_flow: Any,
    sl: float,
    entry: float,
) -> str:
    """Counter-signals the bot can observe for itself.

    Every condition here is measurable from the bot's own frame: layer
    disagreement, an over-extended move, an extreme order-flow imbalance, or a
    stop that sits an unusual distance away. Nothing is invented, and a clean
    result says so rather than padding with "none".
    """
    notes: list[str] = []

    # 1. Layers voting against the trade.
    against: list[str] = []
    for name, score in layers.items():
        if abs(float(score)) < 1e-9:
            continue
        if (action == "BUY" and score < 0) or (action == "SELL" and score > 0):
            against.append(name.replace("_", " ").title())
    if against:
        notes.append(f"counter-signal: {', '.join(sorted(against))} disagree with the trade")

    # 2. Weak trend — read from the trend layer's own detail, not recomputed.
    trend_detail = details.get("trend", "")
    if "weak" in trend_detail.lower() or "no trend" in trend_detail.lower():
        notes.append(trend_detail)

    # 3. Over-extended price.
    momentum_detail = details.get("momentum", "").lower()
    if "overbought" in momentum_detail or "oversold" in momentum_detail:
        notes.append(details.get("momentum", ""))

    # 4. Order-flow extremes.
    imbalance = getattr(order_flow, "imbalance_ratio", 1.0)
    try:
        imbalance_value = float(imbalance)
    except (TypeError, ValueError):
        imbalance_value = 1.0
    if imbalance_value not in (1.0,) and (
        imbalance_value >= 3.0 or (0 < imbalance_value <= 1 / 3)
    ):
        notes.append(
            f"order-flow imbalance {imbalance_value:.1f}:1 — a crowded one-sided book "
            "unwinds violently"
        )

    # 5. A stop far from entry in relative terms.
    distance = abs(entry - sl)
    if entry > 0 and distance / entry > 0.02:
        notes.append(
            f"stop is {distance / entry:.2%} from entry — wide, so size should be small"
        )

    if not notes:
        return "No counter-signals detected across the seven layers."
    return "; ".join(notes) + "."


def build_invalidation(
    *,
    action: str,
    entry: float,
    sl: float,
    structure: float | None = None,
    atr: float | None = None,
    timeframe: str = "",
) -> str:
    """The price level and condition that cancels the signal.

    Built from the bot's own stop and its own structural level, so it stays true
    even if the stop is later moved.
    """
    parts: list[str] = []
    if action == "BUY":
        parts.append(f"close below the stop at {sl:.2f}")
    else:
        parts.append(f"close above the stop at {sl:.2f}")

    if structure is not None and structure > 0:
        if action == "BUY" and structure < entry:
            parts.append(f"or loss of support at {structure:.2f}")
        elif action == "SELL" and structure > entry:
            parts.append(f"or loss of resistance at {structure:.2f}")

    if atr is not None and atr > 0:
        parts.append(f"or a {atr:.2f} adverse move (1 ATR)")

    suffix = f" on {timeframe.upper()}" if timeframe else ""
    return ", ".join(parts) + f", or the signal lapsing after 3 closed candles{suffix}."
