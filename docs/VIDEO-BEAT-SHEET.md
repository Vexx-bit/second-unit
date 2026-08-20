# Demo video beat sheet

180 seconds, hard cap. Devpost requires the project "functioning as built — not a
cinematic trailer", so every second of screen time is real software doing real
work against live Grafana Cloud.

**Before you record**

1. `uv run python check_window.py` must exit 0. If it does not, wait the number of
   minutes it tells you. A contaminated window has invalidated four runs already.
2. `git -C C:\Users\vexx\second-unit status` must be clean and on `main`, at or
   after `95bab8b`. The startup banner prints the commit, and it will be on
   screen — make sure it is a commit you are proud of.
3. Have four things open and sized: PowerShell (large font, at least 16pt), the
   Grafana dashboard, the Tempo trace view, and nothing else. No Discord, no
   Spotify, no notifications.
4. Start the simulator, wait 8 minutes, then start the investigation. Record the
   investigation, not the wait.

---

## 0:00 – 0:12 · The hook

**On screen:** the Grafana dashboard, GPU utilization panel, over a time range.
Two clear bands.

**Say:** "Fourteen of these forty render nodes look idle. Four to eighteen
percent GPU. On a dashboard at six in the morning that reads as spare capacity.
It is actually a render farm failing frames as fast as it can dispatch them, and
nobody will notice until dailies."

**Why it works:** you open on a genuine misreading rather than a title card. The
judge is already inside the problem at twelve seconds.

## 0:12 – 0:30 · The cost

**On screen:** cut to the stat panels — frames failed, nodes affected, GPU spend.

**Say:** "Seven hundred and forty-eight frames dead. Nine hundred and twenty
dollars of GPU time to render them again. An hour and a half of slip on a shot
with a delivery date. The signal was in Prometheus, Loki and Tempo the whole
time — but the answer is only in the intersection, and nothing crosses them at
three in the morning."

## 0:30 – 0:42 · What it is

**On screen:** the terminal, `uv run python run_investigation.py`, showing the
startup banner with the commit SHA and `Telemetry is live — newest sample is Ns
old.`

**Say:** "Second Unit is three specialist agents in a fixed order, on Google's
ADK, talking to Grafana Cloud through the Grafana MCP server. It prints the
commit it is running and refuses to start against stale telemetry."

**Why it works:** the freshness gate and the commit print are unglamorous and
they are exactly what separates a demo from a system.

## 0:42 – 1:20 · Triage

**On screen:** the triage stage running. Let the tool calls scroll.

**Say:** "Stage one only gets metrics. It scopes the blast radius — how many
frames, which nodes, how much money, when it started. It cannot see logs or
traces yet, deliberately, because an agent with every tool at once jumps to a
conclusion after one query."

**Point at:** the approximate-count line. "Notice it says the render is complete
but its counts are approximate. Those come from `increase()` over a range, which
extrapolates at the window edges and runs a few percent low. The simulator's own
summary says seven forty-eight. The agent says seven-oh-six and tells you it is
an estimate rather than pretending otherwise."

**Why it works:** this is the single most credible beat in the video. Volunteering
a known imprecision is something a polished demo never does.

## 1:20 – 2:05 · Correlate

**On screen:** the correlate stage. The bounded window statement, the Loki
queries, the trace inspection, the disconfirming query.

**Say:** "Stage two bounds its window in code, not in the model's head — it got
an epoch conversion twelve days wrong once, so it no longer does arithmetic.
Then it crosses the signals. Logs give the error and the frame numbers. A trace
gives the failing span: `asset_fetch`, `AssetResolutionError`, asset version v7."

**Point at:** the disconfirming query. "And then it tries to prove itself wrong.
It queries a healthy node for the same v7 asset. That comes back successful —
so the asset is not globally broken, and the root cause is scoped to fourteen
nodes that failed to sync it. An agent that only looks for confirmation would
have told you to roll back the asset. That would have been the wrong fix."

**Why it works:** the disconfirming query is your strongest technical
differentiator. Spend the words on it.

## 2:05 – 2:25 · The reveal

**On screen:** the correlate timeline output.

**Say:** "The trigger. Asset v7 published at 11:41:03.854. First failed frame at
11:41:04.028. A hundred and seventy-four milliseconds. Cause and effect,
adjacent in the log stream."

**Beat. Then:** "The metric onset says 11:41:30 — twenty-seven seconds later.
That gap is not the system being slow, it is a thirty-second range step. The
agent is instructed to compare log against log for exactly this reason, and to
quote the metric onset only as the lagging signal. I got this wrong myself, and
the correction is in the repo."

**Why it works:** 174 ms is a precise, memorable, verifiable number. The scrape
lag aside proves you understand your own instrumentation.

## 2:25 – 2:45 · Report, and the write-back

**On screen:** the report output, then cut to the dashboard with the annotation
visible on the time-series panels.

**Say:** "Stage three prices it, builds a re-queue plan across the twenty-six
healthy nodes with the fourteen bad ones held out, states plainly that its frame
list is a sample of the failures rather than all of them — and writes the finding
back into Grafana as an annotation. The conclusion lives where the team already
looks, not in a chat log nobody opens."

## 2:45 – 3:00 · Close

**On screen:** the Tempo trace of the agent itself — 95 spans, three stages.

**Say:** "The agent is observable in the same stack it investigates. Ninety-five
spans, every tool call, every token. Seven runs, identical results, down to the
same frame failing first on the same node. Five minutes of agent time for an
hour of human triage — and it tells you what it does not know."

---

## Rules for the edit

- **No speed-ramps on the agent working.** Cutting between tool calls is fine.
  Fake-accelerating the reasoning is not, and it reads as a trailer.
- **Do not narrate a number that is not on screen.** If you say 174 ms, the
  timestamps are visible.
- **Do not say "wasted".** It is rework spend. Total batch spend is not waste.
- **Do not claim wall-clock hours when you mean machine-hours.** They are
  labelled distinctly in the report for a reason.
- If a take goes wrong, re-run the gate before recording again. Do not film a
  contaminated window to save time.

## Numbers you may say

748 frames · 14 of 40 nodes · $3,949.68 total spend · $920.04 rework · 1.56 hours
slip · 0.62–0.65 failure ratio · 174 ms publish to first failure · 95 spans ·
4m 48s end to end.

Everything else is in the corrections log in `DEMO-NUMBERS.md`. Read it before
you write the script.
