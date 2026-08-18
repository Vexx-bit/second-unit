# Second Unit

> In filmmaking, the *second unit* shoots without the director present. This one investigates your render farm while you sleep.

**Agentic Cinema: The Blockbuster Hackathon 2026 — Grafana track.**

Second Unit is an autonomous agent crew, built on Google ADK + Gemini, that
investigates VFX render-farm incidents by querying live metrics, logs, and traces
through the **Grafana MCP server** — then names a root cause, annotates the
dashboard, and files a triage report for the VFX supervisor's morning.

## The problem

A render farm burns money continuously. When an overnight batch fails at frame
1,400 of 4,000, nobody finds out until the supervisor opens dailies — hours of
GPU spend wasted and a slipped delivery. Diagnosis means correlating node
metrics, render logs, and asset-pipeline traces by hand, at 6am.

## What it does

1. **Detect** — picks up the firing Grafana alert
2. **Scope** — PromQL against Mimir: affected nodes, failed frames, cost burned
3. **Correlate** — LogQL against Loki to cluster errors; Tempo traces to find the shared span
4. **Hypothesise** — Gemini reasons across all three signals to name a root cause
5. **Act** — annotates the Grafana dashboard and proposes the re-queue
6. **Report** — structured triage summary in the web UI

## Architecture

```
telemetry-sim/  ──OTLP──▶  Grafana Cloud (Mimir · Loki · Tempo)
  synthetic render farm                  ▲
                                         │ MCP (streamable-http)
agent/  ──MCPToolset──▶  mcp-grafana on Cloud Run
  google-adk + Gemini
    ├──OTel──▶ Grafana Cloud AI Observability (observes the agent itself)
    └──HTTP──▶ web/  (Next.js, Vercel)
```

## Layout

| Path | Purpose |
| --- | --- |
| `agent/` | ADK agent crew (Triage → Correlate → Report) |
| `telemetry-sim/` | Synthetic render farm emitting metrics, logs, traces via OTLP |
| `web/` | Next.js UI streaming agent reasoning + embedded Grafana panels |
| `infra/` | Cloud Run deploys for `mcp-grafana` and the agent |
| `scripts/` | Compliance guard and demo helpers |

## Compliance

This project uses **only Google Cloud AI tooling** (`google-adk`, `google-genai`)
plus the Grafana stack, per the hackathon rules. CI fails the build if a
non-Google AI SDK is introduced — see `scripts/check-ai-compliance.sh`.

## Status

In active development for the Sep 9, 2026 deadline. Setup instructions land with
the first working agent.

## License

MIT — see [LICENSE](./LICENSE).
