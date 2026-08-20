# Canonical demo run

Every number spoken in the demo video, written in the report, or quoted on the
Devpost submission must come from **this exact command**. The simulator is
seeded, so it is reproducible — which means the numbers can be rehearsed, and a
judge re-running it sees the same incident.

```powershell
cd C:\Users\vexx\second-unit\telemetry-sim
uv run farm.py --duration 600 --inject-incident --incident-at 120
```

10 minutes wall clock: 2 minutes healthy, then asset `v7` publishes and frames
begin failing.

## Run the clean-window gate first

```powershell
cd C:\Users\vexx\second-unit\agent
uv run python check_window.py
```

This is not optional before a filmed run. Both Prometheus and Loki queries look
back 30 minutes, and the MCP log/trace tools default to a 1 hour lookback. If a
previous run is still inside either window, two separate incidents get merged
into one result set and every derived number is wrong. `check_window.py` exits
non-zero and tells you how many minutes to wait.

## Measured values

Observed 2026-08-19 and re-verified 2026-08-20 via Grafana MCP queries. These
supersede all earlier estimates. **Note:** these numbers apply strictly and ONLY
to the canonical command above. Non-canonical durations or `--incident-at`
settings shift the frame calculations.

| Value | Measured | Notes |
| --- | --- | --- |
| Frames succeeded | 3,252 | from the simulator's own end-of-run summary |
| Frames failed | **748** | `increase()` reads 706–760 depending on window, see below |
| Total frames | 4,000 | 3,252 succeeded + 748 failed (strictly deterministic given seed 42) |
| Nodes affected | **14** | of 40. Seed-locked, exact, reproducible |
| Nodes healthy | 26 | proven-healthy control node: `render-04` |
| Failure ratio on affected nodes | 0.62–0.65 | affected nodes fail only when `frame % 3 != 0`, not 100% |
| Frame duration (p95) | ~476s | simulated 4K path-traced render time (3–7 min range) |
| GPU utilization, affected | 4–18% | drops — nodes fail fast instead of rendering |
| GPU utilization, healthy | 82–99% | |
| Alert rule UID | `dfvmtt22674e8b` | reaches `Firing` ~7 min in |
| Failing span | `asset_fetch` | `error.type=AssetResolutionError` |
| Asset version | `v7` | see the v6 warning in the corrections log |
| Broken texture | `/assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | |
| Total GPU spend | **$3,949.68** | measured via `sum(increase(render_cost_usd_total[15m]))` |
| Rework cost (failed frames) | **$920.04** | 748 frames × 300s mean × $0.0041/s |
| Schedule impact | **1.56 hours** | (748 × 300s) / 40 nodes = 5,610s wall-clock slip |

### Determinism

Given the default seed (`--seed 42`) and the frame-based incident onset
(`incident_frame = 801`), the run is strictly deterministic and identical across
runs regardless of host CPU speed or scheduling. Seven consecutive runs printed
`render summary: 3252 succeeded, 748 failed`.

The sharper proof is at the level of an individual frame. Frame 801 succeeds
(`801 % 3 == 0`), so the first FAILING frame is **802**, dispatched to
**render-03**. That exact frame on that exact node was the first failure in two
separate independent runs, at 11:00:04.659Z and 11:41:04.028Z. Determinism at
the frame level, not just in the totals.

### Why the PromQL count differs from the simulator count

The simulator prints `748 failed`. `increase()` over 15 minutes reads ~760; over
30 minutes it has read as low as **706**, about 5.6% low.

Both are artefacts of the same thing. `increase()` extrapolates to the window
edges and returns a float, so it cannot exactly match a discrete counter total,
and the error direction depends on where the window boundaries fall relative to
the burst. Treat every `increase()`-derived count as **approximate**. The
authoritative count is the simulator's own end-of-run summary line, which is
printed to the terminal and is not exported as telemetry — which means the agent
cannot observe it and must never quote it. Narrate that comparison yourself.

A queue depth of 0 means the render is **complete**. It does not mean the counts
are exact. Those are two different claims and conflating them was a defect.

## Narration guidance

Use **748 frames**, **14 of 40 nodes**, **$920.04 rework cost** ($3,949.68 total
batch spend), and **1.56 hours** of wall-clock slip. All are real, measured, and
reproducible.

The strongest line available is the GPU utilization inversion: the failing nodes
look *idle*, at 4–18%, while healthy ones sit at 82–99%. A dashboard glance
suggests those 14 nodes are underused and available for more work. They are
actually burning through the queue failing instantly. That is precisely the kind
of cross-signal read a human skims past at 6am and an agent does not.

Film the GPU panel with a **time range**, not an instant query — the split is
only legible as two bands over time.

## Measured incident timeline

From the validated run of 2026-08-20, all values UTC, each one re-queried
directly against Prometheus, Loki and Tempo rather than taken from the agent's
own report.

| Event | Timestamp (UTC) | Source |
| --- | --- | --- |
| Asset `v7` publish log line | 11:41:03.854Z | Loki, bounded window |
| First FATAL log line (frame 802, render-03) | 11:41:04.028Z | Loki, `direction: "forward"` |
| First non-zero failure metric sample | 11:41:30.797Z | `query_prometheus` range, 30s step |
| Alert transitions to Firing | 11:48:40Z | `alerting_manage_rules` |

**Publish → first failure: ~174 milliseconds.** This is the real interval, and it
is the number to quote. The simulator logs the publish and then fails the very
next frame it dispatches, so cause and effect are effectively simultaneous.

**Publish → metric onset: ~26.8 seconds.** This is a *scrape and range-step
artefact*, not a delay in the system. The metric onset is the first non-zero
sample of a 30-second-step range query, so it lags the true first failure by up
to one step. Quote it only alongside the 174 ms figure and only labelled as the
lagging signal.

The two figures being 150× apart is itself worth saying out loud: it is exactly
why the agent is instructed to compare log against log and never against the
metric onset.

## Agent self-observability

The validated run is traced end to end in Tempo as
`58ba2a4c6a3c6f7672b718f08d898bb2`: **95 spans**, 4m 48s total, split
`triage` 1m 54s → `correlate` 1m 42s → `report` 1m 12s, with 27 tool calls and
per-call token counts. The captured `system_instruction` on the report stage
matches the committed prompt verbatim, which is how a run's provenance is proven
rather than asserted.

## Corrections log

Figures and claims below were produced by earlier runs and must never be quoted
again. Kept deliberately: an agent that is trusted because its failures were
hidden is not trustworthy.

| Retired figure or claim | Why it is wrong |
| --- | --- |
| **"Publish → onset ≈ 33 seconds"** | Mine, and wrong. It compared the publish log line against the METRIC onset, which lags the true first failure by up to one range step and was measured lagging by 26.8s. Log against log, the interval is ~174ms, measured twice (173ms and 174ms on separate runs). |
| "7.6 minutes after publish" | The agent read a newest-first (`direction: "backward"`) unbounded FATAL query and treated the **last** failure as the first. |
| "42 minutes" publish → onset | Derived from a hallucinated onset date (`2026-07-25T23:35:24Z`) after the stage skipped its mandated range query. |
| 706 frames failed, presented as final | `increase()` over 30 minutes reads ~5.6% low against the true 748. The count was correct as an approximation and wrong as a final figure; the run had genuinely completed, which is a different claim. |
| "failure ratio ≈ 54%" | Derived from the 706 reading. Measured ratio is 0.62–0.65. |
| "near-100% failure rates" on affected nodes | Overstated. Affected nodes fail only when `frame % 3 != 0`, about 2 of every 3 frames. |
| 1,565 frames failed / $7,873.06 / $1,875.33 rework / 127.1 machine-hours / 3.18h | Contaminated 30m window spanning **two** simulator runs, presented as one incident. |
| 819.88 failed / 4,246.71 succeeded / $5,282.27 | Same contamination, recurring on 2026-08-20. |
| "successful traces show `skin_albedo.v6.exr`" → "roll back to v6" | Fabricated, and the most dangerous entry here because it produced a confident and actionable recommendation. Once the incident fires, `asset_version=v7` is on **all** frames including the 26 healthy nodes. No v6 span attribute exists post-incident. |
| `2026-08-08T11:50:04.551Z`, `2026-08-19T13:21:06.341Z`, `2026-07-25T23:35:24Z` | Epoch → RFC3339 conversions done by the model in its head, off by up to twelve days. Fixed in `83097894` by moving all conversion into `timewindow.py`. |
| "the asset is globally broken" from `{... && span.asset.version="v7" && status=ok}` returning empty | Successful OTel spans are `STATUS_CODE_UNSET`, not `ok`, so that query cannot return anything. An empty result from an impossible query was read as a positive finding. |
| "a valid local copy of the texture" / "a transient network issue during the sync" / "a pre-existing local copy on the unaffected nodes" | Unqueried mechanisms invented to explain why 26 nodes were healthy. |
| "three of the failing nodes show high GPU utilization — possibly a different failure mode" | Sampling, not a second failure mode. A gauge caught mid-way through one of an affected node's successful frames reads high. |
| "the asset publish event is absent from the window" | It was 173ms inside the window. Two independent causes, both silent: a non-indexed label (`shot=`) in a Loki stream selector matches zero streams, and `endRfc3339` was clamped to the first-failure timestamp. Fixed in `b4daa71`. |
| 49–50 FATAL lines per node | Correct for one accepted run only. The same query over a contaminated window read 57–58. |
| $21.33, $4.92, ~$312 wasted, ~200 failures, 3.2h behind dailies, $4,091 wasted, 48.11 machine-hours, 3250/750, 3249/751, 3552/841/4393, $922.50, 750 frames | Superseded by the canonical seed-locked run. |

### Process corrections

| Problem | Fix |
| --- | --- |
| Three runs analysed as agent reasoning failures were actually a working tree behind `origin/main` | `run_investigation.py` now prints the commit under test at startup (`47bd8b4`) |
| A gauge (`render_queue_depth`) used as a liveness probe reported a healthy finished run as having no telemetry | Probe a counter instead, with retries for ingest lag (`14421029`) |
| The investigation run after the simulator exited, against dead telemetry | Start the investigation **into** the run, roughly 8 minutes in |
