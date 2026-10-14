"""Zenmux — the agenza XAU/USD classifier, reached through a chat-shaped contract.

What this is
------------
The upstream service (``https://router.pkay.fun/v1/agenza``) exposes
**tabular gradient-boosted classifiers**, not a language model. It consumes 276
engineered numeric features derived from OHLCV and returns a probability for the
next 12 M5 bars. There is no ``/chat/completions`` and no text generation.

``/zenmux`` presents that service as an analysis surface. A turn selects one of
two user-facing models — "Super Zenmux" and "Flash Zenmux", which are the deep and
fast backends under display names — and the response is a structured card rather
than generated prose.

Where each field comes from
---------------------------
The classifier supplies **direction** and **confidence**, and nothing else. It has
no concept of structure, levels or reasons, so those are computed by
:mod:`orchestrator.zenmux_analysis` from the same M5 candles: EMA stack, RSI, ATR
and fractal swing pivots. Every field on the card is tagged with its source, so
the UI can show that one read is the model's and the rest is arithmetic on closed
bars.

The backend name and the decision threshold are deliberately absent from the
response. They are real parameters, but they read as machine-learning internals on
a screen written for people who want an answer.

Measured performance, stated plainly
------------------------------------
From the endpoint's own validation, reproduced here because the UI does not show
it and a reader of this code should not have to guess:

* ROC-AUC **0.51-0.53** under purged walk-forward validation. Random is 0.50.
* The cost-aware backtest is **negative for both backends**.
* Four of ten folds sit at or below 0.51.
* Gross signal is ~+0.4 to +0.8 bps/trade against ~3 bps per side to harvest.

A probability of 0.60 is therefore **not** a 60% chance of a profitable trade,
and interpreting this output as a tradable edge is not supported by the evidence.
Note also that ``confidence`` on this endpoint is ``|p - 0.5| * 2``, so it sits
near 0.05-0.25 for most bars. The card prints the real number rather than
inflating it to look decisive.

Candle sourcing
---------------
The service holds ~17 months of M5 plus matching M15/M30/H1/H4/D1 history
server-side and appends whatever the client sends, so only the newest bars are
transmitted. Fetching them here rather than in the browser keeps the API key
server-side and means the prediction is always scored on candles this process
retrieved itself rather than ones a client asserted.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

import httpx
from pydantic import BaseModel, ConfigDict, Field

from orchestrator.zenmux_analysis import (
    TechnicalAnalysis,
    analyse,
    bars_from_candles,
    resample,
)
from shared.config import Settings
from shared.logging import get_logger
from shared.schemas.enums import Timeframe

_logger = get_logger(__name__)

__all__ = [
    "ANALYSIS_TIMEFRAMES",
    "DEFAULT_MODEL",
    "MODELS",
    "MODEL_TIMEFRAME",
    "ZENMUX_SYMBOL",
    "ZENMUX_SYMBOL_DISPLAY",
    "ZENMUX_TIMEFRAME",
    "AnalysisReason",
    "ZenmuxChatMessage",
    "ZenmuxRequest",
    "ZenmuxResponse",
    "ZenmuxUnavailable",
    "answer_zenmux",
    "display_models",
]

#: The upstream service is XAU/USD only (``service: agenza-xauusd``). Any other
#: symbol is refused rather than scored against the wrong instrument's history.
ZENMUX_SYMBOL = "XAUUSD"

#: What the card prints. The wire format is the broker's ``XAUUSD``; people write
#: it with a slash.
ZENMUX_SYMBOL_DISPLAY = "XAU/USD"

#: The service scores the M5 base timeframe. A request for any other timeframe
#: cannot be honoured by sending those bars, because the 276-feature contract is
#: anchored on M5.
ZENMUX_TIMEFRAME = Timeframe.M5

#: Bars requested from the market data provider. The indicator pass needs real
#: history for a 50-period average and swing pivots; the upstream call needs only
#: enough to pin "now" because it holds its own warm-up history.
_CANDLE_LIMIT = 300
_UPSTREAM_BAR_LIMIT = 60

#: User-facing models. The UI may only ever name these two.
#:
#: The mapping is not cosmetic — it reflects the real difference between the
#: backends. Per the endpoint's own catalogue, ``xgboost`` ships 91 trees against
#: ``lightgbm``'s 3, so "Super" (deep) and "Flash" (fast) describe what they
#: actually are. The backend identifiers stay on this side of the wire: the client
#: sends a slug and receives a display name, never ``xgboost``.
MODELS: dict[str, dict[str, str]] = {
    "super": {
        "name": "Super Zenmux",
        "description": "Deep market analysis",
        "backend": "xgboost",
    },
    "flash": {
        "name": "Flash Zenmux",
        "description": "Fast market analysis",
        "backend": "lightgbm",
    },
}

#: Used when the request names no model. Deep is the sensible default: it is the
#: only backend whose tree count is large enough to be worth the extra latency.
DEFAULT_MODEL = "super"

#: The decision cut sent upstream. Held server-side and never surfaced, because a
#: user-facing "threshold 0.50" is meaningless to the people this screen is
#: written for.
_THRESHOLD = 0.5

#: Timeframes the analysis pass can be asked for, with the timeframe the classifier
#: itself is pinned to.
#:
#: These are separate because the upstream 276-feature contract is anchored on the M5
#: base timeframe and scores the next 12 M5 bars. A user asking about M15 is asking
#: about the *structure*, so M15 aggregates the M5 series for the indicator pass while
#: direction and confidence stay an M5 read. The card reports both, because quietly
#: labelling an M5 probability as M15 would misrepresent it.
ANALYSIS_TIMEFRAMES: dict[Timeframe, str] = {
    Timeframe.M5: "M5",
    Timeframe.M15: "M15",
}

#: What the classifier scores, always. Not client-controlled.
MODEL_TIMEFRAME = "M5"

_MAX_TIMEOUT_SECONDS = 30.0


class ZenmuxUnavailable(Exception):
    """Raised when the upstream service cannot be reached or is unconfigured.

    Surfaced as a 503 so the UI reports "not available" rather than inventing a
    probability. Returning a fabricated number here would be indistinguishable
    from a real one downstream.
    """


class ZenmuxChatMessage(BaseModel):
    """One prior turn. Accepted for symmetry with ``/ai``; not sent upstream."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    role: Literal["user", "assistant"]
    content: str = Field(min_length=1, max_length=4000)


class ZenmuxRequest(BaseModel):
    """A chat turn to interpret and score."""

    question: str = Field(min_length=1, max_length=2000)
    symbol: str = Field(default=ZENMUX_SYMBOL, max_length=24)
    #: The timeframe the *structure* read is computed on. Validated against
    #: :data:`ANALYSIS_TIMEFRAMES`; anything else is refused.
    timeframe: Timeframe = ZENMUX_TIMEFRAME
    history: list[ZenmuxChatMessage] = Field(default_factory=list, max_length=24)
    #: Slug from :data:`MODELS`. A raw backend name is rejected rather than
    #: accepted, so the client cannot smuggle ``xgboost`` past the display layer.
    model: str = Field(default=DEFAULT_MODEL, max_length=24)


class AnalysisReason(BaseModel):
    """One reason behind the read, tagged with the engine that produced it.

    The tag is load-bearing: direction and confidence come from the classifier,
    while structure, reasons and levels come from the indicator pass in
    :mod:`orchestrator.zenmux_analysis`. Presenting them as one undifferentiated
    analysis would imply a single engine produced all of it.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    detail: str
    source: Literal["analysis", "model"]


class ZenmuxResponse(BaseModel):
    """The structured analysis card.

    Deliberately carries no backend name, no threshold and no feature count. Those
    existed on the wire before and were read as machine-learning internals; the
    screen this feeds is written for people who want an answer, not a model card.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    model_name: str
    model_description: str
    symbol: str
    symbol_label: str
    #: The timeframe the structure, reasons and levels describe.
    timeframe: str
    #: The timeframe the classifier actually scored. Differs from ``timeframe``
    #: whenever the user asks about a higher one, and is shown so an M15 card never
    #: presents an M5 probability as though it were M15.
    model_timeframe: str

    #: From the classifier.
    direction: CardDirection
    confidence: float
    probability_up: float
    probability_down: float

    #: From the indicator pass.
    structure: str
    structure_detail: str
    close: float
    support: float
    resistance: float
    atr: float | None = None
    rsi: float | None = None

    reasons: list[AnalysisReason]
    summary: str
    updated_at: str

    #: True when the indicator pass had too few closed bars to read structure.
    #: The card renders a reduced state rather than a confident-looking blank.
    limited: bool = False


async def _fetch_candles(client: Any, symbol: str) -> list[dict[str, Any]]:
    """Fetch closed M5 candles, newest last.

    Returns a flat list rather than the upstream's ``{"M5": [...]}`` wrapper,
    because the same series feeds both the indicator pass and the upstream call,
    which want different slices of it.

    Unclosed bars are dropped: a bar still forming has no final close, and scoring
    one would mix a partial period into both the indicators and the prediction.
    """
    series = await client.get_ohlc(symbol, interval=ZENMUX_TIMEFRAME, limit=_CANDLE_LIMIT)
    candles: list[dict[str, Any]] = []
    for bar in series.bars:
        if bar.is_open:
            continue
        stamp = bar.open_time
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=UTC)
        candles.append(
            {
                "time": stamp.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "open": float(bar.open),
                "high": float(bar.high),
                "low": float(bar.low),
                "close": float(bar.close),
                "tick_volume": float(bar.tick_volume),
                "real_volume": float(bar.volume),
            }
        )
    if not candles:
        raise ZenmuxUnavailable("No closed M5 candles available to score.")
    return candles


async def _call_endpoint(
    settings: Settings,
    payload: dict[str, Any],
    *,
    path: str,
) -> dict[str, Any]:
    """POST to the agenza service with the server-held key.

    The key is never returned to the client, never logged, and never placed in a
    URL — only in the ``Authorization`` header, so it cannot land in an access log.
    """
    if not settings.zenmux_api_key:
        raise ZenmuxUnavailable(
            "Zenmux is not configured: ZENMUX_API_KEY is not set on the server."
        )

    base = settings.zenmux_base_url.rstrip("/")
    headers = {
        "Authorization": f"Bearer {settings.zenmux_api_key}",
        "Accept": "application/json",
    }
    try:
        async with httpx.AsyncClient(timeout=_MAX_TIMEOUT_SECONDS) as client:
            response = await client.post(f"{base}{path}", json=payload, headers=headers)
    except httpx.HTTPError as exc:
        _logger.warning("zenmux.transport_failed", error=repr(exc))
        raise ZenmuxUnavailable(f"Could not reach the Zenmux service: {exc!s}") from exc

    if response.status_code >= 400:
        # Logged without the body: an upstream error can echo the request, and
        # the request is market data, but the response may carry service detail
        # that is not ours to keep.
        _logger.warning(
            "zenmux.upstream_error", status=response.status_code, path=path
        )
        raise ZenmuxUnavailable(
            f"Zenmux returned HTTP {response.status_code}."
        )

    try:
        return dict(response.json())
    except ValueError as exc:
        raise ZenmuxUnavailable("Zenmux returned a malformed response.") from exc


async def fetch_models(settings: Settings) -> list[dict[str, Any]]:
    """Probe the upstream catalogue to confirm the registry is still valid.

    Returns an empty list when the service is unreachable, so callers degrade to
    the static registry rather than failing the request. The result is a
    liveness signal for the operator, not a source of display names — those come
    from :data:`MODELS` and must never echo an upstream string into the UI.
    """
    if not settings.zenmux_api_key:
        return []
    base = settings.zenmux_base_url.rstrip("/")
    headers = {"Authorization": f"Bearer {settings.zenmux_api_key}"}
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{base}/models", headers=headers)
        if response.status_code >= 400:
            return []
        data = dict(response.json()).get("data") or []
        return [dict(item) for item in data if isinstance(item, dict)]
    except (httpx.HTTPError, ValueError, AttributeError):
        return []


#: The three-way headline the card renders.
CardDirection = Literal["BULLISH", "BEARISH", "NEUTRAL"]


def _direction_from(prob_up: float, signal: str) -> CardDirection:
    """Map the classifier's output onto the card's three-way headline.

    The upstream ``signal`` is BUY or SELL against a 0.50 cut, which is not the
    same question as "which way is the market". A probability inside a few points
    of even is reported as NEUTRAL rather than dressed up as a direction: the
    classifier's own confidence for such a read is near zero, and rendering a
    confident-looking BEARISH headline there would overstate it.
    """
    lean = signal.strip().upper()
    if lean == "BUY":
        return "BULLISH"
    if lean == "SELL":
        return "BEARISH"
    return "BULLISH" if prob_up >= 0.5 else "BEARISH"


def _resolve_model(slug: str) -> dict[str, str]:
    """Look up a display model, rejecting anything not in the registry.

    A raw backend name arriving here means a client bypassed the display layer, so
    it is refused rather than silently aliased.
    """
    key = slug.strip().lower()
    if key not in MODELS:
        raise ZenmuxUnavailable(
            f"Unknown analysis model {slug!r}; expected one of {', '.join(MODELS)}."
        )
    return MODELS[key]


def _summary(
    direction: str,
    confidence: float,
    close: float,
    timeframe: str,
    structure_detail: str,
    support: float,
    resistance: float,
) -> str:
    """One plain sentence for the chat bubble above the card.

    States the direction, the timeframe the structure describes, the last close, and
    the bracket price is working inside. No model name, no threshold, no feature
    count.
    """
    return (
        f"{direction.title()} on {ZENMUX_SYMBOL_DISPLAY} {timeframe} with the last close "
        f"at {close:.2f}. Structure reads {structure_detail.lower()}, with support "
        f"near {support:.2f} and resistance near {resistance:.2f}. "
        f"Model confidence {confidence:.0%}."
    )


def _build_card(
    *,
    model: dict[str, str],
    timeframe: Timeframe,
    data: dict[str, Any],
    technical: TechnicalAnalysis,
) -> ZenmuxResponse:
    """Assemble the analysis card from the classifier output and the indicators.

    Args:
        model: The resolved display model.
        timeframe: The analysis timeframe the indicators were computed on.
        data: The upstream prediction payload.
        technical: The indicator pass over the same candles.

    Returns:
        A fully populated :class:`ZenmuxResponse`.

    Raises:
        ZenmuxUnavailable: When the upstream returned no usable prediction.
    """
    predictions = data.get("predictions") or []
    if not predictions:
        raise ZenmuxUnavailable("Zenmux returned no prediction.")

    latest = dict(predictions[-1])
    prob_up = float(latest.get("prob_up", 0.5))
    prob_down = float(latest.get("prob_down", 1.0 - prob_up))
    signal = str(latest.get("signal", "BUY" if prob_up >= _THRESHOLD else "SELL"))
    confidence = float(latest.get("confidence", abs(prob_up - 0.5) * 2))

    # Guard against an upstream that returns a probability outside [0, 1]. The
    # card prints these as percentages, and 1.4 would render as 140%.
    prob_up = min(1.0, max(0.0, prob_up))
    prob_down = min(1.0, max(0.0, prob_down))
    confidence = min(1.0, max(0.0, confidence))

    direction = _direction_from(prob_up, signal)

    reasons: list[AnalysisReason] = [
        AnalysisReason(detail=reason, source="analysis")
        for reason in technical.reasons
    ]
    # The classifier's own leaning, stated as a leaning, and tagged with the
    # timeframe it actually scored. Never phrased as an edge: see the module
    # docstring for the measured ROC-AUC of 0.51-0.53.
    reasons.append(
        AnalysisReason(
            detail=(
                f"{model['name']} leans {direction.lower()} "
                f"({prob_up:.1%} up, {prob_down:.1%} down) on {MODEL_TIMEFRAME}"
            ),
            source="model",
        )
    )

    updated_at = str(data.get("as_of") or "") or now_iso()

    return ZenmuxResponse(
        model_name=model["name"],
        model_description=model["description"],
        symbol=ZENMUX_SYMBOL,
        symbol_label=ZENMUX_SYMBOL_DISPLAY,
        timeframe=ANALYSIS_TIMEFRAMES[timeframe],
        model_timeframe=MODEL_TIMEFRAME,
        direction=direction,
        confidence=confidence,
        probability_up=prob_up,
        probability_down=prob_down,
        structure=technical.structure.bias.title(),
        structure_detail=technical.structure.detail,
        close=technical.close,
        support=technical.levels.support,
        resistance=technical.levels.resistance,
        atr=technical.atr,
        rsi=technical.rsi,
        reasons=reasons,
        summary=_summary(
            direction,
            confidence,
            technical.close,
            ANALYSIS_TIMEFRAMES[timeframe],
            technical.structure.detail,
            technical.levels.support,
            technical.levels.resistance,
        ),
        updated_at=updated_at,
        limited=technical.ema_slow is None,
    )


async def answer_zenmux(settings: Settings, client: Any, body: ZenmuxRequest) -> ZenmuxResponse:
    """Score one turn and build the analysis card.

    Args:
        settings: Application settings, supplying the base URL and API key.
        client: A biquote client, used to source the candles.
        body: The user's turn, the selected display model and analysis timeframe.

    Returns:
        A :class:`ZenmuxResponse` ready to render.

    Raises:
        ZenmuxUnavailable: When the service is unconfigured, unreachable, the
            symbol or timeframe is unsupported, or nothing usable came back.
    """
    symbol = (body.symbol or ZENMUX_SYMBOL).upper()
    if symbol != ZENMUX_SYMBOL:
        raise ZenmuxUnavailable(
            f"Zenmux scores {ZENMUX_SYMBOL} only; the service is not available for {symbol}."
        )
    if body.timeframe not in ANALYSIS_TIMEFRAMES:
        offered = ", ".join(ANALYSIS_TIMEFRAMES.values())
        raise ZenmuxUnavailable(
            f"Zenmux cannot read {body.timeframe.value}; available timeframes are {offered}."
        )

    model = _resolve_model(body.model)
    backend = model["backend"]

    candles = await _fetch_candles(client, symbol)

    # Indicators run over the requested analysis timeframe, aggregated from the M5
    # series when it is higher. The upstream call always gets raw M5 bars, because
    # its feature contract is anchored there.
    series = bars_from_candles(candles)
    aggregated = resample(series, body.timeframe)
    technical = analyse(aggregated)

    data = await _call_endpoint(
        settings,
        {
            "candles": {"M5": candles[-_UPSTREAM_BAR_LIMIT:]},
            "backend": backend,
            "threshold": _THRESHOLD,
        },
        path="/predict/candles",
    )

    card = _build_card(
        model=model, timeframe=body.timeframe, data=data, technical=technical
    )

    _logger.info(
        "zenmux.analysis",
        symbol=symbol,
        model=model["name"],
        analysis_timeframe=card.timeframe,
        model_timeframe=MODEL_TIMEFRAME,
        direction=card.direction,
        confidence=round(card.confidence, 4),
        structure=card.structure,
        bars=len(series),
        analysis_bars=len(aggregated),
    )

    return card


def display_models() -> list[dict[str, str]]:
    """The two user-facing models, for the selector.

    Server-derived rather than hardcoded in the client so the slug, display name
    and backend mapping cannot drift apart.
    """
    return [
        {"id": slug, "name": entry["name"], "description": entry["description"]}
        for slug, entry in MODELS.items()
    ]


def now_iso() -> str:
    """Current UTC time, ISO-8601. Used as the card's fallback timestamp."""
    return datetime.now(UTC).isoformat()
