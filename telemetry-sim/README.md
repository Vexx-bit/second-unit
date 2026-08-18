# telemetry-sim

A synthetic VFX render farm. It emits believable metrics, logs, and traces over
OTLP to Grafana Cloud so that the Second Unit agent has real observability data
to investigate.

This is the foundation of the whole project: the agent can only be as convincing
as the telemetry it queries.

## What it simulates

**Shot `SH042_beach_dusk`**, 4,000 frames, distributed across a 40-node farm.
Each frame is a trace with four child spans:

```
render_frame
  ├─ asset_fetch     (pulls textures/geo from the asset store)
  ├─ rasterize       (the expensive GPU work)
  ├─ composite       (denoise + comp passes)
  └─ publish         (writes the EXR to the shot directory)
```

### Signals emitted

| Signal | Name | Notes |
| --- | --- | --- |
| Counter | `render.frames.completed` | attrs: `shot`, `node`, `status` |
| Counter | `render.cost.usd` | GPU-seconds × rate, per shot/node |
| Histogram | `render.frame.duration` | seconds per frame |
| Gauge | `render.node.gpu.utilization` | percent, per node |
| Gauge | `render.queue.depth` | frames still pending, per shot |
| Logs | — | structured render log lines, ERROR on failure |
| Traces | `render_frame` | one trace per frame, failures marked ERROR |

## The incident

Deterministic by design — the demo must be reproducible.

At the injection point, asset revision **v7** of
`SH042_beach_dusk/tex/skin_albedo.exr` is published with a broken path. Every
node that picks up a frame requiring that texture fails in `asset_fetch` with:

```
FATAL: texture not found: /assets/SH042_beach_dusk/tex/skin_albedo.v7.exr
```

The result the agent must uncover:

- ~200 frames fail
- across exactly 14 of the 40 nodes
- GPU utilization on those nodes *drops* (they fail fast rather than working)
- wasted spend accumulates in `render.cost.usd`
- every failing trace shares a broken `asset_fetch` span with `asset.version=v7`

The root cause is only visible by correlating all three signals — metrics show
*that* frames failed, logs show *what* the error was, traces show *which asset
revision* introduced it. That is the investigation the agent performs.

## Running it

From the repo root, with `.env` filled in:

```bash
# Healthy farm, 10 minutes of clean baseline data
make sim

# Healthy baseline, then the asset v7 failure at t+120s
make inject-incident
```

Or directly:

```bash
cd telemetry-sim
uv run farm.py --duration 600 --inject-incident --incident-at 120
```

Useful flags:

| Flag | Default | Purpose |
| --- | --- | --- |
| `--duration` | `600` | seconds to run |
| `--inject-incident` | off | enable the asset v7 failure |
| `--incident-at` | `120` | seconds before the incident fires |
| `--speed` | `1.0` | time multiplier; `5.0` backfills data fast |
| `--seed` | `42` | RNG seed — leave it alone for reproducible demos |

**Tip:** run once with `--speed 10 --duration 1800` to backfill half an hour of
history, so your dashboards do not look empty on camera.

## Verifying data arrived

In Grafana: **Explore** → your Prometheus datasource →

```promql
sum by (status) (rate(render_frames_completed_total[5m]))
```

And for logs, **Explore** → Loki →

```logql
{service_name="render-farm"} |= "texture not found"
```
