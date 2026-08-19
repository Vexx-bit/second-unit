# Task queue — Sprint 1

Work items for the IDE coding agent. Read `AGENTS.md` and
`docs/PROJECT_BRIEF.md` first — they contain hard constraints that disqualify the
project if violated.

Sprint 2 lives in `docs/TASKS-SPRINT2.md`.

## How to work through this file

- Do tasks **in order**. Later tasks depend on earlier ones.
- Each task has **acceptance criteria**. Do not mark a task done until every box
  is genuinely verified. Do not report success based on what a command *should*
  have done.
- If a task cannot be completed, **stop and report exactly what blocked you**.
  Do not substitute a different approach silently, and do not fabricate output.
- **Never commit `.env`, `mcp_config.json`, or any string starting with `glsa_`,
  `glc_`, or `github_pat_`.** CI rejects these and the repo is public.

### Reporting format

```
TASK-XX: DONE | BLOCKED
Evidence: <actual command output or tool result, quoted>
Deviations: <anything you did differently, and why>
```

---

## Status

| Task | State |
| --- | --- |
| TASK-01 Fix the Grafana stack URL | ✅ done |
| TASK-02 Re-run simulator, verify metric names | ✅ done |
| TASK-03 Import the render farm dashboard | ✅ done |
| TASK-04 Create the alert rule | ✅ done — uid `dfvmtt22674e8b` |
| TASK-05 Verify the incident end to end | ✅ done — see `docs/DEMO-NUMBERS.md` |
| TASK-05b Cap the run at TOTAL_FRAMES | ✅ done |
| TASK-05c Separate simulated render time from wall-clock | ✅ done |
| TASK-05d Frame-based deterministic incident onset | ✅ done (3252/748/14) |
| TASK-05e Guard incident_frame formula | ✅ done |
| TASK-06 ADK Agent Architecture & Tools | ✅ done |
| TASK-07 Execute live incident investigation | ✅ done |

**Confirmed stack values** — do not re-derive:

- Stack: `https://violetheron2036.grafana.net`
- Metrics: `grafanacloud-violetheron2036-prom`
- Logs: `grafanacloud-violetheron2036-logs`
- Traces: `grafanacloud-violetheron2036-traces`

**Frozen metric names** — verified against the live stack. Changing any of these
now requires updating `telemetry-sim/farm.py`, the dashboard JSON, and
`agent/second_unit/queries.py` together:

| Name | Type | Labels |
| --- | --- | --- |
| `render_frames_completed_total` | counter | `shot`, `node`, `status` |
| `render_cost_usd_total` | counter | `shot`, `node` |
| `render_frame_duration_seconds_{bucket,sum,count}` | histogram | `shot`, `status`, `le` |
| `render_node_gpu_utilization_percent` | gauge | `shot`, `node` |
| `render_queue_depth` | gauge | `shot` |

---

### TASK-03 — Import the render farm dashboard

Import `infra/grafana/dashboards/render-farm.json` into the stack.

**Preferred method — via MCP:**

Enumerate your Grafana tools and look for a dashboard-write tool (names vary by
`mcp-grafana` version; something like `update_dashboard`). If one exists, read the
JSON from disk and push it, preserving `"uid": "second-unit-farm"`.

The JSON uses datasource template variables `${prom}` and `${loki}`, which resolve
at view time. Leave them — do not hardcode UIDs into panel definitions.

**Fallback — if no dashboard-write tool exists:**

Read-only dashboard access is expected on some builds. Print these steps for the
human and move on:

> 1. Open https://violetheron2036.grafana.net
> 2. **Dashboards → New → Import**
> 3. Paste the contents of `infra/grafana/dashboards/render-farm.json`
> 4. **Load**
> 5. Map: **Metrics** → `grafanacloud-violetheron2036-prom`,
>    **Logs** → `grafanacloud-violetheron2036-logs`
> 6. **Import**

Do not reach the Grafana HTTP API directly with the service account token as a
workaround. Grafana is accessed through MCP in this project; bypassing it in
tooling sets the wrong precedent for the agent code.

**Acceptance criteria**

- [x] Dashboard `Second Unit — Render Farm` exists, uid `second-unit-farm`
- [x] Confirmed by a dashboard search/get MCP call, not by assumption
- [x] Over a range covering the TASK-05 incident, these panels show data: Frame
      outcomes, Failures by node, GPU utilization by node, Frame duration
      p50/p95, Queue depth
- [x] The Loki panel ("Render farm errors") returns the `texture not found` lines
- [x] Report which panels are empty and why, if any

---

### TASK-05b — Cap the simulator at TOTAL_FRAMES

**Bug surfaced by TASK-05.** The run reported `3552 succeeded, 841 failed` =
**4,393 frames**, but `farm.py` declares `TOTAL_FRAMES = 4000`. The run is not
bounded by that constant.

This matters for two reasons:

1. `render_queue_depth` is derived from remaining frames. If the run overshoots
   the total, queue depth is either going negative, clamping at zero, or wrapping
   — and the dashboard panel plus the agent's "how far behind are we?" reasoning
   both depend on it being meaningful.
2. A shot has a fixed frame count. Rendering 4,393 frames of a 4,000-frame shot
   is not a thing that happens, and a judge who reads the source will notice.

**Do:**

1. Read `telemetry-sim/farm.py` and determine why the frame loop exceeds
   `TOTAL_FRAMES`. Report the actual cause before changing anything.
2. Inspect what `render_queue_depth` reports once frames issued exceed
   `TOTAL_FRAMES`. Query it over the TASK-05 window:
   ```promql
   max(render_queue_depth)
   min(render_queue_depth)
   ```
3. Fix so the loop stops at `TOTAL_FRAMES` and exits cleanly, printing the
   summary as it does now. `--duration` should act as a **ceiling**, not a
   guarantee: whichever limit is hit first ends the run.
4. Keep the seed behaviour identical. **The affected-node count must remain
   exactly 14.** That determinism is a demo asset.

**Acceptance criteria**

- [x] Root cause of the overshoot reported in prose before the fix
- [x] `succeeded + failed <= 4000` on a full run
- [x] `min(render_queue_depth) >= 0` and it decreases monotonically toward zero
- [x] Affected node count still exactly **14**
- [x] Re-run the canonical demo command and record the new numbers in
      `docs/DEMO-NUMBERS.md`, replacing the current ones
- [x] Also record the measured `sum(increase(render_cost_usd_total[15m]))` — that
      value is currently TBD and the demo narration needs it

---

### TASK-05c — Separate simulated render time from wall-clock

**Bug surfaced by cost breakdown:** In `render_frame()`, the success path computed
`gpu_seconds` for cost but recorded `duration` (wall-clock, ~0.1s) into the
`frame_duration` histogram.

**Do:**
1. Raise simulated render time to realistic 4K path-traced values: `gpu_seconds = rng.uniform(180, 420)` (mean 300s).
2. Record `gpu_seconds` into the `frame_duration` histogram on success.
3. Record realistic simulated fail-fast duration (`rng.uniform(0.15, 0.45)`) on the failed path.
4. Keep wall-clock runtime at ~10 min for `--duration 600`.
5. Measure p95 duration, batch GPU spend, rework cost, and schedule impact.

**Acceptance criteria**

- [x] Affected node count still EXACTLY 14
- [x] `succeeded + failed <= 4000` (3,250 succeeded, 750 failed)
- [x] Wall-clock runtime ~10 min for `--duration 600`
- [x] `histogram_quantile(0.95, ...)` returns value in low hundreds of seconds (~476s)
- [x] `sum(increase(render_cost_usd_total[15m]))` in low thousands of USD ($3,949.68)
- [x] Rework cost computed and recorded: 750 frames × 300s × $0.0041/s = $922.50
- [x] Schedule impact computed and recorded: (750 frames × 300s) / 40 nodes = 1.56 hours (~1h 34m)
- [x] Updated `docs/DEMO-NUMBERS.md` with all new measured values
- [x] Updated `docs/PROJECT_BRIEF.md` with measured rework figure ($922.50)
- [x] Pushed to `sprint/1-telemetry-dashboard` updating PR #1

---

## Completed task records

### TASK-05 — Verify the incident end to end ✅

All signals confirmed: 14 nodes exactly, `v7` in logs and traces, `asset_fetch`
as the failing span, GPU inversion visible, alert firing.

**Correction to this task's original criteria:** it specified 150–260 failed
frames. That range was an estimate written before any data existed and was
simply wrong — it did not account for 480 seconds of incident at 1x speed. The
observed 841 is correct simulator behaviour. The expectation was at fault, not
the code. Measured values now live in `docs/DEMO-NUMBERS.md`.

Note for future tasks: when a stated expectation conflicts with clean, internally
consistent observed output, report it rather than tuning the code to satisfy the
number. That was the correct call here and it caught a real bug (TASK-05b).
