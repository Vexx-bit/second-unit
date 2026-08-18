# AGENTS.md — instructions for AI coding agents in this repo

Read this fully before writing code. It encodes hard constraints that, if
violated, disqualify the project from the hackathon it is built for.

## Project

**Second Unit** — an autonomous agent crew that investigates VFX render-farm
incidents using live observability data from Grafana Cloud, built for the
Agentic Cinema Hackathon 2026 (Grafana track). Deadline: **2026-09-09 14:00 PDT**.

## 🚨 Hard constraints — never violate

1. **Google AI tooling ONLY.** Permitted AI/agent packages: `google-adk`,
   `google-genai`, `google-generativeai`, `google-cloud-aiplatform`.
2. **FORBIDDEN**, even transitively as a direct dependency: `openai`,
   `anthropic`, `langchain*`, `llama-index`, `@ai-sdk/*`, `ai` (Vercel AI SDK),
   `crewai`, `autogen`, `litellm`, `transformers`, Bedrock, Azure AI.
   Introducing any of these fails CI and disqualifies the submission.
   If a task seems to need one, STOP and ask the human.
3. **Grafana MCP must be called at runtime.** The agent reaches Grafana only via
   the MCP server, never through bare Grafana HTTP API calls. Judges check this.
4. **No secrets in the repo.** Tokens live in Google Secret Manager and `.env`
   (gitignored). Never commit a `glsa_` or `glc_` string, service-account JSON,
   or PAT. Never print a secret in logs.
5. **Original work only.** Do not vendor or copy existing project code.

## Stack

- **Agent:** Python 3.12, `google-adk`, Gemini. Sub-agents: Triage → Correlate → Report.
- **MCP:** self-hosted `grafana/mcp-grafana`, `-t streamable-http`, on Cloud Run,
  authed with a Grafana service-account token (NOT interactive OAuth — the agent
  must run unattended). Connect via ADK `McpToolset` +
  `StreamableHTTPConnectionParams`.
- **Telemetry:** `telemetry-sim/` emits metrics, logs, and traces over a single
  **OTLP/HTTP** endpoint to Grafana Cloud. Do not add Prometheus remote-write,
  Promtail, or separate Tempo exporters — one OTLP path only.
- **Web:** Next.js (App Router) + TypeScript on Vercel. Streams agent steps.
- **Self-observation:** instrument the agent with OpenTelemetry into Grafana
  Cloud AI Observability. This is a scored differentiator, not optional polish.

## Conventions

- Python: `uv` for deps, `ruff` for lint/format, type hints everywhere.
- Every Grafana query (PromQL/LogQL/TraceQL) lives in a named, documented
  function — never an inline string literal in agent prompt text.
- Conventional Commits. Work on `feat/*` branches, open a PR, never push to `main`.
- The demo must be **deterministic**: `make inject-incident` always produces the
  same failure (asset v7 breaks a texture path → ~200 frames fail across 14
  nodes). Never make the demo scenario random.

## Reference docs (use these, do not guess API surfaces)

- ADK docs: https://google.github.io/adk-docs/
- ADK Python API reference: https://adk.dev/api-reference/python/
- ADK MCP guide: https://google.github.io/adk-docs/mcp/
- ADK samples: https://github.com/google/adk-samples
- mcp-grafana (tools + CLI flags): https://github.com/grafana/mcp-grafana
- Grafana OSS MCP docs: https://grafana.com/docs/grafana/latest/developer-resources/mcp/
- Grafana Cloud OTLP endpoint: https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/otlp/send-data-otlp/
- Grafana AI Observability: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/ai-observability/
- Hackathon rules: https://agentic-cinema.devpost.com/rules

If an API surface is unclear, fetch the doc above rather than inventing a method
name. Hallucinated ADK methods are the most common time sink in this project.

## Definition of done for any change

- `scripts/check-ai-compliance.sh` passes.
- No secret material added.
- Grafana access still goes through MCP.
- README stays accurate.
