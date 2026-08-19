# Task queue — Sprint 2 (the agent)

Sprint 1 lives in `docs/TASKS.md`. Finish TASK-05 before starting TASK-06.

Same rules apply: work in order, verify with real output, quote it, never commit
secrets, stop and report when blocked. Do not silently substitute an approach.

---

### TASK-06 — Verify the ADK and MCP API surfaces

The `agent/` package was written against documented API surfaces that have
changed names across ADK releases. **Confirm the real names before running
anything.** This task exists to prevent an afternoon lost to import errors.

**Do:**

1. Install the agent package:
   ```powershell
   cd C:\Users\vexx\second-unit\agent
   uv sync
   ```
2. Record the resolved version:
   ```powershell
   uv run python -c "import google.adk; print(google.adk.__version__)"
   ```
3. Determine which class names actually exist in that version:
   ```powershell
   uv run python -c "import google.adk.tools.mcp_tool as m; print([n for n in dir(m) if 'ool' in n or 'aram' in n or 'onnection' in n])"
   ```
   Cross-check against https://adk.dev/api-reference/python/ for the installed
   version. The candidates the shim tries are in
   `agent/second_unit/mcp_tools.py`.
4. Confirm the toolset resolves at all:
   ```powershell
   uv run python -c "from second_unit.mcp_tools import build_grafana_toolset; build_grafana_toolset(); print('toolset ok')"
   ```
5. **Then simplify.** Replace the `_resolve` shim with direct imports of the
   names that exist, and pin the confirmed `google-adk` version in
   `agent/pyproject.toml` (`>=X.Y,<X.Y+1`). The shim is scaffolding for an
   unknown; once known, it is just noise.
6. List the tools your `mcp-grafana` build exposes and compare against the
   `TRIAGE_TOOLS`, `CORRELATE_TOOLS`, and `REPORT_TOOLS` allowlists. **A tool
   name that does not exist is silently dropped by the filter — no error.** So a
   typo here shows up as an agent that mysteriously cannot query logs. Correct
   any names that differ; in particular confirm the real names for the Loki
   query, Tempo query, and annotation-write tools.

**Acceptance criteria**

- [ ] `google-adk` version recorded in your report and pinned in `pyproject.toml`
- [ ] Shim replaced with direct imports; `mcp_tools.py` has no `importlib`
- [ ] `build_grafana_toolset()` returns without raising
- [ ] Every name in all three allowlists exists in your `mcp-grafana` build, or
      has been corrected — list the corrections explicitly
- [ ] `uv run ruff check .` passes in `agent/`

---

### TASK-07 — Run Triage against a live incident

**Do:**

1. In one terminal, start an incident:
   ```powershell
   cd C:\Users\vexx\second-unit\telemetry-sim
   uv run farm.py --duration 900 --inject-incident --incident-at 120
   ```
2. Wait for the alert to fire (~4 minutes), then in a second terminal:
   ```powershell
   cd C:\Users\vexx\second-unit\agent
   uv run adk web
   ```
3. Open the web UI, select `second_unit`, and send:
   `Frames are failing on SH042_beach_dusk. Investigate.`

**Acceptance criteria**

- [ ] All three stages run in order without exceptions
- [ ] Triage reports **exactly 14** affected nodes and a failed frame count
      matching what TASK-05 observed
- [ ] Triage notes the GPU utilization drop as corroborating evidence, not as a
      contradiction or a sign of health
- [ ] Correlate quotes the real error text and identifies asset version **v7**
- [ ] Correlate names `asset_fetch` as the failing span
- [ ] Report produces the structured report with a concrete recommended action
- [ ] **No invented metric names anywhere.** If a stage queries a name not in
      `queries.py`, that is a prompt failure — report the invented name verbatim
      so the instruction can be tightened.

Paste the full transcript of all three stages into your report. Do not summarise
it — the wording is what gets tuned.

---

### TASK-08 — Confirm the annotation write

The agent writing back to Grafana is the project's main differentiator. Most
submissions will only read. Verify it truly happens.

**Acceptance criteria**

- [ ] An annotation tagged `second-unit` exists, created by the agent
- [ ] Confirmed by an MCP annotation/dashboard read, not just by the agent
      claiming success
- [ ] It appears as a marker on the `second-unit-farm` dashboard time-series
      panels — screenshot this, it is a demo shot
- [ ] Its text names the root cause and blast radius in one or two sentences
- [ ] If the write failed, report the exact error. A likely cause is the service
      account having **Viewer** instead of **Editor** — annotations are a write.

---

### TASK-09 — Self-observation

The agent emits its own traces to Grafana Cloud (`agent/second_unit/telemetry.py`).

**Acceptance criteria**

- [ ] Traces for service `second-unit-agent` appear in Tempo after a run
- [ ] They are visible in **Application Observability** / AI Observability
- [ ] The render farm and the agent are both visible in the same stack — the
      incident and the responder side by side. Screenshot this.
- [ ] Report whether model calls appear as spans, and what attributes they carry

---

## Not yet specified

After TASK-09: Cloud Run deployment of `mcp-grafana` plus the agent (`infra/`),
the `web/` Next.js UI on Vercel, and the demo recording. Those depend on how
TASK-07's transcript reads, so they stay unwritten until then.
