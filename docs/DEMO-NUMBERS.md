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
estimates.

| Value | Measured | Notes |
| --- | --- | --- |
| Frames succeeded | 3,552 | |
| Frames failed | **841** | `increase(...[15m])` reads ~850.6 — extrapolation artefact, see below |
| Nodes affected | **14** | of 40. Seed-locked, exact, reproducible |
| Nodes healthy | 26 | |
| GPU utilization, affected | 4–18% | drops — nodes fail fast instead of rendering |
| GPU utilization, healthy | 82–99% | |
| Alert rule UID | `dfvmtt22674e8b` | reaches `Firing` ~4 min in |
| Failing span | `asset_fetch` | `error.type=AssetResolutionError` |
| Asset version | `v7` | healthy predecessor was `v6` |
| Broken texture | `/assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | |
| GPU spend wasted | **TBD** | must be measured — see below |

### Still to measure

Run this and record the result here:

```promql
sum(increase(render_cost_usd_total[15m]))
```

The earlier "$312 wasted" figure in the project brief was an estimate made before
any data existed. **Do not use it.** Replace it with the measured value, and
prefer quoting only the spend attributable to failed frames if that can be
isolated by label.

### Why the PromQL count differs from the simulator count

The simulator printed `841 failed`. `increase()` over 15 minutes reads ~850.6.

Both are correct. `increase()` extrapolates to the window edges and returns a
float, so it will not exactly match a discrete counter total. When quoting a
number to a human, use the simulator's integer or round the PromQL result — and
never present a fractional frame count.

## Narration guidance

Use **841 frames** and **14 of 40 nodes**. Both are real, measured, and
reproducible.

The strongest line available is the GPU utilization inversion: the failing nodes
look *idle*, at 4–18%, while healthy ones sit at 82–99%. A dashboard glance
suggests those 14 nodes are underused and available for more work. They are
actually burning through the queue failing instantly. That is precisely the kind
of cross-signal read a human skims past at 6am and an agent does not.
