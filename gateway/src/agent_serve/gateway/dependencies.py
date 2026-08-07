from fastapi import Depends

from ..accounting.protocols import AccountantProtocol
from ..admission.protocols import AdmissionControllerProtocol
from ..affinity.protocols import AffinitySchedulerProtocol
from ..backends.protocols import BackendProxyProtocol, BackendRegistryProtocol
from ..config.models import GatewayConfig
from ..routing.protocols import RouterProtocol
from .lifespan import get_singletons


def _singletons() -> dict:
    return get_singletons()


def get_config(s: dict = Depends(_singletons)) -> GatewayConfig:
    return s["config"]


def get_registry(s: dict = Depends(_singletons)) -> BackendRegistryProtocol:
    return s["registry"]


def get_proxy(s: dict = Depends(_singletons)) -> BackendProxyProtocol:
    return s["proxy"]


def get_accountant(s: dict = Depends(_singletons)) -> AccountantProtocol:
    return s["accountant"]


def get_admission(s: dict = Depends(_singletons)) -> AdmissionControllerProtocol:
    return s["admission"]


def get_router(s: dict = Depends(_singletons)) -> RouterProtocol:
    return s["router"]


def get_affinity(s: dict = Depends(_singletons)) -> AffinitySchedulerProtocol:
    return s["affinity"]
