# agent

The Second Unit investigation crew, built on Google ADK.

## Design

Three stages in a fixed order, wired with ADK's `SequentialAgent`:

| Stage | Question | Signals | Tools |
| --- | --- | --- | --- |
| **Triage** | What happened, how bad, how expensive? | metrics | `query_prometheus`, alert rules |
| **Correlate** | Why did it happen? | logs + traces | `query_loki_logs`, Tempo queries |
| **Report** | Say so, and record it. | — | `create_annotation`, dashboard reads |

### Why three agents instead of one

A single agent holding every tool tends to shortcut: it runs one query, forms a
theory, and starts arguing for it. Splitting the stages forces evidence
collection to finish before reasoning begins, and makes each stage's output
inspectable on its own.

It also matches what the hackathon asks for — a *deterministic, multi-step
agent*. The step order is structural, not a suggestion in a prompt.

### Why queries live in `queries.py`

Models invent metric names. Asked to write PromQL from memory, they produce
plausible-looking names that return nothing, and then reason confidently about
empty results. Every query is therefore a named function in `queries.py`, and
the instructions tell each stage to prefer them.

`queries.py` is also the single place to change if a metric name changes. It is
the contract between the agent and `telemetry-sim`.

## Running locally

Needs `.env` at the repo root with `GRAFANA_URL`,
`GRAFANA_SERVICE_ACCOUNT_TOKEN`, the OTLP variables, and Google Cloud settings.

```bash
cd agent
uv sync

# Web UI — shows each stage's reasoning and tool calls as they happen
uv run adk web

# Terminal
uv run adk run second_unit
```

With no `GRAFANA_MCP_URL` set, the toolset spawns `uvx mcp-grafana` over stdio.
Set `GRAFANA_MCP_URL` to use a deployed server instead.

`adk web` is the right tool for demo recording: the stage-by-stage tool calls are
visible, which is what makes the investigation legible to a judge.

## Verify before trusting

Two things in this package are written against documented-but-unpinned API
surfaces and must be confirmed against the installed versions:

1. **ADK class names.** `mcp_tools.py` resolves the toolset and connection-params
   classes through a shim, because ADK has renamed them across releases. Once the
   version is pinned, collapse the shim into a direct import.
2. **MCP tool names.** The `*_TOOLS` allowlists must match what your
   `mcp-grafana` build actually exposes. A name that does not exist is silently
   filtered out, so the agent simply lacks the tool — it does not error.

Both are TASK-06 in `docs/TASKS-SPRINT2.md`. Do that task before debugging
anything else in here.

## Not built yet

- Frame re-queue proposal as a callable tool
- Cloud Run deployment (`infra/`)
- The `web/` UI that streams the investigation
