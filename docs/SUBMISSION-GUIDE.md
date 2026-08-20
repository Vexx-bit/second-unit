# Devpost submission guide

Agentic Cinema hackathon. Deadline **2026-09-09, 2:00 PM PDT** — which is
**2026-09-10, 12:00 AM EAT**. Target the 8th. Judging runs Sep 23 – Oct 7.

Declared track: **Grafana**.

---

## Mandatory

Each of these is pass/fail. Missing one disqualifies before judging starts.

| # | Requirement | Status |
| --- | --- | --- |
| 1 | Public repository | ✅ github.com/Vexx-bit/second-unit |
| 2 | Open source license, visible in the repo's **About** section | ✅ MIT |
| 3 | Demo video, **3 minutes or less**, public on YouTube or Vimeo | ⬜ see `VIDEO-BEAT-SHEET.md` |
| 4 | Video shows the project **functioning as built** — not a cinematic trailer | ⬜ |
| 5 | Written project description on the Devpost form | ⬜ |
| 6 | Exactly one partner track declared | ⬜ select Grafana |
| 7 | Grafana track requirement: **connect the Grafana Cloud MCP server** | ✅ `mcp-grafana` over stdio, proven in the agent's own trace |
| 8 | Google AI tooling only — `google-adk`, `google-genai`, `google-generativeai`, `google-cloud-aiplatform`. Azure, OpenAI, Anthropic and AWS AI services are banned | ✅ CI-enforced by `scripts/check-ai-compliance.sh` |

## Explicitly NOT required

Do not spend the remaining days on any of these under the impression that they
are gates. They are not.

- **A hosted web interface.** No rule requires one. `adk web` on localhost
  satisfies "functioning as built".
- **A public deployment URL.** Only the *Replit* track requires deployment. The
  Grafana track does not.
- **A pitch deck.** Useful for writing the description and the script. Not
  submitted.
- **A logo, landing page, or branding.**

The Cloud Run deployment in `infra/` and any future `web/` front end are optional
polish. They read as Technological Implementation and Design credit, nothing
more. A flawless three-minute video beats a half-built UI every time.

---

## Judging criteria

Four criteria, equal weight. Worth knowing what each one is actually rewarding
before you write a word of the description.

| Criterion | What to put in front of it |
| --- | --- |
| **Technological Implementation** | The `SequentialAgent` with a fixed stage order. Timestamp arithmetic moved out of the model into `timewindow.py`. The disconfirming query. The freshness gate and the commit-provenance print. Agent self-tracing into the same stack it queries. |
| **Design** | Not visual design — the design of the *investigation*. Why three stages instead of one agent with every tool. Why the agent writes its finding back to the dashboard instead of a chat window. Why it labels its own counts approximate. |
| **Potential Impact** | Render farms are the narrow case. The general shape is: expensive batch infrastructure, telemetry nobody watches overnight, and a root cause that only exists at the intersection of three signals. CI fleets, ETL pipelines, GPU training clusters. |
| **Quality of the Idea** | The hackathon's own phrase is "deterministic, multi-step agent". Seven identical runs, and the same frame failing first on the same node twice. That is the idea: an incident responder that can be trusted because it is repeatable and honest about its limits. |

---

## Form fields, and what to write

Wording on the Devpost form varies slightly, but it will ask for these.

### Project name

```
Second Unit
```

### Elevator pitch (one line, ~200 characters)

```
An autonomous incident responder for VFX render farms. Three ADK agents in a fixed order cross Prometheus, Loki and Tempo through the Grafana MCP server, find the root cause, and write it back to the dashboard.
```

### The initial-idea field, if still shown

```
A deterministic, multi-step agent that investigates render farm failures the way a supervisor would: scope the blast radius from metrics, find the cause by crossing logs and traces, then price the damage and record the finding in Grafana. The interesting constraint is trust — an agent that guesses a root cause at 3am is worse than no agent at all.
```

### About the project — structure

Write it in this order. Lead with the answer, like the agent does.

1. **The problem, in cost terms.** Fourteen of forty nodes failing, looking idle
   on the dashboard while they burn through the queue. $920 of rework, 1.56 hours
   of slip, invisible until dailies.
2. **What it does.** Triage → Correlate → Report, fixed order, ADK
   `SequentialAgent`. Name the actual tools it calls.
3. **The hard part: making it trustworthy.** This is the section that wins. Be
   specific and be honest:
   - It runs a **disconfirming query** — actively tries to falsify its own root
     cause against a healthy node. Without it, the agent concluded the asset was
     globally broken and recommended a rollback. That was the wrong fix.
   - An **empty result is not evidence.** A query that cannot return anything
     looks identical to a query that found nothing.
   - **No epoch arithmetic.** It got a conversion twelve days wrong, so
     conversion moved into code with a plausibility guard.
   - **Provenance or silence.** Any span attribute it quotes comes with the
     trace ID it was read from.
   - **It labels its own counts approximate**, because `increase()` extrapolates
     at window edges.
4. **How you know it works.** Seven identical runs. Frame 802 on render-03 first
   in two independent runs. Every headline number re-queried from live Grafana
   rather than taken from the agent's own report. Publish → first failure of
   174 ms, measured twice.
5. **Built with.** Google ADK 2.7.1, Gemini 2.5 Pro on Vertex AI, Grafana Cloud
   (Prometheus, Loki, Tempo, Alerting), `mcp-grafana` over stdio, OpenTelemetry,
   Python 3.12, `uv`.
6. **What is next.** Cloud Run deployment, a re-queue executor that submits the
   plan rather than proposing it, and generalising the stage prompts beyond the
   render-farm schema.

### Links

- Repository: `https://github.com/Vexx-bit/second-unit`
- Video: paste after upload. **Set it to Public, not Unlisted.**

### Screenshots to attach

1. The dashboard over the incident window, annotation visible.
2. Panel 6, failures by node — the fourteen-band split.
3. The Tempo trace of the agent itself: 95 spans, three stages in order.

Caption each one. An uncaptioned screenshot of a dashboard is just a dashboard.

---

## Final pass before submitting

- Repo **About** section shows the MIT license and a one-line description.
- `README.md` opens with what it is and how to run it, not with a wall of
  context.
- No secrets. `scripts/check-ai-compliance.sh` passes and the secret regexes find
  nothing. `.env` is gitignored and stays that way.
- Every number in the description appears in `DEMO-NUMBERS.md`, and none appears
  in its corrections log.
- Video is under 3:00 and public. Check the runtime, not your intention.
- Track selection says Grafana.
- Submit two days early. The form has been known to be slow on deadline day, and
  the deadline is 12:00 AM in Nairobi.
