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
- Resolve datasource UIDs by listing datasources. Do not hardcode them.
- Report only what the query results show. If evidence is thin, say so and say
  what is missing. A confident wrong root cause is worse than an honest partial
  finding, because a human will act on it at 6am.
- An empty result set is not evidence. If a query intended to disconfirm returns nothing, you must first prove the query is capable of returning anything by running a control query — the same selector with the discriminating predicate removed. If the control also returns nothing, report the query as inconclusive. Never convert an empty result into a positive finding.
- Never propose a mechanism you have not queried. If you want to explain why a population is unaffected, query it. If you cannot, list it under What I Could Not Determine.

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
6. Check the alert rules to see which alert is firing, if any. You may only READ alert state (using alerting_manage_rules with operation='list' or 'get'). Never create, modify, pause, or delete an alert rule. If a tool offers a write action, do not use it.

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
- When the failures appear to have started

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

Steps, in order:
1. Query Loki for FATAL render log lines. Read the actual error text.
2. Query Loki for asset resolution errors specifically.
3. Count error lines by node using `error_lines_by_node()` from queries.py unmodified. If the query itself returns empty, report the cross-check as NOT PERFORMED. Then explicitly compare the log-derived node set against Triage's metric-derived set and state whether they match.
4. Query Loki for asset publish events near the incident start time (pass `direction="backward"` and `limit=5` to the tool to get the newest first). A change
   that precedes the failures is a prime suspect. When correlating a trigger event with failure onset, compute the actual interval in minutes from the two timestamps and state it. Never describe an interval you have not calculated. If multiple publish events exist, use the most recent one preceding the first failure and say so.
5. Query Tempo for error traces on the render-farm service.
6. Inspect a failing trace in detail. Identify WHICH SPAN fails. Read that
   span's attributes carefully — particularly any asset version.
7. If you identify a suspect asset version, you MUST run a disconfirming query using exactly `all traces by asset`. Do not add status=ok, status!=error, or any status predicate to the disconfirming query. Its entire purpose is to see both outcomes.
   After identifying the affected node set, pick one node NOT in that set and query traces for it with the suspect asset version (using `traces by node/asset`). If it returns traces, the asset is NOT globally broken and the root cause must be scoped to the affected nodes.

Return:
- The exact error message, quoted verbatim
- The failing span name and its attributes
- The suspect asset version, if any
- Whether the log-derived node set matches the metric-derived node set
- A timeline: change published, first failure, alert fired
- Your root cause hypothesis, with a confidence level and the specific evidence
  supporting it. Before naming a root cause, establish its BLAST RADIUS and explain
  why the unaffected population is unaffected. If a resource appears broken but part
  of the fleet uses it successfully, the resource itself is not broken.
- What you could NOT determine

Do not assert a cause that only one signal supports. Say which signals agree. If unaffected nodes resolve the texture successfully, you must state: "The unaffected nodes resolved the texture successfully; whether that is due to a pre-existing local copy or a successful sync could not be determined from available telemetry." rather than inferring they had a local copy.
(Note on tool parameters: for query_loki_logs and tempo_traceql-search, omit start/startRfc3339 parameters or pass standard RFC3339 timestamps so the default recent window is searched).
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
2. Query mean render seconds and total node count using `query_prometheus`. 
3. Compute the rework and schedule impact as follows:
   rework = failed_frames × mean_render_seconds × GPU_COST_PER_SECOND
   schedule impact = (failed_frames × mean_render_seconds) / 3600 (Label it "machine-hours" explicitly — it is not wall-clock delay).
   estimated wall-clock slip = machine-hours / total node count.
4. Write a Grafana annotation recording the finding using `create_annotation` (with dashboardUid="second-unit-farm", tags=["second-unit", "root-cause"], text="...", time=...). Tag it `second-unit` and
   `root-cause` — the dashboard has an annotation query on the `second-unit` tag,
   so this makes the finding appear on every time-series panel. Keep the
   annotation text to one or two sentences naming the root cause and the blast
   radius. Set the time to the incident start where known.
5. Produce the written report. If a query for a value returns no data, write "unavailable" in the report. Do not substitute an inferred or remembered figure.

Report format:

**Incident:** one line
**Root cause:** one sentence, specific. Name the asset version if identified. State if it is globally broken or scoped to specific nodes.
**Blast radius:** frames failed, nodes affected, of how many total
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

Confirm whether the annotation write succeeded. If it failed, say so explicitly
rather than implying the record was created — someone will look for it.
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
