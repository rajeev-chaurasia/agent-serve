import asyncio
import time

from ..core.exceptions import QueueFullException
from ..telemetry.metrics import QUEUE_DEPTH, QUEUE_WAIT_SECONDS


class BackpressureQueue:
    """Bounded async semaphore with queue-depth tracking.

    Callers acquire() to enter and must call release() when done.
    If max_inflight slots are taken and the queue is full, raises QueueFullException.
    """

    def __init__(
        self,
        max_inflight: int,
        max_queue: int,
        timeout_seconds: float,
        tier: str,
    ) -> None:
        self._semaphore = asyncio.Semaphore(max_inflight)
        self._max_queue = max_queue
        self._timeout = timeout_seconds
        self._tier = tier
        self._queued = 0

    async def acquire(self) -> float:
        """Acquire a slot. Returns wait time in seconds. Raises QueueFullException if queue is full."""
        if self._queued >= self._max_queue:
            raise QueueFullException(retry_after_seconds=int(self._timeout))
        self._queued += 1
        QUEUE_DEPTH.labels(tier=self._tier).inc()
        start = time.monotonic()
        try:
            await asyncio.wait_for(self._semaphore.acquire(), timeout=self._timeout)
        except asyncio.TimeoutError:
            raise QueueFullException(retry_after_seconds=int(self._timeout))
        finally:
            self._queued -= 1
            QUEUE_DEPTH.labels(tier=self._tier).dec()
        wait = time.monotonic() - start
        QUEUE_WAIT_SECONDS.labels(tier=self._tier).observe(wait)
        return wait

    def release(self) -> None:
        self._semaphore.release()
