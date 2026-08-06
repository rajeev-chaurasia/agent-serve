from collections.abc import AsyncIterator

import httpx

from ..core.models import BackendInfo
from .protocols import BackendRegistryProtocol


class BackendProxy:
    """Forwards requests to vLLM backends, with single-retry on alternate replica."""

    def __init__(self, registry: BackendRegistryProtocol, timeout_seconds: float = 300.0) -> None:
        self._registry = registry
        self._timeout = timeout_seconds

    async def stream(
        self,
        backend: BackendInfo,
        path: str,
        payload: dict,
        headers: dict,
    ) -> AsyncIterator[bytes]:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            async with client.stream(
                "POST",
                f"{backend.base_url}{path}",
                json=payload,
                headers=headers,
            ) as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    yield chunk

    async def call(
        self,
        backend: BackendInfo,
        path: str,
        payload: dict,
        headers: dict,
    ) -> dict:
        async with httpx.AsyncClient(timeout=self._timeout) as client:
            response = await client.post(
                f"{backend.base_url}{path}",
                json=payload,
                headers=headers,
            )
            response.raise_for_status()
            return response.json()
