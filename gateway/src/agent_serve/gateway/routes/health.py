import logging

import httpx
from fastapi import APIRouter, Depends

from ..dependencies import get_accountant, get_registry
from ...core.enums import BackendStatus

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/healthz")
async def healthz():
    return {"status": "ok"}


@router.get("/v1/models")
async def list_models(registry=Depends(get_registry)):
    backends = [b for b in registry.all_backends() if b.status == BackendStatus.HEALTHY]
    models = []
    for backend in backends:
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                r = await client.get(f"{backend.base_url}/v1/models")
                if r.status_code == 200:
                    data = r.json()
                    for m in data.get("data", []):
                        m["backend_id"] = backend.id
                        m["tier"] = backend.tier.value
                        models.append(m)
        except Exception:
            pass
    return {"object": "list", "data": models}


@router.get("/status")
async def status(registry=Depends(get_registry), accountant=Depends(get_accountant)):
    backends = registry.all_backends()
    backend_states = [
        {
            "id": b.id,
            "tier": b.tier.value,
            "status": b.status.value,
            "gpu": b.gpu,
            "max_inflight": b.max_inflight,
        }
        for b in backends
    ]
    return {
        "gateway": "ok",
        "backends": backend_states,
        "healthy_big": len(
            [b for b in backends if b.tier.value == "big" and b.status == BackendStatus.HEALTHY]
        ),
        "healthy_small": len(
            [b for b in backends if b.tier.value == "small" and b.status == BackendStatus.HEALTHY]
        ),
    }
