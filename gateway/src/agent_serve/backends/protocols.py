from collections.abc import AsyncIterator
from typing import Protocol, runtime_checkable

from ..core.enums import BackendStatus, Tier
from ..core.models import BackendInfo, HealthStatus


@runtime_checkable
class HealthCheckableProtocol(Protocol):
    async def probe(self, backend: BackendInfo) -> HealthStatus: ...


@runtime_checkable
class BackendRegistryProtocol(Protocol):
    def get_healthy_backends(self, tier: Tier) -> list[BackendInfo]: ...
    def get_backend(self, backend_id: str) -> BackendInfo | None: ...
    def mark_status(self, backend_id: str, status: BackendStatus) -> None: ...
    def all_backends(self) -> list[BackendInfo]: ...


@runtime_checkable
class BackendProxyProtocol(Protocol):
    async def stream(
        self,
        backend: BackendInfo,
        path: str,
        payload: dict,
        headers: dict,
    ) -> AsyncIterator[bytes]: ...

    async def call(
        self,
        backend: BackendInfo,
        path: str,
        payload: dict,
        headers: dict,
    ) -> dict: ...
