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

Observed 2026-08-19 via Grafana MCP queries. These supersede all earlier
estimates. **Note:** These numbers apply strictly and ONLY to the canonical command:
`uv run farm.py --duration 600 --inject-incident --incident-at 120`. Non-canonical durations or incident-at settings shift the frame calculations.

| Value | Measured | Notes |
| --- | --- | --- |
| Frames succeeded | 3,252 | |
| Frames failed | **748** | `increase(...[15m])` reads ~760 — extrapolation artefact, see below |
| Total frames | 4,000 | 3,252 succeeded + 748 failed (strictly deterministic given seed 42) |
| Nodes affected | **14** | of 40. Seed-locked, exact, reproducible |
| Nodes healthy | 26 | |
| Failure ratio on affected nodes | ~2 in 3 of their frames | affected nodes fail only when `frame % 3 != 0`, not 100% |
| Frame duration (p95) | ~476s | simulated 4K path-traced render time (3–7 min range) |
| GPU utilization, affected | 4–18% | drops — nodes fail fast instead of rendering |
| GPU utilization, healthy | 82–99% | |
| Alert rule UID | `dfvmtt22674e8b` | reaches `Firing` ~4 min in |
| Failing span | `asset_fetch` | `error.type=AssetResolutionError` |
| Asset version | `v7` | simulator's healthy predecessor is `v6` |
| Broken texture | `/assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | |
| Total GPU spend | **$3,949.68** | measured via `sum(increase(render_cost_usd_total[15m]))` |
| Rework cost (failed frames) | **$920.04** | 748 frames × 300s mean × $0.0041/s |
| Schedule impact | **1.56 hours** | (748 frames × 300s) / 40 nodes = 5,610s (~1h 34m delay) |

### Determinism

Given the default seed (`--seed 42`) and frame-based incident onset (`incident_frame = 801`),
the run is strictly deterministic and byte-identical across runs regardless of host CPU speed or scheduling.

### Why the PromQL count differs from the simulator count

The simulator prints `748 failed`. `increase()` over 15 minutes reads ~760.

Both are correct. `increase()` extrapolates to the window edges and returns a
float, so it will not exactly match a discrete counter total. When quoting a
number to a human, use the simulator's integer or round the PromQL result — and
never present a fractional frame count.

## Narration guidance

Use **748 frames**, **14 of 40 nodes**, **$920.04 rework cost** ($3,949.68 total batch spend), and **1.56 hours delivery delay**. All are real, measured, and
reproducible.

The strongest line available is the GPU utilization inversion: the failing nodes
look *idle*, at 4–18%, while healthy ones sit at 82–99%. A dashboard glance
suggests those 14 nodes are underused and available for more work. They are
actually burning through the queue failing instantly. That is precisely the kind
of cross-signal read a human skims past at 6am and an agent does not.

Film the GPU panel with a **time range**, not an instant query — the split is
only legible as two bands over time.

## Observed live run (non-canonical)

792 failed, 14 of 40 nodes, $3,876 total spend, $948.15 rework, 64.34 machine-hours, 1.61h wall-clock slip, alert fired 13:19:40Z.

Measured timeline for that run, all UTC:

| Event | Timestamp (UTC) | Source |
| --- | --- | --- |
| Asset `v7` publish log line | 13:55:57Z | Loki, bounded window |
| First non-zero failure sample | 13:56:30Z | `query_prometheus` range, 30s step |
| Failures tail off | ~14:04:30Z | same range query |

**Publish → onset interval: ~33 seconds.** This is the correct figure.

## Corrections log

Figures below were produced by earlier runs and must never be quoted again.

| Retired figure | Why it is wrong |
| --- | --- |
| "7.6 minutes after publish" | The agent read a newest-first (`direction: "backward"`) unbounded FATAL query and treated the **last** failure as the first. Real interval is ~33s. |
| 1,565 frames failed / $7,873.06 / $1,875.33 rework / 127.1 machine-hours / 3.18h | Contaminated 30m window spanning **two** simulator runs, presented as one incident. |
| "successful traces show `skin_albedo.v6.exr`" | Fabricated. Once the incident fires, `asset_version=v7` is on **all** frames including the 26 healthy nodes. No v6 span attribute exists post-incident. |
| "near-100% failure rates" on affected nodes | Overstated. Affected nodes fail only when `frame % 3 != 0`, about 2 of every 3 frames. |
| 49–50 FATAL lines per node | Correct for the accepted run only. The same query over a contaminated window read 57–58. |
| $21.33, $4.92, ~$312 wasted, ~200 failures, 3.2h behind dailies, $4,091 wasted, 3250/750, 3249/751, 3552/841/4393 | Superseded by the canonical seed-locked run. |
