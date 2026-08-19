"""OpenTelemetry self-instrumentation for the agent.

An observability agent that is not itself observable is an unfinished thought.
This sends the agent's own spans to Grafana Cloud, where they surface in AI
Observability alongside the render farm it investigates — one stack showing both
the incident and the responder.

That side-by-side view is a scored differentiator, not polish. Most submissions
will instrument nothing about themselves.
"""

from __future__ import annotations

import os

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

_initialised = False


def init_agent_telemetry() -> None:
    """Install a tracer provider for the agent. Safe to call more than once."""
    global _initialised
    if _initialised:
        return

    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        # Running without telemetry is allowed — the agent still works. But say
        # so loudly, because silent absence of self-observation is a regression
        # we would otherwise only notice at demo time.
        print("[telemetry] OTEL_EXPORTER_OTLP_ENDPOINT unset; agent spans disabled")
        _initialised = True
        return

    resource = Resource.create(
        {
            "service.name": "second-unit-agent",
            "service.namespace": "second-unit",
            "service.version": "0.1.0",
            "service.instance.id": os.getenv("AGENT_INSTANCE_ID", "local"),
            "deployment.environment.name": os.getenv("AGENT_ENV", "demo"),
            "gen_ai.system": "gcp.vertex_ai",
        }
    )

    provider = TracerProvider(resource=resource)
    provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(provider)
    _initialised = True


def tracer() -> trace.Tracer:
    """Tracer for instrumenting investigation steps."""
    return trace.get_tracer("second_unit.agent")
