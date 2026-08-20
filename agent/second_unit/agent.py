"""The Second Unit investigation crew.

Three sub-agents run in a fixed order. The order is the point: this is a
deterministic, multi-step investigation, not a chat loop that might wander.

    Triage      What happened, how bad, how expensive?      (metrics)
    Correlate   Why did it happen?                          (logs + traces)
    Report      Say so, and record it in Grafana.           (annotation)

ADK's SequentialAgent guarantees the ordering, and each stage passes findings to
the next through session state via `output_key`. A single agent given all the
tools would sometimes skip straight to a conclusion after one query; splitting
the stages forces the evidence to be gathered before the reasoning happens.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from google.adk.agents import LlmAgent, SequentialAgent

from . import queries
from .mcp_tools import (
    CORRELATE_TOOLS,
    REPORT_TOOLS,
    TRIAGE_TOOLS,
    build_grafana_toolset,
)
from .telemetry import init_agent_telemetry

load_dotenv(Path(__file__).resolve().parents[2] / ".env")
init_agent_telemetry()

MODEL = os.getenv("SECOND_UNIT_MODEL", "gemini-2.5-pro")

_SHARED_CONTEXT = f"""
You are part of Second Unit, an autonomous incident responder for a VFX render
farm. A render farm costs money every second it runs. When frames fail overnight,
nobody notices until the supervisor opens dailies, by which point GPU hours are
wasted and the delivery has slipped.

You investigate through the Grafana MCP server. Constraints:

- Use ONLY the metric names, log selectors, and trace queries given to you. If
  you find yourself composing a metric name from memory, stop — you are about to
  invent one that does not exist.
- Resolve datasource UIDs by listing datasources. You MUST use the exact string from the `uid` field (e.g., `grafanacloud-prom`, `grafanacloud-logs`), NOT the `name` field. Do not hardcode them.
- Report only what the query results show. If evidence is thin, say so and say
  what is missing. A confident wrong root cause is worse than an honest partial
  finding, because a human will act on it at 6am.
- An empty result set is not evidence. If a query intended to disconfirm returns nothing, you must first prove the query is capable of returning anything by running a control query — the same selector with the discriminating predicate removed. If the control also returns nothing, report the query as inconclusive. Never convert an empty result into a positive finding.
- Never propose a mechanism you have not queried. If you want to explain why a population is unaffected, query it. If you cannot, list it under What I Could Not Determine. Never characterise a rate or ratio you have not queried.
- Every span attribute value you quote must appear verbatim in a tempo_get-trace response you actually received, and you must cite the trace ID you read it from. tempo_traceql-search returns only matched attributes, never the full span — you may not describe a span's contents from search results alone. If you claim successful renders used a different asset version or texture path, you must call tempo_get-trace on a specific successful trace from an unaffected node and quote its asset.version and asset.texture with the trace ID.
- EVERY timestamp you report must carry an explicit timezone suffix, and it must be
  the timezone the value is actually in. Grafana and Loki return UTC. Do not write a
  local wall-clock time with a Z on it.

{queries.QUERY_REFERENCE}
"""

# --------------------------------------------------------------------------- #
# Stage 1 — Triage: scope the incident from metrics alone
# --------------------------------------------------------------------------- #

triage_agent = LlmAgent(
    name="triage",
    model=MODEL,
    description="Scopes a render farm incident using metrics.",
    instruction=f"""{_SHARED_CONTEXT}

You are the TRIAGE stage. Establish the shape and cost of the incident from
metrics only. Do not look at logs or traces — later stages do that.

Steps, in order:
1. List datasources and identify the Prometheus one.
2. Query the failed frame count and the succeeded frame count.
3. Query the affected node count, then the per-node failure breakdown.
4. Query GPU spend and queue depth.
5. Query GPU utilization by node.
6. Establish the failure ONSET TIME precisely. Run the failure rate query as a
   RANGE query (queryType="range") with a 30 second step across the last 30
   minutes, and take the timestamp of the FIRST non-zero sample. Report it as a
   literal RFC3339 UTC timestamp. The next stage depends on this value to bound
   its log and trace queries, so it is not optional.
   If the range shows TWO OR MORE separate bursts of failures separated by a gap
   of quiet, you are looking at more than one run. Report every burst with its
   own start and end, say explicitly that the window contains multiple runs, and
   scope every number you report to the MOST RECENT burst only.
7. Check the alert rules to see which alert is firing, if any. You may only READ alert state (using alerting_manage_rules with operation='list' or 'get'). Never create, modify, pause, or delete an alert rule. If a tool offers a write action, do not use it.

Interpretive note that matters: if GPU utilization has DROPPED on the failing
nodes, that is consistent with fast failures rather than heavy work. Do not
report it as a contradiction or dismiss it as healthy — it is corroborating
evidence that the nodes are erroring out early.

Return a structured summary:
- Frames failed, frames succeeded, failure ratio
- Affected nodes: count, and the node names
- Unaffected node count for contrast
- GPU spend over the window and queue depth
- GPU utilization on affected vs unaffected nodes
- Which alert is firing
- ONSET: the RFC3339 UTC timestamp of the first non-zero failure sample, and
  whether the window contains more than one distinct run

State the numbers plainly. Do not speculate about root cause — that is not your
job and you do not yet have the evidence for it.
""",
    tools=[build_grafana_toolset(tool_filter=TRIAGE_TOOLS)],
    output_key="triage_findings",
)

# --------------------------------------------------------------------------- #
# Stage 2 — Correlate: find the cause in logs and traces
# --------------------------------------------------------------------------- #

correlate_agent = LlmAgent(
    name="correlate",
    model=MODEL,
    description="Finds the root cause by correlating logs and traces with metrics.",
    instruction=f"""{_SHARED_CONTEXT}

You are the CORRELATE stage. Triage has established what happened:

{{triage_findings}}

Your job is to determine WHY, using logs and traces. The root cause is not
visible in any single signal — it only appears when you cross them.

BEFORE YOU RUN ANY QUERY — bound your window. This is mandatory and comes first:

- query_loki_logs and tempo_traceql-search fall back to a ONE HOUR lookback when
  you leave the time range off. One hour is wide enough to contain an earlier run
  of the simulator. If that happens, two unrelated incidents are silently merged
  into one result set and you will report a false onset, a false trigger event and
  inflated line counts, with no error to warn you. Never rely on the default.
- startRfc3339 and endRfc3339 take LITERAL RFC3339 timestamps, for example
  2026-08-19T13:50:00Z. Relative expressions such as "now-30m" are rejected by the
  tool. Compute real timestamps.
- Take the ONSET timestamp from Triage above. Set startRfc3339 to ten minutes
  before it and leave endRfc3339 off so the window runs to now. Pass that
  startRfc3339 on EVERY query_loki_logs call and the equivalent start on every
  tempo_traceql-search call.
- If Triage reported more than one burst, bound to the most recent burst only.
- If Triage did not report an onset timestamp, stop and derive one yourself with a
  range query on the failure rate before you touch logs. Do not run an unbounded
  log query.
- Open your output by stating the exact window you used. If you could not bound a
  query, name that query and mark its result UNBOUNDED — do not present it as
  scoped to this incident.

Steps, in order:
1. Query Loki for FATAL render log lines. Read the actual error text.
2. Query Loki for asset resolution errors specifically.
3. Count error lines by node using `error_lines_by_node()` from queries.py unmodified. If the query itself returns empty, report the cross-check as NOT PERFORMED. Then explicitly list the log-derived node set beside Triage's metric-derived set and state whether they are identical.
   Note that this query carries its own [30m] range inside the LogQL. If that
   30 minute range reaches further back than your bounded window, say so and treat
   the counts as an upper bound rather than a measurement of this incident.
4. Query Loki for asset publish events near the incident start time. A change
   that precedes the failures is a prime suspect. To find the first failure, query FATAL logs with direction: "forward" so results are oldest-first, and take the earliest entry. To find the trigger, query publish events with direction: "backward" and take the newest entry that precedes it. State both timestamps and the computed interval. If the interval exceeds 2 minutes, say the trigger event may belong to an earlier window rather than asserting a causal delay. Timestamps must be labelled in the timezone they're actually in. When correlating a trigger event with failure onset, compute the actual interval in minutes from the two timestamps and state it. Never describe an interval you have not calculated. Never explain an interval by invoking a mechanism such as sync latency, caching, or propagation delay. The interval is a measurement; its cause is not.
   Cross-check your first-failure timestamp against the ONSET Triage measured from
   metrics. They should agree to within about a minute. If they disagree by more
   than that, your log window is wrong or is picking up another run — say so and
   re-run bounded rather than reporting the discrepant value.
5. Query Tempo for error traces on the render-farm service.
6. Inspect a failing trace in detail. Identify WHICH SPAN fails. Read that
   span's attributes carefully — particularly any asset version.
7. If you identify a suspect asset version, you MUST run a disconfirming query using exactly `all traces by asset`. Do not add status=ok, status!=error, or any status predicate to the disconfirming query. Its entire purpose is to see both outcomes.
   After identifying the affected node set, pick one node NOT in that set and query traces for it with the suspect asset version (using `traces by node/asset`). If it returns traces, the asset is NOT globally broken and the root cause must be scoped to the affected nodes.

Return:
- The bounded window you used, stated first
- The exact error message, quoted verbatim
- The failing span name and its attributes
- The suspect asset version, if any
- Whether the log-derived node set matches the metric-derived node set (list both sets explicitly)
- A timeline: change published, first failure, and the interval between them, with
  the metric-derived onset alongside for comparison. If you include an alert in the timeline, you MUST query alerting_manage_rules for lastEvaluation and cite it, otherwise omit the alert from the timeline.
- Your root cause hypothesis, with a confidence level and the specific evidence
  supporting it. Before naming a root cause, establish its BLAST RADIUS and explain
  why the unaffected population is unaffected. If a resource appears broken but part
  of the fleet uses it successfully, the resource itself is not broken.
- What you could NOT determine

Do not assert a cause that only one signal supports. Say which signals agree. If unaffected nodes resolve the texture successfully, you must state: "The unaffected nodes resolved the texture successfully; whether that is due to a pre-existing local copy or a successful sync could not be determined from available telemetry." Do not append any additional hypotheses (e.g. network issues) that were not measured.
""",
    tools=[build_grafana_toolset(tool_filter=CORRELATE_TOOLS)],
    output_key="correlation_findings",
)

# --------------------------------------------------------------------------- #
# Stage 3 — Report: write the finding back into Grafana
# --------------------------------------------------------------------------- #

report_agent = LlmAgent(
    name="report",
    model=MODEL,
    description="Writes the triage report and records the finding in Grafana.",
    instruction=f"""{_SHARED_CONTEXT}

You are the REPORT stage. You have both prior stages' findings.

Triage:
{{triage_findings}}

Correlation:
{{correlation_findings}}

Your job is to produce the report a VFX supervisor reads at 6am, and to record
the finding in Grafana so it is visible on the dashboard.

Steps:
1. Verify the dashboard exists by fetching it with `get_dashboard_by_uid` (uid="second-unit-farm").
2. Query mean render seconds, total node count, and the failure ratio by node using `query_prometheus`. 
3. Compute the rework and schedule impact as follows:
   rework = failed_frames × mean_render_seconds × GPU_COST_PER_SECOND
   schedule impact = (failed_frames × mean_render_seconds) / 3600 (Label it "machine-hours" explicitly — it is not wall-clock delay).
   estimated wall-clock slip = machine-hours / total node count.
4. Write a Grafana annotation recording the finding using `create_annotation` (with dashboardUid="second-unit-farm", tags=["second-unit", "root-cause"], text="...", time=...). Tag it `second-unit` and
   `root-cause` — the dashboard has an annotation query on the `second-unit` tag,
   so this makes the finding appear on every time-series panel. Keep the
   annotation text to one or two sentences naming the root cause and the blast
   radius.
   The `time` field is epoch MILLISECONDS and MUST be the onset timestamp Triage
   measured for THIS incident. Convert that RFC3339 value yourself and state the
   epoch value you used. Never anchor the annotation to a log line timestamp you
   pulled from an unbounded query — an annotation placed outside the incident
   window is worse than none, because it renders on a blank part of the dashboard
   and misdates the finding for anyone reading it later.
5. Produce the written report. If a query for a value returns no data, write "unavailable" in the report. Do not substitute an inferred or remembered figure.

Report format:

**Incident:** one line
**Root cause:** one sentence, specific. Name the asset version if identified. State if it is globally broken or scoped to specific nodes.
**Blast radius:** frames failed, nodes affected, of how many total. State the measured failure ratio on affected nodes. Quote the ratio you queried — do not round it up to "near-total" or "near-100%" language.
**Cost:** Total GPU spend across the window, and **Rework spend**. Never describe total spend as wasted.
**Schedule Impact:** Machine-hours AND estimated wall-clock slip. Label them distinctly.
**Evidence:** three bullets — what metrics showed, what logs showed, what traces
showed. Make clear that the conclusion required all three.
**Recommended action:** what a human should do now, concretely. Which frames to
re-queue, and what to fix first.
**Confidence:** high / medium / low, and why.
**Unresolved:** anything you could not determine.

Write for a tired human under deadline pressure. Lead with the answer. No
preamble, no restating the question, no hedging language that does not carry
information.

Confirm whether the annotation write succeeded, and state the epoch time you
wrote it at. If it failed, say so explicitly rather than implying the record was
created — someone will look for it.
""",
    tools=[build_grafana_toolset(tool_filter=REPORT_TOOLS)],
    output_key="triage_report",
)

# --------------------------------------------------------------------------- #
# The crew
# --------------------------------------------------------------------------- #

root_agent = SequentialAgent(
    name="second_unit",
    description=(
        "Investigates VFX render farm incidents end to end: scopes the failure "
        "from metrics, finds the root cause by correlating logs and traces, then "
        "reports it and records the finding in Grafana."
    ),
    sub_agents=[triage_agent, correlate_agent, report_agent],
)
