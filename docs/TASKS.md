# Task queue

Work items for the IDE coding agent. Read `AGENTS.md` and
`docs/PROJECT_BRIEF.md` first — they contain hard constraints that disqualify the
project if violated.

## How to work through this file

- Do tasks **in order**. Later tasks depend on earlier ones.
- Each task has **acceptance criteria**. Do not mark a task done until every box
  is genuinely verified. Do not report success based on what a command *should*
  have done.
- If a task cannot be completed, **stop and report exactly what blocked you**.
  Do not substitute a different approach silently, and do not fabricate output.
- When you finish a task, tick its boxes in this file and commit that change on
  your working branch.
- **Never commit `.env`, `mcp_config.json`, or any string starting with `glsa_`,
  `glc_`, or `github_pat_`.** CI rejects these and the repo is public.

### Reporting format

After each task, report:

```
TASK-XX: DONE | BLOCKED
Evidence: <actual command output or tool result, quoted>
Deviations: <anything you did differently, and why>
```

---

## Sprint 1 — Telemetry and dashboards

### TASK-01 — Fix the Grafana stack URL

The `.env` file contains a guessed stack hostname. The real stack is
`violetheron2036.grafana.net`.

**Do:**

1. In `C:\Users\vexx\second-unit\.env`, set exactly:
   ```
   GRAFANA_URL=https://violetheron2036.grafana.net
   ```
   No trailing slash, no surrounding quotes.
2. Update the same value in the Antigravity MCP config (`mcp_config.json`) if it
   carries a `GRAFANA_URL`, then reload MCP servers.

**Acceptance criteria**

- [ ] `.env` contains the correct hostname
- [ ] A Grafana MCP tool call succeeds against the stack (e.g. list datasources)
      and returns real datasource names
- [ ] `.env` is still untracked by git (`git status` must not list it)

---

### TASK-02 — Re-run the simulator with corrected metric units

Metric units changed so the Prometheus names are predictable. Data emitted
before this change used a different gauge name and must be superseded.

**Do:**

```powershell
cd C:\Users\vexx\second-unit
git pull
cd telemetry-sim
uv run farm.py --duration 1800 --speed 10
```

This backfills ~30 minutes of healthy baseline in ~3 minutes. Let it finish; it
prints a render summary on exit.

**Acceptance criteria**

- [ ] Run completes and prints `render summary: N succeeded, 0 failed`
- [ ] No exporter errors (401, 403, connection refused) in the output
- [ ] Metric discovery returns exactly these five names — verify with a Grafana
      MCP Prometheus query, do not assume:
      ```promql
      group by (__name__) ({__name__=~"render_.*"})
      ```
      Expected: `render_frames_completed_total`, `render_cost_usd_total`,
      `render_frame_duration_seconds_bucket` (plus `_sum`/`_count`),
      `render_node_gpu_utilization_percent`, `render_queue_depth`
- [ ] **If any name differs**, do NOT edit the dashboard to match. Report the
      actual names — the mismatch means the unit-to-suffix mapping needs fixing
      at the source in `farm.py`, so that the agent, dashboard, and simulator
      stay consistent.

---

### TASK-03 — Import the render farm dashboard

Import `infra/grafana/dashboards/render-farm.json` into the stack.

**Preferred method — via MCP:**

First enumerate your available Grafana tools and look for a dashboard-write tool
(names vary by `mcp-grafana` version; something like `update_dashboard`). If one
exists:

1. Read the JSON file from disk
2. Resolve the real datasource UIDs by listing datasources — the Prometheus one
   is typically `grafanacloud-<stack>-prom`, the Loki one
   `grafanacloud-<stack>-logs`. **Confirm, do not assume.**
3. The JSON uses datasource template variables `${prom}` and `${loki}`. Those
   resolve at view time and are correct as-is — do not hardcode UIDs into panel
   definitions.
4. Push the dashboard, preserving `"uid": "second-unit-farm"`

**Fallback — if no dashboard-write tool exists:**

The server may be read-only for dashboards. That is expected on some versions.
In that case, print these instructions for the human and stop:

> 1. Open https://violetheron2036.grafana.net
> 2. **Dashboards → New → Import**
> 3. Paste the full contents of `infra/grafana/dashboards/render-farm.json`
>    into the *"Import via dashboard JSON model"* box
> 4. Click **Load**
> 5. Map the datasource prompts: **Metrics** → the `grafanacloud-*-prom`
>    datasource, **Logs** → the `grafanacloud-*-logs` datasource
> 6. Click **Import**

Do not attempt to reach the Grafana HTTP API directly with the service account
token as a workaround. The project rule is that Grafana is reached through MCP;
bypassing it in tooling sets the wrong precedent for the agent code.

**Acceptance criteria**

- [ ] Dashboard `Second Unit — Render Farm` exists, uid `second-unit-farm`
- [ ] Confirmed by a dashboard search/get MCP call, not by assumption
- [ ] At time range "Last 1 hour", these panels show data: Frame outcomes,
      GPU utilization by node, Frame duration p50/p95, Queue depth
- [ ] The Loki panel ("Render farm errors") is empty — correct, since no
      incident has been injected yet
- [ ] Report which panels are empty and why, if any of the above are blank

---

### TASK-04 — Create the alert rule

The agent's investigation is triggered by a firing alert, so this rule is a
functional dependency of the agent, not decoration.

Spec (full walkthrough in `infra/grafana/README.md`):

- **Name:** `Render farm frame failures`
- **Query A** (Prometheus, code mode):
  ```promql
  sum(rate(render_frames_completed_total{status="failed"}[5m]))
  ```
- **Condition B:** Threshold on `A`, `IS ABOVE` `0.1`
- **Folder:** `Second Unit` · **Evaluation group:** `render-farm`
- **Evaluate every:** `1m` · **Pending period:** `1m`
- **Labels:** `shot=SH042_beach_dusk`, `team=vfx`, `service=render-farm`
- **Summary:** `Frames are failing on the render farm for {{ $labels.shot }}`

Check for an alert-rule-write MCP tool. Most `mcp-grafana` builds expose alert
rule **reads** only, so expect to fall back to guiding the human through the UI
(**Alerting → Alert rules → New alert rule**).

**Acceptance criteria**

- [ ] Rule exists and is listed by an alert-rule MCP call
- [ ] State is `Normal` while the farm is healthy
- [ ] The three labels are present — the agent matches on them
- [ ] Record the rule UID in your report; the agent will reference it

---

### TASK-05 — Verify the incident end to end

Prove the full scenario produces the signals the agent must correlate.

**Do:**

```powershell
cd C:\Users\vexx\second-unit\telemetry-sim
uv run farm.py --duration 600 --inject-incident --incident-at 120
```

Let it run the full 10 minutes. Two minutes of healthy baseline, then asset v7
breaks and frames start failing.

Then verify each signal independently via MCP:

1. **Metrics** — failed frames and blast radius:
   ```promql
   sum(increase(render_frames_completed_total{status="failed"}[15m]))
   count(count by (node) (increase(render_frames_completed_total{status="failed"}[15m]) > 0))
   ```
2. **Logs** — the error text:
   ```logql
   {service_name="render-farm"} |= "texture not found"
   ```
3. **Traces** — the shared failing span. Query Tempo for traces on service
   `render-farm` with errors, and confirm the failing `asset_fetch` span carries
   `asset.version=v7`.
4. **Alert** — confirm the rule moved to `Firing`.

**Acceptance criteria**

- [ ] Failed frame count is in the 150–260 range
- [ ] Affected node count is **exactly 14**
- [ ] Loki returns log lines containing
      `/assets/SH042_beach_dusk/tex/skin_albedo.v7.exr`
- [ ] Tempo returns error traces whose `asset_fetch` span has
      `asset.version=v7`
- [ ] GPU utilization on affected nodes **drops** into the 4–18% band while
      unaffected nodes stay 82–99% — this counter-intuitive signal is a key
      demo beat, so confirm it visibly
- [ ] Alert rule reached `Firing`
- [ ] Record the exact numbers observed. The demo video narration must match
      them, and the seed makes them reproducible.

---

## Sprint 2 — The agent (not yet specified)

Do not start these. The `agent/` package will be scaffolded once Sprint 1 is
verified, so that its queries are written against confirmed metric names and a
known-good alert rule rather than assumptions.

Planned: ADK agent crew (Triage → Correlate → Report), `McpToolset` wired to a
self-hosted `mcp-grafana` over streamable-http, annotation writing, and
OpenTelemetry self-instrumentation into Grafana Cloud AI Observability.
