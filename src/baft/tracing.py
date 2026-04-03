"""
Baft tracing integration — initialize OpenTelemetry for ITP pipelines.

Wraps ``heddle.tracing`` to provide ITP-specific service names and
defaults. All functions are safe to call without OTel installed
(they degrade to no-ops via heddle.tracing internals).

Usage::

    from baft.tracing import init_baft_tracing

    # Called once at startup (e.g. in CLI or test setup)
    init_baft_tracing()

    # Or with explicit collector endpoint
    init_baft_tracing(endpoint="http://localhost:4317")
"""

from __future__ import annotations

import os

import structlog

from heddle.tracing import get_tracer, init_tracing

logger = structlog.get_logger()

# Default service name for Baft in trace backends (Jaeger, Tempo, etc.)
BAFT_SERVICE_NAME = "baft-itp"


def init_baft_tracing(
    *,
    service_name: str = BAFT_SERVICE_NAME,
    endpoint: str | None = None,
) -> bool:
    """Initialize OpenTelemetry tracing for Baft.

    Reads ``OTEL_EXPORTER_OTLP_ENDPOINT`` from environment if *endpoint*
    is not provided.  Returns ``True`` if OTel was successfully initialized.

    Args:
        service_name: Service name reported to the collector.
        endpoint: OTLP gRPC endpoint.  Defaults to env var.

    Returns:
        ``True`` if tracing is active, ``False`` if OTel is not installed.
    """
    endpoint = endpoint or os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT")
    ok = init_tracing(service_name, endpoint=endpoint)
    if ok:
        logger.info("baft.tracing.initialized", service_name=service_name, endpoint=endpoint)
    else:
        logger.debug("baft.tracing.otel_not_available")
    return ok


def get_baft_tracer(scope: str = "baft") -> object:
    """Get a tracer scoped to a Baft component.

    Args:
        scope: Instrumentation scope (e.g. ``baft.pipeline``, ``baft.audit``).

    Returns:
        An OTel tracer or a no-op tracer.
    """
    return get_tracer(scope)
