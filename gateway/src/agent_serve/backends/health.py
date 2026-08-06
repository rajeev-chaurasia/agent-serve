import asyncio
import logging

import httpx

from ..config.models import HealthConfig
from ..core.enums import BackendStatus, HealthProbeResult
from ..core.models import BackendInfo
from .protocols import BackendRegistryProtocol

logger = logging.getLogger(__name__)


class _BackendHealthState:
    """Tracks consecutive failures/successes for hysteresis."""

    def __init__(self, failures_to_down: int, successes_to_up: int) -> None:
        self.failures_to_down = failures_to_down
        self.successes_to_up = successes_to_up
        self.consecutive_failures = 0
        self.consecutive_successes = 0

    def record_success(self) -> BackendStatus:
        self.consecutive_failures = 0
        self.consecutive_successes += 1
        if self.consecutive_successes >= self.successes_to_up:
            return BackendStatus.HEALTHY
        return BackendStatus.DEGRADED

    def record_failure(self) -> BackendStatus:
        self.consecutive_successes = 0
        self.consecutive_failures += 1
        if self.consecutive_failures >= self.failures_to_down:
            return BackendStatus.DOWN
        return BackendStatus.DEGRADED


class HealthChecker:
    """Periodically probes each backend and updates the registry."""

    def __init__(self, registry: BackendRegistryProtocol, config: HealthConfig) -> None:
        self._registry = registry
        self._config = config
        self._states: dict[str, _BackendHealthState] = {}
        self._task: asyncio.Task | None = None

    def start(self) -> None:
        self._task = asyncio.create_task(self._probe_loop(), name="health-probe-loop")

    async def stop(self) -> None:
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _probe_loop(self) -> None:
        while True:
            for backend in self._registry.all_backends():
                asyncio.create_task(self._probe_one(backend))
            await asyncio.sleep(self._config.probe_interval_seconds)

    async def _probe_one(self, backend: BackendInfo) -> None:
        state = self._states.setdefault(
            backend.id,
            _BackendHealthState(
                self._config.failures_to_mark_down,
                self._config.successes_to_mark_up,
            ),
        )
        result = await self._probe(backend)
        if result == HealthProbeResult.OK:
            new_status = state.record_success()
        else:
            new_status = state.record_failure()
            logger.warning(
                "backend %s probe %s (failures=%d)",
                backend.id,
                result,
                state.consecutive_failures,
            )

        if new_status != backend.status:
            logger.info(
                "backend %s status: %s -> %s",
                backend.id,
                backend.status,
                new_status,
            )
            self._registry.mark_status(backend.id, new_status)

    async def _probe(self, backend: BackendInfo) -> HealthProbeResult:
        try:
            async with httpx.AsyncClient(timeout=self._config.probe_timeout_seconds) as client:
                r = await client.get(f"{backend.base_url}/health")
                if r.status_code == 200:
                    return HealthProbeResult.OK
                return HealthProbeResult.ERROR
        except httpx.TimeoutException:
            return HealthProbeResult.TIMEOUT
        except Exception:
            return HealthProbeResult.ERROR
