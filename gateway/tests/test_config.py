import pytest
import tempfile
from pathlib import Path
from agent_serve.config.loader import load_config
from agent_serve.config.models import GatewayConfig
from agent_serve.core.enums import Tier

VALID_YAML = """
backends:
  - id: small-0
    tier: small
    base_url: "http://localhost:8002"
    gpu: 0
    max_inflight: 64
admission:
  default_token_budget: 50000
routing:
  prompt_length_threshold: 1000
"""

MULTI_BACKEND_YAML = """
backends:
  - id: small-0
    tier: small
    base_url: "http://localhost:8002"
    gpu: 0
    max_inflight: 64
  - id: big-0
    tier: big
    base_url: "http://localhost:8001"
    gpu: 1
    max_inflight: 32
admission:
  default_token_budget: 100000
  budget_window_seconds: 3600
routing:
  prompt_length_threshold: 2000
affinity:
  sticky_ttl_seconds: 1800
"""


def _write_temp_yaml(content: str) -> str:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(content)
        return f.name


def test_load_valid_config():
    path = _write_temp_yaml(VALID_YAML)
    config = load_config(path)
    assert isinstance(config, GatewayConfig)
    assert len(config.backends) == 1
    assert config.backends[0].tier == Tier.SMALL
    assert config.admission.default_token_budget == 50000
    assert config.routing.prompt_length_threshold == 1000


def test_load_missing_file():
    with pytest.raises(Exception):
        load_config("/nonexistent/path/config.yaml")


def test_defaults_applied():
    minimal = (
        "backends:\n"
        "  - id: b1\n"
        "    tier: small\n"
        "    base_url: http://x\n"
        "    gpu: 0\n"
        "    max_inflight: 1\n"
    )
    path = _write_temp_yaml(minimal)
    config = load_config(path)
    assert config.affinity.enabled is True
    assert config.health.probe_interval_seconds == 10


def test_load_multi_backend_config():
    path = _write_temp_yaml(MULTI_BACKEND_YAML)
    config = load_config(path)
    assert len(config.backends) == 2
    tiers = {b.tier for b in config.backends}
    assert Tier.SMALL in tiers
    assert Tier.BIG in tiers


def test_load_invalid_yaml_raises():
    bad_yaml = "backends: [unclosed"
    path = _write_temp_yaml(bad_yaml)
    with pytest.raises(Exception):
        load_config(path)


def test_load_missing_required_field_raises():
    # Missing base_url — should fail schema validation
    bad = (
        "backends:\n"
        "  - id: b1\n"
        "    tier: small\n"
        "    gpu: 0\n"
        "    max_inflight: 1\n"
    )
    path = _write_temp_yaml(bad)
    with pytest.raises(Exception):
        load_config(path)


def test_backend_config_fields():
    path = _write_temp_yaml(VALID_YAML)
    config = load_config(path)
    b = config.backends[0]
    assert b.id == "small-0"
    assert b.base_url == "http://localhost:8002"
    assert b.gpu == 0
    assert b.max_inflight == 64


def test_default_health_config():
    path = _write_temp_yaml(VALID_YAML)
    config = load_config(path)
    assert config.health.failures_to_mark_down == 3
    assert config.health.successes_to_mark_up == 2
    assert config.health.probe_timeout_seconds == 5


def test_default_routing_config_is_applied_when_omitted():
    minimal = (
        "backends:\n"
        "  - id: b1\n"
        "    tier: big\n"
        "    base_url: http://x\n"
        "    gpu: 1\n"
        "    max_inflight: 8\n"
    )
    path = _write_temp_yaml(minimal)
    config = load_config(path)
    # Default prompt_length_threshold is 2000
    assert config.routing.prompt_length_threshold == 2000


def test_affinity_sticky_ttl_default():
    path = _write_temp_yaml(VALID_YAML)
    config = load_config(path)
    assert config.affinity.sticky_ttl_seconds == 1800


def test_custom_affinity_sticky_ttl():
    yaml_with_affinity = VALID_YAML + "affinity:\n  sticky_ttl_seconds: 600\n"
    path = _write_temp_yaml(yaml_with_affinity)
    config = load_config(path)
    assert config.affinity.sticky_ttl_seconds == 600
