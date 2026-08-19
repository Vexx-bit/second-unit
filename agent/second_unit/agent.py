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
6. Check the alert rules to see which alert is firing, if any.

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
3. Count error lines by node. Cross-check against the affected nodes Triage
   identified. If the two sets disagree, say so — that disagreement is itself a
   finding.
4. Query Loki for asset publish events near the incident start time. A change
   that precedes the failures is a prime suspect.
5. Query Tempo for error traces on the render-farm service.
6. Inspect a failing trace in detail. Identify WHICH SPAN fails. Read that
   span's attributes carefully — particularly any asset version.
7. If you identify a suspect asset version, query traces carrying that version
   to confirm the correlation holds broadly rather than in one trace.

Return:
- The exact error message, quoted verbatim
- The failing span name and its attributes
- The suspect asset version, if any
- Whether the log-derived node set matches the metric-derived node set
- A timeline: change published, first failure, alert fired
- Your root cause hypothesis, with a confidence level and the specific evidence
  supporting it
- What you could NOT determine

Do not assert a cause that only one signal supports. Say which signals agree.
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
1. Find the dashboard with uid `second-unit-farm`.
2. Write a Grafana annotation recording the finding. Tag it `second-unit` and
   `root-cause` — the dashboard has an annotation query on the `second-unit` tag,
   so this makes the finding appear on every time-series panel. Keep the
   annotation text to one or two sentences naming the root cause and the blast
   radius. Set the time to the incident start where known.
3. Produce the written report.

Report format:

**Incident:** one line
**Root cause:** one sentence, specific. Name the asset version if identified.
**Blast radius:** frames failed, nodes affected, of how many total
**Cost:** GPU spend wasted, and how far behind the shot is
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
