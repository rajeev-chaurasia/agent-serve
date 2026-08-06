import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI

from ..config.loader import load_config
from ..config.models import GatewayConfig
from ..backends.registry import BackendRegistry
from ..backends.health import HealthChecker
from ..backends.proxy import BackendProxy
from ..accounting.accountant import TokenAccountant
from ..accounting.snapshot import SnapshotManager
from ..admission.controller import AdmissionController
from ..routing.router import TierRouter
from ..affinity.scheduler import AffinityScheduler
from ..telemetry.logging import configure_logging
from ..telemetry.tracing import setup_tracing, instrument_app
from ..telemetry.metrics import BACKEND_UP

logger = logging.getLogger(__name__)

# Module-level singletons populated during startup, accessed via dependencies.py
_config: GatewayConfig | None = None
_registry: BackendRegistry | None = None
_proxy: BackendProxy | None = None
_accountant: TokenAccountant | None = None
_admission: AdmissionController | None = None
_router: TierRouter | None = None
_affinity: AffinityScheduler | None = None
_health_checker: HealthChecker | None = None
_snapshot_manager: SnapshotManager | None = None


def get_singletons() -> dict:
    return {
        "config": _config,
        "registry": _registry,
        "proxy": _proxy,
        "accountant": _accountant,
        "admission": _admission,
        "router": _router,
        "affinity": _affinity,
    }


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _registry, _proxy, _accountant, _admission, _router, _affinity
    global _health_checker, _snapshot_manager

    config_path = os.environ.get("GATEWAY_CONFIG", "configs/gateway.yaml")
    _config = load_config(config_path)

    configure_logging(_config.telemetry.log_level)
    setup_tracing(_config.telemetry)

    _registry = BackendRegistry(_config)
    _proxy = BackendProxy(_registry)
    _accountant = TokenAccountant(_config.admission)

    snapshot_path = Path("results/accounting_snapshot.json")
    _snapshot_manager = SnapshotManager(_accountant, snapshot_path)
    _snapshot_manager.restore()

    _admission = AdmissionController(_config.admission, _accountant, _registry)
    _router = TierRouter(_config.routing, _registry)
    _affinity = AffinityScheduler(_registry, _config.affinity.sticky_ttl_seconds)

    _health_checker = HealthChecker(_registry, _config.health)
    _health_checker.start()
    _snapshot_manager.start()

    # Initialise backend_up gauge for all configured backends
    for backend in _registry.all_backends():
        BACKEND_UP.labels(backend=backend.id, tier=backend.tier.value).set(1)

    instrument_app(app)
    logger.info("gateway started with %d backends", len(_registry.all_backends()))

    yield

    logger.info("gateway shutting down")
    await _health_checker.stop()
    await _snapshot_manager.stop()
