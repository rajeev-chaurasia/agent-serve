"""
Structured JSON logging for agent-serve.

All log records are emitted as single-line JSON objects to stdout so that
log-aggregation pipelines (Loki, CloudWatch, Splunk) can index individual
fields without a parsing stage.

Usage
-----
Call configure_logging() once at startup, then obtain per-module loggers via
get_logger().  To attach request-scoped context to a log record without
threading it through every call-site, pass keyword arguments prefixed with
``ctx_``::

    logger.info("request routed", extra={"ctx_session_id": sid, "ctx_tier": tier})

The formatter strips the ``ctx_`` prefix so the emitted JSON key reads
``session_id`` and ``tier`` instead.
"""

import json
import logging
import sys
from datetime import UTC, datetime


class _JsonFormatter(logging.Formatter):
    """Render a LogRecord as a one-line JSON object."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict = {
            "ts": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }

        # Attach exception traceback when present.
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)

        # Promote any extra field whose key starts with "ctx_" into a
        # first-class JSON field, trimming the sentinel prefix.
        for key, value in record.__dict__.items():
            if key.startswith("ctx_"):
                payload[key[4:]] = value

        return json.dumps(payload)


def configure_logging(level: str = "info") -> None:
    """Replace all root-logger handlers with a single JSON handler.

    Call this once from the application entry-point before any loggers are
    used.  Subsequent calls are idempotent in terms of handler count because
    existing handlers are cleared first.
    """
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_JsonFormatter())

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    """Return a named logger that inherits the root JSON handler."""
    return logging.getLogger(name)
