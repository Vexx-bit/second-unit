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
| Frame duration (p95) | ~476s | simulated 4K path-traced render time (3–7 min range) |
| GPU utilization, affected | 4–18% | drops — nodes fail fast instead of rendering |
| GPU utilization, healthy | 82–99% | |
| Alert rule UID | `dfvmtt22674e8b` | reaches `Firing` ~4 min in |
| Failing span | `asset_fetch` | `error.type=AssetResolutionError` |
| Asset version | `v7` | healthy predecessor was `v6` |
| Broken texture | `/assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | |
| Total GPU spend | **~$3,940** | measured via `sum(increase(render_cost_usd_total[15m]))` |
| Rework cost (failed frames) | **$920.04** | 748 frames × 300s mean × $0.0041/s |
| Schedule impact | **1.56 hours** | (748 frames × 300s) / 40 nodes = 5,610s (~1h 34m delay) |

### Determinism

Given the default seed (`--seed 42`) and frame-based incident onset (`incident_frame = 801`),
the run is strictly deterministic and byte-identical across runs regardless of host CPU speed or scheduling.

### Measured GPU spend

```promql
sum(increase(render_cost_usd_total[15m]))
```

The measured total GPU spend across the 15-minute run window is **~$3,940**.

### Why the PromQL count differs from the simulator count

The simulator prints `748 failed`. `increase()` over 15 minutes reads ~760.

Both are correct. `increase()` extrapolates to the window edges and returns a
float, so it will not exactly match a discrete counter total. When quoting a
number to a human, use the simulator's integer or round the PromQL result — and
never present a fractional frame count.

## Narration guidance

Use **748 frames**, **14 of 40 nodes**, **$920.04 rework cost** (~$3,940 total batch spend), and **1.56 hours delivery delay**. All are real, measured, and
reproducible.

The strongest line available is the GPU utilization inversion: the failing nodes
look *idle*, at 4–18%, while healthy ones sit at 82–99%. A dashboard glance
suggests those 14 nodes are underused and available for more work. They are
actually burning through the queue failing instantly. That is precisely the kind
of cross-signal read a human skims past at 6am and an agent does not.

## Observed live run (non-canonical)

During the interactive 15-minute live run (`--duration 900 --inject-incident --incident-at 120`), the investigation was triggered after 7 minutes. Because the Prometheus queries use a 30-minute lookback window (`increase(...[30m])`), the metrics aggregated failures from the preceding 10-minute run as well. 

The reported figures for that specific live observation were:
*   **Frames failed:** 1,565 (sum of both recent sim runs)
*   **Nodes affected:** 14 of 40 (consistent blast radius)
*   **Total GPU spend:** $7,873.06
*   **Rework cost:** $1,875.33
*   **Schedule impact:** 127.1 machine-hours (estimated 3.18 hours wall-clock slip)
