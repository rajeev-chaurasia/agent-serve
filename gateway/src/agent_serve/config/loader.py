import os
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import GatewayConfig


def load_config(path: str | Path) -> GatewayConfig:
    """Load gateway configuration from a YAML file with env-var overrides.

    Env-var overrides:
        GATEWAY_LOG_LEVEL       -> telemetry.log_level
        GATEWAY_OTLP_ENDPOINT   -> telemetry.otlp_endpoint

    Raises:
        FileNotFoundError: if the config file does not exist.
        ValueError: if the file contains invalid YAML or fails schema validation.
    """
    config_path = Path(path)

    if not config_path.exists():
        raise FileNotFoundError(
            f"Gateway config file not found: {config_path.resolve()}"
        )

    try:
        raw = config_path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ValueError(f"Could not read config file '{config_path}': {exc}") from exc

    try:
        data: dict = yaml.safe_load(raw) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"Invalid YAML in config file '{config_path}': {exc}") from exc

    if not isinstance(data, dict):
        raise ValueError(
            f"Config file '{config_path}' must contain a YAML mapping at the top level."
        )

    # Apply environment-variable overrides
    telemetry: dict = data.setdefault("telemetry", {})

    log_level = os.environ.get("GATEWAY_LOG_LEVEL")
    if log_level:
        telemetry["log_level"] = log_level

    otlp_endpoint = os.environ.get("GATEWAY_OTLP_ENDPOINT")
    if otlp_endpoint:
        telemetry["otlp_endpoint"] = otlp_endpoint

    try:
        return GatewayConfig(**data)
    except ValidationError as exc:
        raise ValueError(
            f"Config file '{config_path}' failed validation:\n{exc}"
        ) from exc
