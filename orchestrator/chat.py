"""Market-aware AI chat backing the ``/ai`` page.

The assistant is grounded in data fetched here, server-side, at question time:
the live quote, a recent OHLC window for the requested timeframe, and current
market headlines. The client sends only the question, so it cannot talk the
model into quoting a price or headline that was never retrieved.

Every source is gathered independently. A provider failure degrades that one
section and is reported in ``data_status`` rather than being hidden, so the
model is told what it does *not* have instead of filling the gap itself.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field

from data_pipeline.biquote_client import BiquoteClient
from shared.config import Settings
from shared.llm import build_chat_llm_client
from shared.logging import get_logger
from shared.schemas.enums import Timeframe

__all__ = [
    "ChatMessage",
    "ChatRequest",
    "ChatResponse",
    "ChatUnavailable",
    "MarketContext",
    "answer_question",
]

_logger = get_logger(__name__)

# 200 bars is enough for a stable SMA50 without a large payload per question.
_BAR_LIMIT = 200
_NEWS_LIMIT = 8
_MAX_HISTORY = 10

_SYSTEM_PROMPT = """\
You are the market analyst inside Pkay, an AI market analysis and market \
intelligence platform. You answer questions about live market conditions using \
ONLY the figures and headlines supplied in the user message.

Rules you must follow:
- Ground every number in the supplied data. Never invent, estimate or recall a \
price, level, percentage or headline from memory or from training data.
- If a value you need is absent, or a data source is marked unavailable, say so \
plainly and explain what you can and cannot conclude.
- State the as-of time of the data when it is relevant to your answer.
- You provide analysis and market intelligence, not order execution. Do not \
instruct the user to place, size or time trades, and do not promise or \
guarantee any outcome.
- Distinguish clearly between what the data shows and what you infer from it. \
Label inferences as inference.
- Be concise and concrete. Prefer short paragraphs or tight bullets over \
padding, and do not restate the question back to the user.
"""


class ChatUnavailable(RuntimeError):
    """Raised when no chat model is configured or the provider call fails."""


class ChatMessage(BaseModel):
    """One prior turn supplied by the client for conversational continuity."""

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ChatRequest(BaseModel):
    """A question plus the market it is about."""

    question: str = Field(min_length=1, max_length=2000)
    symbol: str = Field(default="XAUUSD", max_length=24)
    timeframe: Timeframe = Timeframe.H1
    history: list[ChatMessage] = Field(default_factory=list, max_length=24)


class ChatResponse(BaseModel):
    """A grounded answer plus the evidence it was drawn from."""

    answer: str
    model: str
    symbol: str
    timeframe: Timeframe
    as_of: datetime
    data_status: dict[str, str]
    snapshot: dict[str, Any]


class MarketContext(BaseModel):
    """Live facts gathered for a single question, with per-source status."""

    symbol: str
    timeframe: Timeframe
    as_of: datetime
    status: dict[str, str] = Field(default_factory=dict)
    quote: dict[str, Any] | None = None
    technicals: dict[str, Any] | None = None
    news: list[dict[str, Any]] = Field(default_factory=list)

    def render(self) -> str:
        """Serialise the context into the factual block sent to the model."""
        lines: list[str] = [f"SYMBOL: {self.symbol}   TIMEFRAME: {self.timeframe}"]
        lines.append(f"DATA AS OF: {self.as_of.isoformat()}")

        lines.append("")
        lines.append("LIVE QUOTE")
        if self.quote is None:
            lines.append(f"  unavailable ({self.status.get('quote', 'unknown')})")
        else:
            for key, value in self.quote.items():
                lines.append(f"  {key}: {value}")

        lines.append("")
        lines.append("TECHNICALS (derived from the candle window above)")
        if self.technicals is None:
            lines.append(f"  unavailable ({self.status.get('ohlc', 'unknown')})")
        else:
            for key, value in self.technicals.items():
                lines.append(f"  {key}: {value}")

        lines.append("")
        lines.append("CURRENT NEWS HEADLINES")
        if not self.news:
            lines.append(f"  unavailable ({self.status.get('news', 'unknown')})")
        else:
            for item in self.news:
                stamp = item.get("published") or "date unknown"
                lines.append(f"  - [{item['publisher'] or 'unknown'}] {item['title']} ({stamp})")
        return "\n".join(lines)


def _round(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def _sma(closes: list[float], period: int) -> float | None:
    """Simple moving average over the last ``period`` closes."""
    if len(closes) < period:
        return None
    return sum(closes[-period:]) / period


def _technicals(bars: list[Any], timeframe: Timeframe) -> dict[str, Any]:
    """Derive a compact technical snapshot from an oldest-first bar window."""
    closes = [bar.close for bar in bars]
    highs = [bar.high for bar in bars]
    lows = [bar.low for bar in bars]
    last = closes[-1]

    window_change = ((last - closes[0]) / closes[0] * 100) if closes[0] else None
    window_high = max(highs)
    window_low = min(lows)
    span = window_high - window_low
    # Where price sits inside the window's range, 0% = the low, 100% = the high.
    range_position = ((last - window_low) / span * 100) if span else None

    # Stdev of per-bar percentage moves: a volatility read, not an annualised
    # figure, so it is labelled by bar rather than by year.
    moves = [
        (closes[i] - closes[i - 1]) / closes[i - 1] * 100
        for i in range(1, len(closes))
        if closes[i - 1]
    ]
    volatility = statistics.pstdev(moves) if len(moves) > 1 else None

    sma20 = _sma(closes, 20)
    sma50 = _sma(closes, 50)
    # `if sma20` covers both None and a zero average, which would divide by zero.
    sma20_gap = (last - sma20) / sma20 * 100 if sma20 else None

    return {
        "bars": len(bars),
        "last_close": _round(last, 4),
        "window_change_pct": _round(window_change),
        "window_high": _round(window_high, 4),
        "window_low": _round(window_low, 4),
        "range_position_pct": _round(range_position),
        "sma20": _round(sma20, 4),
        "sma50": _round(sma50, 4),
        "price_vs_sma20_pct": _round(sma20_gap),
        "close_above_sma20": None if sma20 is None else last > sma20,
        "close_above_sma50": None if sma50 is None else last > sma50,
        "per_bar_volatility_pct": _round(volatility, 3),
        "last_bar_open_time": bars[-1].open_time.isoformat(),
        "note": f"Derived from the most recent {len(bars)} {timeframe} candles.",
    }


async def gather_market_context(
    client: BiquoteClient,
    symbol: str,
    timeframe: Timeframe,
) -> MarketContext:
    """Fetch quote, candles and news for ``symbol``, tolerating partial failure."""
    context = MarketContext(
        symbol=symbol.upper(),
        timeframe=timeframe,
        as_of=datetime.now(UTC),
    )

    try:
        tick = await client.get_tick(symbol)
        context.quote = {
            "last": _round(tick.mid, 4),
            "bid": _round(tick.bid, 4),
            "ask": _round(tick.ask, 4),
            "spread": _round(tick.spread, 4),
            "session_high": _round(tick.high, 4),
            "session_low": _round(tick.low, 4),
            "day_change_pct": _round(tick.day_diff_percent),
            "session_direction": tick.direction,
            "market_state": str(tick.market_state),
            "quote_timestamp": tick.timestamp.isoformat(),
            "quote_age_seconds": _round(tick.quote_age_seconds, 1),
            "is_stale": tick.stale,
        }
        context.status["quote"] = "ok"
    except Exception as exc:
        context.status["quote"] = f"unavailable: {exc!s}"
        _logger.warning("chat.quote_failed", symbol=symbol, error=repr(exc))

    try:
        series = await client.get_ohlc(symbol, interval=timeframe, limit=_BAR_LIMIT)
        if series.bars:
            context.technicals = _technicals(list(series.bars), timeframe)
            context.status["ohlc"] = "ok"
        else:
            context.status["ohlc"] = "unavailable: provider returned no candles"
    except Exception as exc:
        context.status["ohlc"] = f"unavailable: {exc!s}"
        _logger.warning("chat.ohlc_failed", symbol=symbol, error=repr(exc))

    try:
        articles = await client.get_news(symbol=symbol, max_results=_NEWS_LIMIT)
        context.news = [
            {
                "title": article.title,
                "publisher": article.publisher,
                "published": article.published_date.isoformat() if article.published_date else None,
            }
            for article in articles
        ]
        context.status["news"] = "ok" if context.news else "unavailable: no articles returned"
    except Exception as exc:
        context.status["news"] = f"unavailable: {exc!s}"
        _logger.warning("chat.news_failed", symbol=symbol, error=repr(exc))

    return context


def _build_prompt(request: ChatRequest, context: MarketContext) -> str:
    """Assemble the user-turn prompt from history, live data and the question."""
    parts: list[str] = []

    recent = request.history[-_MAX_HISTORY:]
    if recent:
        transcript = "\n".join(f"{turn.role}: {turn.content}" for turn in recent)
        parts.append(f"EARLIER IN THIS CONVERSATION\n{transcript}")

    parts.append(f"LIVE MARKET DATA\n{context.render()}")

    unavailable = [name for name, value in context.status.items() if value != "ok"]
    if unavailable:
        parts.append(
            "NOTE: the following sources failed to load: "
            + ", ".join(unavailable)
            + ". Do not fill those gaps with remembered or assumed values; tell the "
            "user what is missing."
        )

    parts.append(f"USER QUESTION\n{request.question.strip()}")
    return "\n\n".join(parts)


async def answer_question(
    settings: Settings,
    client: BiquoteClient,
    request: ChatRequest,
) -> ChatResponse:
    """Answer ``request`` with the chat model, grounded in freshly fetched data."""
    llm = build_chat_llm_client(settings)
    if llm is None:
        raise ChatUnavailable(
            "The assistant is not configured: no CHAT_LLM_API_KEY is set on the server."
        )

    context = await gather_market_context(client, request.symbol, request.timeframe)
    answer = await llm.complete(_build_prompt(request, context), system=_SYSTEM_PROMPT)

    return ChatResponse(
        answer=answer.strip(),
        model=llm.model,
        symbol=context.symbol,
        timeframe=context.timeframe,
        as_of=context.as_of,
        data_status=context.status,
        snapshot={
            "quote": context.quote,
            "technicals": context.technicals,
            "news": context.news,
        },
    )
