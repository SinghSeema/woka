"""Circuit breaker for Supabase memory fetch calls.

Prevents a slow or failing Supabase from blocking every user turn.
When DB calls repeatedly timeout or fail, the breaker opens and all
context fetches return an empty result immediately for a cooldown window.
After the cooldown the breaker half-opens and probes one call; success
resets the breaker, failure extends the cooldown.
"""

import asyncio
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Coroutine, TypeVar

from app.core.logging import get_logger

logger = get_logger(__name__)

T = TypeVar("T")

# Default thresholds — can be overridden per instance
_FAILURE_THRESHOLD = 3       # open after this many consecutive failures
_TIMEOUT_SECONDS   = 0.5     # individual call budget
_COOLDOWN_SECONDS  = 60      # how long the circuit stays open


class _State(Enum):
    CLOSED    = "closed"     # normal operation
    OPEN      = "open"       # failing — return fallback immediately
    HALF_OPEN = "half_open"  # one probe allowed to test recovery


class CircuitBreaker:
    """Simple async circuit breaker for Supabase / external DB calls.

    Usage::

        breaker = CircuitBreaker()
        results = await breaker.call(
            get_sessions_by_semantic_search(...),
            fallback=[],
        )
    """

    def __init__(
        self,
        failure_threshold: int = _FAILURE_THRESHOLD,
        timeout_seconds: float = _TIMEOUT_SECONDS,
        cooldown_seconds: int = _COOLDOWN_SECONDS,
        name: str = "supabase",
    ):
        self._failure_threshold = failure_threshold
        self._timeout = timeout_seconds
        self._cooldown = cooldown_seconds
        self._name = name

        self._state = _State.CLOSED
        self._failure_count = 0
        self._open_until: datetime | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def call(self, coro: Coroutine[Any, Any, T], fallback: T) -> T:
        """Execute *coro* with a timeout, applying circuit-breaker logic.

        Returns *fallback* immediately when the circuit is open, or when the
        call times out / raises an exception.

        Args:
            coro: The async coroutine to execute (e.g. a DB query).
            fallback: Value to return when the circuit is open or the call fails.
        """
        if self._is_open():
            logger.warning(
                "⚡ [CIRCUIT BREAKER] %s — OPEN, skipping DB call (opens until %s)",
                self._name,
                self._open_until.strftime("%H:%M:%S") if self._open_until else "?",
            )
            return fallback

        if self._state == _State.HALF_OPEN:
            logger.info("⚡ [CIRCUIT BREAKER] %s — probing (HALF_OPEN)", self._name)

        try:
            result = await asyncio.wait_for(coro, timeout=self._timeout)
            self._on_success()
            return result

        except asyncio.TimeoutError:
            logger.warning(
                "⚡ [CIRCUIT BREAKER] %s — timeout after %.2fs",
                self._name,
                self._timeout,
            )
            self._on_failure()
            return fallback

        except Exception as exc:
            logger.warning(
                "⚡ [CIRCUIT BREAKER] %s — error: %s",
                self._name,
                exc,
            )
            self._on_failure()
            return fallback

    @property
    def is_healthy(self) -> bool:
        """True when the circuit is closed and not accumulating failures."""
        return self._state == _State.CLOSED and self._failure_count == 0

    # ------------------------------------------------------------------
    # Internal state transitions
    # ------------------------------------------------------------------

    def _is_open(self) -> bool:
        if self._state == _State.OPEN:
            if datetime.now() >= self._open_until:
                # Cooldown expired — allow one probe
                self._state = _State.HALF_OPEN
                logger.info("⚡ [CIRCUIT BREAKER] %s — cooldown expired, entering HALF_OPEN", self._name)
                return False
            return True
        return False

    def _on_success(self) -> None:
        if self._state != _State.CLOSED:
            logger.info("⚡ [CIRCUIT BREAKER] %s — CLOSED (recovered)", self._name)
        self._state = _State.CLOSED
        self._failure_count = 0
        self._open_until = None

    def _on_failure(self) -> None:
        self._failure_count += 1
        if self._failure_count >= self._failure_threshold or self._state == _State.HALF_OPEN:
            self._state = _State.OPEN
            self._open_until = datetime.now() + timedelta(seconds=self._cooldown)
            logger.error(
                "⚡ [CIRCUIT BREAKER] %s — OPEN after %d failures (cooldown %ds, until %s)",
                self._name,
                self._failure_count,
                self._cooldown,
                self._open_until.strftime("%H:%M:%S"),
            )
        else:
            logger.warning(
                "⚡ [CIRCUIT BREAKER] %s — failure %d/%d",
                self._name,
                self._failure_count,
                self._failure_threshold,
            )
