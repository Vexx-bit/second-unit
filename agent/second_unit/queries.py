"""Every observability query the agent runs, as named functions.

Project rule (see AGENTS.md): queries never appear as inline string literals in
agent prompt text. They live here, named and documented, for three reasons:

1. They are the contract with `telemetry-sim`. If a metric name changes, this is
   the one file that must change.
2. A model asked to compose PromQL on the fly will invent metric names. Giving it
   ready-made queries removes that failure mode entirely.
3. They are testable without a model in the loop.

Metric names are confirmed against the live stack — see infra/grafana/README.md.
"""

from __future__ import annotations

SHOT = "SH042_beach_dusk"
SERVICE_NAME = "render-farm"

# --------------------------------------------------------------------------- #
# Metrics (PromQL) — scope the incident
# --------------------------------------------------------------------------- #


def failed_frame_count(window: str = "30m") -> str:
    """Total frames that failed in the window. Answers "how bad is it?"."""
    return f'sum(increase(render_frames_completed_total{{status="failed"}}[{window}]))'


def succeeded_frame_count(window: str = "30m") -> str:
    """Total frames that completed successfully, for context on the failure ratio."""
    return f'sum(increase(render_frames_completed_total{{status="succeeded"}}[{window}]))'


def affected_node_count(window: str = "30m") -> str:
    """Number of distinct nodes with at least one failure. The blast radius."""
    return (
        "count(count by (node) ("
        f'increase(render_frames_completed_total{{status="failed"}}[{window}]) > 0))'
    )


def affected_node_names(window: str = "30m") -> str:
    """Per-node failure counts, so the report can name the specific nodes."""
    return (
        "topk(50, sum by (node) ("
        f'increase(render_frames_completed_total{{status="failed"}}[{window}])))'
    )


def gpu_spend(window: str = "30m") -> str:
    """Total GPU spend in USD across the window."""
    return f"sum(increase(render_cost_usd_total[{window}]))"


def gpu_utilization_by_node() -> str:
    """Current GPU utilization per node.

    Important interpretive note for the agent: during an asset-resolution
    incident this DROPS on affected nodes, because they fail fast instead of
    doing work. Low utilization alongside high failure counts is corroborating
    evidence, not a contradiction.
    """
    return "render_node_gpu_utilization_percent"


def queue_depth() -> str:
    """Frames still pending for the shot. Answers "how far behind are we?"."""
    return "max(render_queue_depth)"


def failure_rate(window: str = "5m") -> str:
    """Failure rate per second — the same expression the alert rule evaluates."""
    return f'sum(rate(render_frames_completed_total{{status="failed"}}[{window}]))'


def frame_duration_p95(window: str = "5m") -> str:
    """p95 frame render duration, to check whether surviving renders degraded too."""
    return (
        "histogram_quantile(0.95, sum by (le) ("
        f"rate(render_frame_duration_seconds_bucket[{window}])))"
    )


# --------------------------------------------------------------------------- #
# Logs (LogQL) — find the error text
# --------------------------------------------------------------------------- #


def fatal_render_errors() -> str:
    """All FATAL render log lines. The raw error text behind the metric spike."""
    return f'{{service_name="{SERVICE_NAME}"}} |= "FATAL"'


def asset_resolution_errors() -> str:
    """Log lines specific to a texture that could not be resolved."""
    return f'{{service_name="{SERVICE_NAME}"}} |= "texture not found"'


def error_lines_by_node() -> str:
    """Error line counts grouped by node, to cross-check the metric blast radius."""
    return (
        f'sum by (node) (count_over_time({{service_name="{SERVICE_NAME}"}} '
        '|= "FATAL" [30m]))'
    )


def asset_publish_events() -> str:
    """Asset publish log lines — the likely trigger for an asset-related incident."""
    return f'{{service_name="{SERVICE_NAME}"}} |= "published"'


# --------------------------------------------------------------------------- #
# Traces (TraceQL) — identify the shared failing span
# --------------------------------------------------------------------------- #


def failing_render_traces() -> str:
    """Traces where a frame render errored."""
    return f'{{resource.service.name="{SERVICE_NAME}" && status=error}}'


def failing_asset_fetch_spans() -> str:
    """Error spans in asset_fetch specifically — the suspected failure stage."""
    return (
        f'{{resource.service.name="{SERVICE_NAME}" '
        '&& name="asset_fetch" && status=error}'
    )


def traces_by_asset_version(version: str) -> str:
    """Traces carrying a specific asset revision.

    This is the query that closes the investigation: it ties the failures to a
    single asset revision, which no metric or log line can establish alone.
    """
    return (
        f'{{resource.service.name="{SERVICE_NAME}" '
        f'&& span.asset.version="{version}"}}'
    )


# --------------------------------------------------------------------------- #
# Reference block injected into agent instructions
# --------------------------------------------------------------------------- #

QUERY_REFERENCE = f"""
Available metric names (Prometheus). These are exact. Never invent others:
  render_frames_completed_total    counter, labels: shot, node, status
  render_cost_usd_total            counter, labels: shot, node
  render_frame_duration_seconds_*  histogram, labels: shot, status, le
  render_node_gpu_utilization_percent  gauge, labels: shot, node
  render_queue_depth               gauge, labels: shot

The shot under investigation is {SHOT}. The service name in logs and traces is
{SERVICE_NAME}.

Ready-made queries you should prefer over composing your own:
  failed frames        {failed_frame_count()}
  blast radius         {affected_node_count()}
  affected nodes       {affected_node_names()}
  GPU spend            {gpu_spend()}
  GPU utilization      {gpu_utilization_by_node()}
  queue depth          {queue_depth()}
  fatal log lines      {fatal_render_errors()}
  asset errors         {asset_resolution_errors()}
  failing spans        {failing_asset_fetch_spans()}
"""
