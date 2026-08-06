import threading

from ..config.models import GatewayConfig
from ..core.enums import BackendStatus, Tier
from ..core.models import BackendInfo


class BackendRegistry:
    """Holds runtime state of all configured backends.

    Thread-safe: health state is updated by the probe loop, read by request handlers.
    """

    def __init__(self, config: GatewayConfig) -> None:
        self._backends: dict[str, BackendInfo] = {
            b.id: BackendInfo(**b.model_dump())
            for b in config.backends
        }
        self._lock = threading.RLock()

    def get_healthy_backends(self, tier: Tier) -> list[BackendInfo]:
        with self._lock:
            return [
                b for b in self._backends.values()
                if b.tier == tier and b.status == BackendStatus.HEALTHY
            ]

    def get_backend(self, backend_id: str) -> BackendInfo | None:
        with self._lock:
            return self._backends.get(backend_id)

    def mark_status(self, backend_id: str, status: BackendStatus) -> None:
        with self._lock:
            if backend_id in self._backends:
                self._backends[backend_id] = self._backends[backend_id].model_copy(
                    update={"status": status}
                )

    def all_backends(self) -> list[BackendInfo]:
        with self._lock:
            return list(self._backends.values())
