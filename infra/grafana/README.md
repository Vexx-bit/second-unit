# Grafana configuration

## Stack details

| | |
| --- | --- |
| Stack URL | `https://violetheron2036.grafana.net` |
| Region | `prod-eu-west-2` |
| OTLP endpoint | `https://otlp-gateway-prod-eu-west-2.grafana.net/otlp` |

### Datasource UIDs

Confirmed against the live stack on 2026-08-19 via `list_datasources`:

| Signal | Datasource UID | Type |
| --- | --- | --- |
| Metrics | `grafanacloud-prom` | Prometheus (default) |
| Logs | `grafanacloud-logs` | Loki |
| Traces | `grafanacloud-traces` | Tempo |

The agent will need all three. Prefer resolving them at runtime through the MCP
datasource-listing tool rather than hardcoding these strings — they are recorded
here for reference and debugging, not as configuration.

---

## Why not the community APM dashboard?

Grafana's onboarding suggests **"Lightweight APM for OpenTelemetry"** (dashboard
ID `22784`). Do not use it for this project.

That dashboard expects **HTTP, gRPC, or database-client metrics** produced by
OpenTelemetry auto-instrumentation — `http.server.request.duration` and friends.
It was built and tested against auto-instrumented Java web services.

`telemetry-sim` is not a web service. It emits **domain metrics** about frames,
nodes, and GPU cost. There is no HTTP surface to instrument, so every panel on
that dashboard would be empty and its service dropdown would stay blank. Its own
FAQ lists "the drop down list for services is empty" as a known issue, marked
TODO.

It also asks you to open a Grafana Cloud support ticket to enable
`otel_keep_identifying_resource_attributes`. Do not spend hackathon time on a
support ticket for a dashboard you are not going to use.

**Use `dashboards/render-farm.json` instead.** It queries the metrics this
project actually emits, and it is the dashboard the agent annotates — which
makes it part of the demo rather than decoration.

## Importing the render farm dashboard

1. In Grafana: **Dashboards → New → Import**
2. Paste the contents of `dashboards/render-farm.json` into the JSON box, or
   upload the file
3. Click **Load**, then pick your datasources:
   - **Metrics** → `grafanacloud-prom`
   - **Logs** → `grafanacloud-logs`
4. **Import**

Set the time range to **Last 1 hour** and confirm panels populate. If they are
empty, run the simulator first — metrics export on a 15-second interval, so
allow a minute.

### Panels

| Panel | Question it answers |
| --- | --- |
| Frames failed | How bad is it? |
| Nodes affected | What is the blast radius? |
| GPU spend | How much money is involved? |
| Queue depth | How far behind is the shot? |
| Frame outcomes | When did it start? |
| Failures by node | Which nodes, exactly? |
| GPU utilization by node | Are the nodes working or failing fast? |
| Frame duration p50/p95 | Are surviving renders also degraded? |
| Render farm errors | What is the actual error text? |

Those nine questions are the same ones the agent answers in its investigation.
The dashboard is the human version; the agent is the automated version. Showing
both side by side in the demo video is the clearest way to make the point.

## Metric names

Grafana Cloud translates OTLP names to Prometheus names. These are the exact
names to query — see the docstring in `telemetry-sim/farm.py` for why the units
were chosen to make them predictable:

| Prometheus name | Type | Labels |
| --- | --- | --- |
| `render_frames_completed_total` | counter | `shot`, `node`, `status` |
| `render_cost_usd_total` | counter | `shot`, `node` |
| `render_frame_duration_seconds_bucket` | histogram | `shot`, `status`, `le` |
| `render_node_gpu_utilization_percent` | gauge | `shot`, `node` |
| `render_queue_depth` | gauge | `shot` |

Verify in **Explore** before trusting them:

```promql
group by (__name__) ({__name__=~"render_.*"})
```

## The alert rule

The agent's investigation is triggered by an alert. Create it in the UI:

1. **Alerting → Alert rules → New alert rule**
2. Name: `Render farm frame failures`
3. Query **A**, Prometheus datasource, code mode:
   ```promql
   sum(rate(render_frames_completed_total{status="failed"}[5m]))
   ```
4. Expression **B**: Threshold, input `A`, `IS ABOVE` `0.1`
5. Set B as the alert condition
6. Folder: create `Second Unit`. Evaluation group: `render-farm`, every `1m`,
   pending period `1m`
7. Add labels — the agent uses these to identify the alert:
   `shot=SH042_beach_dusk`, `team=vfx`, `service=render-farm`
8. Summary annotation:
   `Frames are failing on the render farm for {{ $labels.shot }}`
9. **Save rule and exit**

A short pending period keeps the demo tight: `make inject-incident` should move
the rule to Firing within about two minutes.

## Annotations the agent writes

Step 5 of the investigation writes a Grafana annotation tagged `second-unit`.
The dashboard has a built-in annotation query for that tag, so agent findings
appear as red markers on every time-series panel.

This is the most important visual proof in the demo: it shows the agent **acting
on** the observability stack, not merely reading from it. Most hackathon
submissions in this track will only read.
