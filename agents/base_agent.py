"""Base class shared by every specialised agent."""

from __future__ import annotations

import abc
import uuid
from collections.abc import Awaitable, Callable
from typing import Any, ClassVar, TypeVar

from pydantic import BaseModel, TypeAdapter

from shared.circuit_breaker import CircuitBreaker, CircuitOpenError
from shared.config import Settings, get_settings
from shared.logging import get_logger
from shared.messaging import InMemoryMessageBus, MessageBus
from shared.schemas.enums import AgentName
from shared.schemas.messages import AgentMessage

_logger = get_logger(__name__)

_T = TypeVar("_T", bound=BaseModel)


class BaseAgent(abc.ABC):
    """Common lifecycle, logging and publishing for agents.

    Subclasses declare their :attr:`name` and implement :meth:`run`. They may
    also override :meth:`start`/:meth:`stop` to manage long-lived resources
    (streams, connections), calling ``await super().start()`` first.
    """

    name: ClassVar[AgentName]

    def __init__(
        self,
        *,
        bus: MessageBus | None = None,
        settings: Settings | None = None,
    ) -> None:
        self.settings = settings or get_settings()
        self.bus: MessageBus = bus or InMemoryMessageBus()
        self.log = get_logger(f"agents.{self.name.value}", agent=self.name.value)
        self.breaker = CircuitBreaker(
            name=self.name.value,
            failure_threshold=self.settings.circuit_breaker_failure_threshold,
            recovery_timeout_seconds=self.settings.circuit_breaker_recovery_timeout_seconds,
        )

    # ------------------------------------------------------------------ #
    # Lifecycle
    # ------------------------------------------------------------------ #
    async def start(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Prepare the agent. Override for long-lived resources."""

    async def stop(self) -> None:  # noqa: B027 - optional hook, not abstract
        """Release agent resources. Override for long-lived resources."""

    # ------------------------------------------------------------------ #
    # Core contract
    # ------------------------------------------------------------------ #
    @abc.abstractmethod
    async def run(self, *args: Any, **kwargs: Any) -> BaseModel:
        """Execute one unit of work and return the agent's signal.

        Concrete signatures vary per agent; callers should consult the
        subclass docstring.
        """

    # ------------------------------------------------------------------ #
    # Publishing
    # ------------------------------------------------------------------ #
    @property
    def channel(self) -> str:
        """Default publish channel for this agent."""
        return f"signals.{self.name.value}"

    async def publish(
        self,
        payload: BaseModel | dict[str, Any],
        *,
        kind: str,
        correlation_id: str | None = None,
        channel: str | None = None,
    ) -> AgentMessage:
        """Wrap ``payload`` in an :class:`AgentMessage` and publish it.

        Args:
            payload: The signal model (or plain dict) to publish.
            kind: Message kind, e.g. ``"technical_signal"``.
            correlation_id: Correlates messages produced by one analysis cycle.
            channel: Override the default channel.

        Returns:
            The published envelope.
        """
        body = payload.model_dump(mode="json") if isinstance(payload, BaseModel) else payload
        message = AgentMessage(
            source=self.name,
            kind=kind,
            payload=body,
            correlation_id=correlation_id or uuid.uuid4().hex,
        )
        await self.bus.publish(channel or self.channel, message)
        self.log.debug("agent.published", kind=kind, channel=channel or self.channel)
        return message

    # ------------------------------------------------------------------ #
    # Safety: circuit breaker + output validation
    # ------------------------------------------------------------------ #
    @staticmethod
    def validate_output(output: Any, model_type: type[_T]) -> _T:
        """Validate ``output`` against ``model_type`` (Pydantic guard).

        Returns the output unchanged when it already conforms to the expected
        schema; otherwise raises a :class:`~pydantic.ValidationError`.
        """
        if isinstance(output, model_type):
            return output
        return TypeAdapter(model_type).validate_python(output)

    async def _guarded(
        self,
        expected: type[_T],
        operation: Callable[..., Awaitable[Any]],
        *args: Any,
        **kwargs: Any,
    ) -> _T:
        """Run ``operation`` through the circuit breaker and output validation.

        When the circuit is open a :class:`CircuitOpenError` is raised without
        invoking the operation. On failure the breaker records a strike and the
        error propagates. On success the returned payload must validate against
        ``expected`` or the breaker counts it as a failure.
        """
        if self.breaker.is_open:
            raise CircuitOpenError(f"{self.name.value} circuit is open")
        try:
            raw = await operation(*args, **kwargs)
            validated = self.validate_output(raw, expected)
        except Exception:
            self.breaker.record_failure()
            raise
        self.breaker.record_success()
        return validated
