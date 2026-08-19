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

A VFX render farm burns money continuously. When an overnight batch fails at
frame 1,400 of 4,000, nobody finds out until the supervisor opens dailies the
next morning. By then hours of GPU spend are wasted and the delivery has
slipped. Diagnosis means hand-correlating node metrics, render logs, and
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
                                                  │ MCP (streamable-http)
                                                  │
                                        mcp-grafana on Cloud Run
                                                  ▲
                                                  │ McpToolset
agent/  google-adk + Gemini  ─────────────────┘
  Triage → Correlate → Report
    │
    ├──OTel──▶ Grafana Cloud AI Observability   (the agent observes itself)
    └──HTTP──▶ web/  Next.js on Vercel          (streams the investigation)
```

### Component status

| Component | Purpose | Status |
| --- | --- | --- |
| `telemetry-sim/` | Synthetic render farm; emits all three signals over OTLP | ✅ built |
| `scripts/` | Compliance guard, secret guard, MCP smoke test | ✅ built |
| `.github/workflows/` | CI enforcing the hackathon constraints | ✅ built |
| `agent/` | ADK agent crew that performs the investigation | ⬜ next |
| `infra/` | Cloud Run deploy for `mcp-grafana` and the agent | ⬜ todo |
| `web/` | Next.js UI streaming agent reasoning + Grafana panels | ⬜ todo |
| Grafana dashboard | The "render farm" dashboard the agent annotates | ⬜ todo |
| Demo video | ≤ 3 min, showing a real investigation | ⬜ todo |

---

## 4. The incident the agent must solve

Deterministic by design — seed `42`, identical every run, because the demo video
will be recorded many times and the narration must match the numbers.

**Setup:** shot `SH042_beach_dusk`, 4,000 frames, 40 render nodes.

**Trigger:** asset revision **v7** of `skin_albedo.exr` is published with a
broken texture path.

**Symptoms the agent discovers:**

| Signal | What it reveals | What it does NOT reveal |
| --- | --- | --- |
| Metrics (Mimir) | 750 frames failed; 14 of 40 nodes affected; GPU utilization *dropped* on those nodes; $922.50 rework cost accumulating | why |
| Logs (Loki) | `FATAL: texture not found: /assets/SH042_beach_dusk/tex/skin_albedo.v7.exr` | which change introduced it |
| Traces (Tempo) | every failing trace shares a broken `asset_fetch` span carrying `asset.version=v7` | the blast radius |

**The point:** no single signal is sufficient. The root cause exists only in the
correlation. That is what makes this a genuine multi-step agent task rather than
a single tool call dressed up as one.

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
   wasted spend, recommended remediation

Sub-agents: **Triage** (steps 1–2) → **Correlate** (step 3) → **Report**
(steps 4–6). Each has a narrow tool allowlist via ADK's `tool_filter`.

---

## 6. Definition of done

The project is complete when every box is checked.

### Functional

- [ ] `make verify-mcp` passes — agent can reach Grafana through MCP
- [ ] `telemetry-sim` reliably populates Mimir, Loki, and Tempo
- [ ] A Grafana dashboard shows the farm: frame outcomes, cost, GPU util, queue depth
- [ ] A Grafana alert rule fires when the failure rate crosses threshold
- [ ] The agent runs the full six steps unattended, from alert to report
- [ ] The agent writes a real annotation into Grafana (a visible side effect —
      proof it acts, not just reads)
- [ ] The agent correctly identifies `asset.version=v7` as root cause, and states
      blast radius (750 frames, 14 nodes) and rework spend ($922.50)
- [ ] The agent is itself instrumented into Grafana Cloud AI Observability —
      token usage, latency, tool calls per investigation
- [ ] `web/` streams the investigation live and embeds the Grafana panels
- [ ] Deployed and publicly reachable (Vercel + Cloud Run)

### Submission

- [ ] Repo public, MIT license visible in the GitHub About section
- [ ] README explains the problem, architecture, and how to run it
- [ ] `scripts/check-ai-compliance.sh` green; no forbidden AI dependency
- [ ] No secret committed anywhere in git history
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

---

## 7. Timeline (3 weeks from 2026-08-18)

| Window | Goal |
| --- | --- |
| **Week 1** (Aug 18–24) | Accounts done. Telemetry flowing. Dashboard + alert built. Agent completes steps 1–3 locally. |
| **Week 2** (Aug 25–31) | Full six steps working. Annotation writing. AI Observability wired. `mcp-grafana` on Cloud Run. **Submit the $100 GCP credits form — hard deadline Aug 31.** |
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
