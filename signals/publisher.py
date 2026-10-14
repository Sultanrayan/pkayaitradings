"""Published signal published to the bus by the scheduler.

Kept separate from the engine so :mod:`signals.store` stays free of any transport
dependency. The store adapter holds signals; this module is what puts one on the
wire, and the two are wired together only by the caller.

Channel convention follows the existing bus: ``signals.<name>``, subscribable with
the ``signals.*`` glob. The kind is ``"signal"``.
"""

from __future__ import annotations

from shared.logging import get_logger
from shared.messaging import MessageBus
from shared.schemas.enums import AgentName
from shared.schemas.messages import AgentMessage
from signals.models import Signal

_logger = get_logger(__name__)

__all__ = ["SIGNAL_CHANNEL", "build_message", "publish_signal"]

#: Channel signals are published on. Subscribers use the ``signals.*`` glob.
SIGNAL_CHANNEL = "signals.engine"


def build_message(signal: Signal, *, correlation_id: str = "") -> AgentMessage:
    """Wrap a signal in the bus envelope.

    The payload is :meth:`Signal.to_dict` verbatim â€” no reformatting, no rounding,
    no timestamp conversion â€” so a subscriber receives exactly what the store holds
    and what the chart will plot.

    Args:
        signal: The signal to publish.
        correlation_id: Groups this signal with the cycle that produced it. The
            engine is deterministic and reads no cycle state, so this is purely
            for tracing.

    Returns:
        An :class:`~shared.schemas.messages.AgentMessage` ready to publish.
    """
    return AgentMessage(
        source=AgentName.ORCHESTRATOR,
        kind="signal",
        payload=signal.to_dict(),
        correlation_id=correlation_id or "engine",
    )


async def publish_signal(
    bus: MessageBus,
    signal: Signal,
    *,
    correlation_id: str = "",
    channel: str = SIGNAL_CHANNEL,
) -> None:
    """Publish one signal on the bus.

    Args:
        bus: Transport to publish on.
        signal: The signal to announce.
        correlation_id: Optional cycle identifier, forwarded to the envelope.
        channel: Override for the channel; defaults to :data:`SIGNAL_CHANNEL`.

    Raises:
        Exception: Propagated from the bus. A publish failure is not swallowed:
            a signal that reached the store but not the bus is a real gap, and
            hiding it would make the gap invisible to the operator.
    """
    message = build_message(signal, correlation_id=correlation_id)
    await bus.publish(channel, message)
    _logger.info(
        "signals.published",
        channel=channel,
        symbol=signal.symbol,
        timeframe=signal.timeframe,
        action=signal.action,
        bar_timestamp=signal.timestamp.isoformat(),
        price=signal.price,
        confidence=signal.confidence,
    )
