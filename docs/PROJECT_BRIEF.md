# Second Unit — Project Brief

The single source of truth for what this project is, what it must do, and when
it is finished. If you are an AI coding agent, read this after `AGENTS.md`.

---

## 1. What it is

**Second Unit** is an autonomous agent crew that investigates VFX render-farm
incidents the way a senior site-reliability engineer would — by querying live
metrics, logs, and traces, correlating across all three, and naming a root cause.

The name comes from filmmaking: the *second unit* is the crew that shoots
without the director present. It works autonomously while the main unit sleeps.

> **Tagline:** In filmmaking, the second unit shoots without the director
> present. This one investigates your render farm while you sleep.

### The problem it solves

A VFX render farm burns money continuously. When an overnight batch starts
failing at frame 801 of 4,000, nobody finds out until the supervisor opens
dailies the next morning. By then hours of GPU spend are wasted and the delivery
has slipped. Diagnosis means hand-correlating node metrics, render logs, and
asset-pipeline traces — at 6am, under deadline pressure.

That correlation work is mechanical. It is also exactly what an agent with
observability tools can do unattended.

### Why it is not a chatbot

The agent does not answer questions about dashboards. It runs a **fixed
investigation procedure** end to end, without a human in the loop, and produces
a decision. The hackathon's own framing is "deterministic, multi-step agent" —
that phrase should describe this project literally.

---

## 2. Context: the hackathon

| | |
| --- | --- |
| Event | Agentic Cinema: The Blockbuster Hackathon 2026 |
| Track | **Grafana** (one of five partner tracks; a track is mandatory) |
| Submission deadline | **2026-09-09, 14:00 PDT** (= Sep 10, 00:00 EAT) |
| Judging | Sep 23 – Oct 7, 2026 |
| Prizes (this track) | $7,500 / $4,500 / $3,000 |
| Grafana track judge | Jeremy Breland, Partner Architect |
| Entrant | Solo (permitted; teams capped at 4, no minimum) |

### Judging criteria — all four weighted equally

1. **Technological Implementation** — is the engineering sound and non-trivial?
2. **Design** — is it coherent and usable?
3. **Potential Impact** — does it solve a real, expensive problem?
4. **Quality of the Idea** — is it original and well-conceived?

Most submissions will score well on 1 and poorly on 3 and 4. The VFX framing is
the deliberate edge: it is a real industry with real render-farm economics, and
almost nobody else will pick it.

### 🚨 Disqualifying constraints

- **Google AI tooling only.** `google-adk`, `google-genai`,
  `google-generativeai`, `google-cloud-aiplatform`. Any OpenAI, Anthropic,
  LangChain, Bedrock, or Azure AI dependency is a Stage One fail. CI enforces
  this via `scripts/check-ai-compliance.sh`.
- **Grafana must be reached through MCP at runtime**, not via bare HTTP calls to
  the Grafana API. This is the track requirement; judges check it.
- **Public repo, OSS license** detectable in the GitHub About section, and the
  license must not restrict commercial use. (MIT — already in place.)
- **Demo video ≤ 3 minutes**, public on YouTube or Vimeo, English or subtitled,
  showing the project "functioning as built — not a cinematic trailer".
- **Original work**, created during the contest period. No reusing prior
  projects.

---

## 3. Architecture

```
telemetry-sim/  ──OTLP/HTTP──▶  Grafana Cloud
  synthetic 40-node render farm        (Mimir · Loki · Tempo)
  4,000 frames, deterministic incident            ▲
                                                  │ Grafana HTTP API
                                                  │
                                          mcp-grafana
                                                  ▲
                                                  │ MCP over stdio
                                                  │ (same container)
agent/  google-adk + Gemini ──────────────────────┘
  Triage → Correlate → Report
    │
    ├──OTel──▶ Grafana Cloud AI Observability   (the agent observes itself)
    └──HTTP──▶ web/  Next.js on Vercel          (streams the investigation)
```

The agent and `mcp-grafana` ship as **one private Cloud Run service**. ADK's
`adk api_server` launches `uvx mcp-grafana` as a child process and speaks MCP
over stdio, so no MCP port is ever exposed to the internet. Setting
`GRAFANA_MCP_URL` switches the toolset to streamable-http instead, if a remote
MCP server is ever preferred — the agent code supports both paths.

### Component status

| Component | Purpose | Status |
| --- | --- | --- |
| `telemetry-sim/` | Synthetic render farm; emits all three signals over OTLP | ✅ built |
| `scripts/` | Compliance guard, secret guard, MCP smoke test | ✅ built |
| `.github/workflows/` | CI enforcing the hackathon constraints | ✅ built |
| Grafana dashboard | The "render farm" dashboard the agent annotates | ✅ built — uid `second-unit-farm`, 9 panels |
| Grafana alert rule | Fires on sustained frame-failure rate | ✅ built — uid `dfvmtt22674e8b`, observed firing |
| `agent/` | ADK agent crew that performs the investigation | ✅ built — Triage → Correlate → Report, verified end to end |
| `infra/` | Cloud Run deploy for the agent + mcp-grafana | 🟡 written, not yet deployed |
| `web/` | Next.js UI streaming agent reasoning + Grafana panels | ⬜ todo |
| Demo video | ≤ 3 min, showing a real investigation | ⬜ todo |

---

## 4. The incident the agent must solve

Deterministic by design — seed `42`, identical every run, because the demo video
will be recorded many times and the narration must match the numbers.

**Setup:** shot `SH042_beach_dusk`, 4,000 frames, 40 render nodes.

**Trigger:** asset revision **v7** of `skin_albedo.exr` is published with a
broken texture path, at frame 801.

**Symptoms the agent discovers:**

| Signal | What it reveals | What it does NOT reveal |
| --- | --- | --- |
| Metrics (Mimir) | 748 frames failed; 14 of 40 nodes affected; GPU utilization *dropped* on those nodes; $920.04 rework cost accumulating | why |
| Logs (Loki) | `FATAL: texture not found: /assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | which change introduced it |
| Traces (Tempo) | every failing trace shares a broken `asset_fetch` span carrying `asset.version=v7` | the blast radius |

Canonical figures live in `docs/DEMO-NUMBERS.md`. That file wins over this one;
if they disagree, this one is stale.

**The point:** no single signal is sufficient. The root cause exists only in the
correlation. That is what makes this a genuine multi-step agent task rather than
a single tool call dressed up as one.

**The blast radius is the hard part.** Once v7 publishes, *every* frame carries
`asset.version=v7`, including the 26 healthy nodes. So "v7 is broken" is wrong —
v7 renders fine on most of the farm. The real finding is that the asset failed to
*synchronise* to 14 specific nodes, and the only way to establish that is a
disconfirming trace query against a node outside the failing set. An agent that
skips that step reports a confident, wrong root cause.

**Counter-intuitive detail worth showing on camera:** GPU utilization *falls*
during the incident, because failing nodes fail fast instead of doing work. A
naive "high utilization = problem" alert would miss this entirely. The agent
catches it because it reasons about frame outcomes, not resource pressure.

---

## 5. What the agent does — the six steps

1. **Detect** — read the firing Grafana alert (or accept a manual trigger)
2. **Scope** — PromQL against Mimir: how many frames, which nodes, how much money
3. **Correlate** — LogQL against Loki to cluster the errors; TraceQL against
   Tempo to find the shared failing span
4. **Hypothesise** — Gemini reasons across all three to name the root cause and
   state its confidence
5. **Act** — write a Grafana annotation onto the dashboard marking the incident
   window and the identified cause; propose the frame re-queue
6. **Report** — emit a structured triage summary: root cause, blast radius,
   rework spend, schedule impact, recommended remediation

Sub-agents: **Triage** (steps 1–2) → **Correlate** (step 3) → **Report**
(steps 4–6). Each has a narrow tool allowlist via ADK's `tool_filter`.

---

## 6. Definition of done

The project is complete when every box is checked.

### Functional

- [x] `make verify-mcp` passes — agent can reach Grafana through MCP
- [x] `telemetry-sim` reliably populates Mimir, Loki, and Tempo
- [x] A Grafana dashboard shows the farm: frame outcomes, cost, GPU util, queue depth
- [x] A Grafana alert rule fires when the failure rate crosses threshold
- [x] The agent runs the full six steps unattended, from alert to report
- [x] The agent writes a real annotation into Grafana (a visible side effect —
      proof it acts, not just reads)
- [x] The agent correctly identifies `asset.version=v7` as root cause, scopes it
      to the 14 nodes rather than calling the asset globally broken, and states
      blast radius (748 frames, 14 of 40 nodes) and rework spend ($920.04)
- [x] The agent is itself instrumented into Grafana Cloud AI Observability —
      token usage, latency, tool calls per investigation
- [ ] The agent proposes a concrete frame re-queue (step 5, write side)
- [ ] `web/` streams the investigation live and embeds the Grafana panels
- [ ] Deployed and publicly reachable (Vercel + Cloud Run)

### Submission

- [x] Repo public, MIT license visible in the GitHub About section
- [x] `scripts/check-ai-compliance.sh` green; no forbidden AI dependency
- [x] No secret committed anywhere in git history
- [ ] README explains the problem, architecture, and how to run it
- [ ] Demo video ≤ 3:00, public, showing a real end-to-end investigation
- [ ] Devpost writeup: problem, what it does, how it uses Grafana MCP, what's next
- [ ] Grafana track explicitly selected on the submission form
- [ ] Submitted **before 2026-09-09 14:00 PDT** — not on the day

### The differentiator, stated plainly

Most Grafana-track submissions will be a chat interface over `mcp-grafana`.
This one must demonstrate three things they will not:

1. **A closed loop** — the agent *writes* to Grafana, it does not only read.
2. **Genuine cross-signal correlation** — the answer requires metrics AND logs
   AND traces. Not one query.
3. **Self-observation** — the agent's own behaviour is monitored in Grafana. An
   observability agent that is not itself observable is an unfinished thought.

A fourth, earned the hard way: **the agent is built not to lie.** Its
instructions forbid reporting an empty result as evidence, quoting a span
attribute it did not read, explaining an interval it did not measure, or naming a
mechanism it did not query. Each of those rules exists because an earlier run
broke it and produced a confident, wrong answer. See the corrections log in
`docs/DEMO-NUMBERS.md`.

---

## 7. Timeline (3 weeks from 2026-08-18)

| Window | Goal |
| --- | --- |
| **Week 1** (Aug 18–24) | Accounts done. Telemetry flowing. Dashboard + alert built. Agent completes steps 1–3 locally. |
| **Week 2** (Aug 25–31) | Full six steps working. Annotation writing. AI Observability wired. Agent on Cloud Run. **Submit the $100 GCP credits form — hard deadline Aug 31.** |
| **Week 3** (Sep 1–7) | `web/` built and deployed. Record and edit the video. Devpost writeup. Buffer for breakage. |
| **Sep 8** | Submit. A full day early. |

---

## 8. Reference docs

Use these rather than guessing API surfaces. Hallucinated ADK method names are
the biggest predictable time sink on this project.

**ADK**
- Docs: https://google.github.io/adk-docs/
- Python API reference: https://adk.dev/api-reference/python/
- MCP guide: https://google.github.io/adk-docs/mcp/
- Samples: https://github.com/google/adk-samples

**Grafana**
- `mcp-grafana` (tool list, RBAC scopes, CLI flags): https://github.com/grafana/mcp-grafana
- OSS MCP docs: https://grafana.com/docs/grafana/latest/developer-resources/mcp/
- OTLP endpoint: https://grafana.com/docs/grafana-cloud/observe-and-act/send-data/otlp/send-data-otlp/
- AI Observability: https://grafana.com/docs/grafana-cloud/observe-and-act/monitor-applications/ai-observability/
- LLM-friendly doc indexes: https://grafana.com/llms.txt · https://grafana.com/llms-full.txt

**Hackathon**
- Rules: https://agentic-cinema.devpost.com/rules
- Grafana track resources: https://agentic-cinema.devpost.com/details/grafana-resources
