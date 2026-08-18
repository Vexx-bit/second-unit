"""Synthetic VFX render farm emitting OTLP metrics, logs and traces to Grafana Cloud.

The Second Unit agent investigates the data this produces. The scenario is
intentionally deterministic: given the same seed, the same frames fail on the
same nodes for the same reason, every run. A demo you cannot reproduce is a demo
you cannot record.

Run from the repo root via `make sim` / `make inject-incident`, or directly:

    uv run farm.py --duration 600 --inject-incident --incident-at 120

Configuration comes from the standard OTLP environment variables in .env:
    OTEL_EXPORTER_OTLP_ENDPOINT
    OTEL_EXPORTER_OTLP_HEADERS
    OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf
"""

from __future__ import annotations

import argparse
import logging
import os
import random
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from opentelemetry import metrics, trace
from opentelemetry.exporter.otlp.proto.http._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Status, StatusCode

# --------------------------------------------------------------------------- #
# The shot being rendered
# --------------------------------------------------------------------------- #

SHOT = "SH042_beach_dusk"
TOTAL_FRAMES = 4000
NODE_COUNT = 40
GPU_COST_PER_SECOND = 0.0041  # USD, roughly an L4 spot instance

# The asset revision that breaks everything.
BROKEN_ASSET_VERSION = "v7"
BROKEN_TEXTURE = f"/assets/{SHOT}/tex/skin_albedo.{BROKEN_ASSET_VERSION}.exr"

# Exactly 14 of the 40 nodes pick up frames needing the broken texture.
AFFECTED_NODE_COUNT = 14

log = logging.getLogger("render-farm")


@dataclass
class FarmState:
    """Mutable state of the farm as the render progresses."""

    frames_done: int = 0
    frames_failed: int = 0
    incident_active: bool = False

    @property
    def queue_depth(self) -> int:
        return max(0, TOTAL_FRAMES - self.frames_done - self.frames_failed)


# --------------------------------------------------------------------------- #
# Telemetry wiring
# --------------------------------------------------------------------------- #


def init_telemetry() -> tuple[TracerProvider, MeterProvider, LoggerProvider]:
    """Wire up OTLP exporters for all three signals.

    Endpoint and auth headers are read from the standard OTEL_* environment
    variables, so nothing sensitive is hardcoded here.
    """
    if not os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT"):
        sys.exit(
            "ERROR: OTEL_EXPORTER_OTLP_ENDPOINT is not set.\n"
            "Copy .env.example to .env and fill in your Grafana Cloud OTLP values."
        )

    resource = Resource.create(
        {
            "service.name": "render-farm",
            "service.namespace": "second-unit",
            "service.version": "0.1.0",
            "deployment.environment": "demo",
            "vfx.shot": SHOT,
        }
    )

    tracer_provider = TracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(tracer_provider)

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[
            PeriodicExportingMetricReader(
                OTLPMetricExporter(), export_interval_millis=15_000
            )
        ],
    )
    metrics.set_meter_provider(meter_provider)

    logger_provider = LoggerProvider(resource=resource)
    logger_provider.add_log_record_processor(BatchLogRecordProcessor(OTLPLogExporter()))

    handler = LoggingHandler(level=logging.INFO, logger_provider=logger_provider)
    log.addHandler(handler)
    log.addHandler(logging.StreamHandler(sys.stdout))
    log.setLevel(logging.INFO)

    return tracer_provider, meter_provider, logger_provider


class Instruments:
    """Named metric instruments for the farm."""

    def __init__(self) -> None:
        meter = metrics.get_meter("second_unit.render_farm")

        self.frames_completed = meter.create_counter(
            "render.frames.completed",
            unit="{frame}",
            description="Frames finished, by outcome",
        )
        self.cost = meter.create_counter(
            "render.cost.usd",
            unit="USD",
            description="Cumulative GPU spend",
        )
        self.frame_duration = meter.create_histogram(
            "render.frame.duration",
            unit="s",
            description="Wall-clock time to render one frame",
        )
        self.gpu_utilization = meter.create_gauge(
            "render.node.gpu.utilization",
            unit="%",
            description="GPU utilization per render node",
        )
        self.queue_depth = meter.create_gauge(
            "render.queue.depth",
            unit="{frame}",
            description="Frames still pending for the shot",
        )


# --------------------------------------------------------------------------- #
# Frame rendering
# --------------------------------------------------------------------------- #


def render_frame(
    frame: int,
    node: str,
    inst: Instruments,
    state: FarmState,
    rng: random.Random,
    affected_nodes: set[str],
) -> None:
    """Emit one frame's worth of telemetry: a trace, metrics, and log lines."""
    tracer = trace.get_tracer("second_unit.render_farm")

    # A frame fails only if the incident is live AND this node is one of the
    # unlucky ones AND this frame needs the broken texture.
    needs_texture = frame % 3 != 0
    will_fail = state.incident_active and node in affected_nodes and needs_texture
    asset_version = BROKEN_ASSET_VERSION if state.incident_active else "v6"

    base_attrs = {"shot": SHOT, "node": node, "frame": frame}

    with tracer.start_as_current_span("render_frame") as span:
        span.set_attributes(
            {
                "vfx.shot": SHOT,
                "vfx.frame": frame,
                "vfx.node": node,
                "asset.version": asset_version,
            }
        )
        started = time.monotonic()

        # --- asset_fetch: where the incident bites ------------------------- #
        with tracer.start_as_current_span("asset_fetch") as fetch:
            fetch.set_attribute("asset.version", asset_version)
            fetch.set_attribute("asset.texture", BROKEN_TEXTURE if will_fail else "skin_albedo.v6.exr")
            time.sleep(rng.uniform(0.01, 0.04))

            if will_fail:
                fetch.set_status(Status(StatusCode.ERROR, "texture not found"))
                fetch.set_attribute("error.type", "AssetResolutionError")
                span.set_status(Status(StatusCode.ERROR, "asset_fetch failed"))

                duration = time.monotonic() - started
                state.frames_failed += 1

                log.error(
                    "FATAL: texture not found: %s (frame %d on %s)",
                    BROKEN_TEXTURE,
                    frame,
                    node,
                    extra={**base_attrs, "asset_version": asset_version},
                )
                inst.frames_completed.add(
                    1, {"shot": SHOT, "node": node, "status": "failed"}
                )
                inst.frame_duration.record(duration, {"shot": SHOT, "status": "failed"})
                # Failing fast still costs a little GPU time.
                inst.cost.add(duration * GPU_COST_PER_SECOND, {"shot": SHOT, "node": node})
                # A node that keeps failing sits mostly idle.
                inst.gpu_utilization.set(rng.uniform(4, 18), {"node": node, "shot": SHOT})
                return

        # --- the expensive part -------------------------------------------- #
        with tracer.start_as_current_span("rasterize") as raster:
            gpu_seconds = rng.uniform(0.8, 2.4)
            raster.set_attribute("gpu.seconds", round(gpu_seconds, 3))
            time.sleep(rng.uniform(0.02, 0.06))

        with tracer.start_as_current_span("composite"):
            time.sleep(rng.uniform(0.01, 0.03))

        with tracer.start_as_current_span("publish") as publish:
            publish.set_attribute("output.path", f"/renders/{SHOT}/{frame:04d}.exr")
            time.sleep(rng.uniform(0.005, 0.02))

        duration = time.monotonic() - started
        state.frames_done += 1

        log.info(
            "frame %d rendered on %s in %.2fs",
            frame,
            node,
            duration,
            extra={**base_attrs, "asset_version": asset_version},
        )
        inst.frames_completed.add(1, {"shot": SHOT, "node": node, "status": "succeeded"})
        inst.frame_duration.record(duration, {"shot": SHOT, "status": "succeeded"})
        inst.cost.add(gpu_seconds * GPU_COST_PER_SECOND, {"shot": SHOT, "node": node})
        inst.gpu_utilization.set(rng.uniform(82, 99), {"node": node, "shot": SHOT})


# --------------------------------------------------------------------------- #
# Main loop
# --------------------------------------------------------------------------- #


def main() -> int:
    parser = argparse.ArgumentParser(description="Synthetic VFX render farm")
    parser.add_argument("--duration", type=int, default=600, help="seconds to run")
    parser.add_argument(
        "--inject-incident", action="store_true", help="fire the asset v7 failure"
    )
    parser.add_argument(
        "--incident-at", type=int, default=120, help="seconds before the incident"
    )
    parser.add_argument("--speed", type=float, default=1.0, help="time multiplier")
    parser.add_argument("--seed", type=int, default=42, help="RNG seed")
    args = parser.parse_args()

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")

    tracer_provider, meter_provider, logger_provider = init_telemetry()
    inst = Instruments()
    state = FarmState()
    rng = random.Random(args.seed)

    nodes = [f"render-{i:02d}" for i in range(1, NODE_COUNT + 1)]
    # Deterministic: the same 14 nodes are affected on every run.
    affected_nodes = set(random.Random(args.seed).sample(nodes, AFFECTED_NODE_COUNT))

    stopping = False

    def handle_stop(*_: object) -> None:
        nonlocal stopping
        stopping = True
        log.info("shutdown requested, flushing telemetry...")

    signal.signal(signal.SIGINT, handle_stop)
    signal.signal(signal.SIGTERM, handle_stop)

    log.info(
        "render farm online: shot=%s frames=%d nodes=%d",
        SHOT,
        TOTAL_FRAMES,
        NODE_COUNT,
    )
    if args.inject_incident:
        log.info(
            "incident scheduled: asset %s at t+%ds across %d nodes",
            BROKEN_ASSET_VERSION,
            args.incident_at,
            AFFECTED_NODE_COUNT,
        )

    started = time.monotonic()
    frame = 1

    try:
        while not stopping:
            elapsed = (time.monotonic() - started) * args.speed
            if elapsed >= args.duration:
                break

            if (
                args.inject_incident
                and not state.incident_active
                and elapsed >= args.incident_at
            ):
                state.incident_active = True
                log.error(
                    "asset %s published for %s — texture path is broken",
                    BROKEN_ASSET_VERSION,
                    SHOT,
                    extra={"shot": SHOT, "asset_version": BROKEN_ASSET_VERSION},
                )

            node = nodes[frame % NODE_COUNT]
            render_frame(frame, node, inst, state, rng, affected_nodes)
            inst.queue_depth.set(state.queue_depth, {"shot": SHOT})

            frame += 1
            if frame > TOTAL_FRAMES:
                log.info("all frames dispatched, looping for continuous data")
                frame = 1

            time.sleep(max(0.0, 0.05 / args.speed))
    finally:
        log.info(
            "render summary: %d succeeded, %d failed",
            state.frames_done,
            state.frames_failed,
        )
        tracer_provider.shutdown()
        meter_provider.shutdown()
        logger_provider.shutdown()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
