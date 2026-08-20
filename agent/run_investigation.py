import asyncio
import json
import sys
import os
import urllib.request
from google.adk.runners import InMemoryRunner
from google.genai import types
from second_unit.agent import root_agent


async def main():
    url = os.getenv("GRAFANA_URL", "").rstrip("/")
    token = os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")
    if url and token:
        import time as _time
        import urllib.parse

        def _prom_instant(expr: str) -> list:
            """Run an instant PromQL query; return the result list."""
            q = urllib.parse.urlencode({"query": expr})
            req = urllib.request.Request(
                f"{url}/api/datasources/uid/grafanacloud-prom/resources/api/v1/query?{q}"
            )
            req.add_header("Authorization", f"Bearer {token}")
            with urllib.request.urlopen(req, timeout=15) as r:
                return json.loads(r.read().decode()).get("data", {}).get("result", [])

        # ── Gate 1: telemetry is live and fresh ─────────────────────────
        # Probe a COUNTER, not the queue-depth gauge.
        #
        # render_queue_depth stops being exported the moment the simulator
        # exits, and once its last sample ages past Prometheus' five minute
        # staleness window an instant query returns nothing at all. A farm that
        # ran start to finish then reports as having no telemetry, which is the
        # opposite of the truth. render_frames_completed_total is a counter and
        # persists, so it can be aged instead of merely tested for existence.
        #
        # Retry rather than fail on the first attempt. Grafana Cloud's OTLP
        # ingest path typically runs a minute or two behind the exporter, so a
        # single hard check immediately after launch measures ingest lag rather
        # than whether telemetry exists.
        FRESHNESS_LIMIT_S = 300
        ATTEMPTS = 6
        RETRY_WAIT_S = 20

        for attempt in range(1, ATTEMPTS + 1):
            try:
                result = _prom_instant(
                    "time() - max(timestamp(render_frames_completed_total))"
                )
            except Exception as exc:
                print(f"Could not reach Grafana to check telemetry: {exc}", flush=True)
                sys.exit(1)

            age = float(result[0]["value"][1]) if result else None

            if age is not None and age <= FRESHNESS_LIMIT_S:
                print(
                    f"Telemetry is live — newest sample is {age:.0f}s old.",
                    flush=True,
                )
                break

            detail = (
                "no render_frames_completed_total samples found at all"
                if age is None
                else f"newest sample is {age:.0f}s old, limit is {FRESHNESS_LIMIT_S}s"
            )

            if attempt == ATTEMPTS:
                print(f"TELEMETRY NOT LIVE — {detail}.", flush=True)
                print(
                    "Start telemetry-sim, give Grafana Cloud about a minute to "
                    "ingest, then re-run.",
                    flush=True,
                )
                sys.exit(1)

            print(
                f"Waiting for telemetry ({detail}) — attempt {attempt} of {ATTEMPTS}.",
                flush=True,
            )
            _time.sleep(RETRY_WAIT_S)
    else:
        print(
            "GRAFANA_URL or GRAFANA_SERVICE_ACCOUNT_TOKEN is not set, so the "
            "telemetry gate was skipped. The investigation may run against an "
            "empty farm.",
            flush=True,
        )

    runner = InMemoryRunner(agent=root_agent, app_name="second_unit")
    session = await runner.session_service.create_session(
        app_name=runner.app_name,
        user_id="supervisor",
        session_id="incident-01",
    )
    content = types.Content(
        role="user",
        parts=[types.Part.from_text(text="Frames are failing on SH042_beach_dusk. Investigate.")],
    )

    print("=== STARTING SECOND UNIT INVESTIGATION ===", flush=True)
    last_author = None
    async for event in runner.run_async(
        user_id="supervisor",
        session_id=session.id,
        new_message=content,
    ):
        author = getattr(event, "author", None) or getattr(event, "node_name", None) or "agent"

        if last_author and author != last_author:
            if hasattr(runner, "_last_state") and runner._last_state:
                for k, v in runner._last_state.items():
                    print(f"\n=======================================================", flush=True)
                    print(f"[{last_author}] STAGE OUTPUT: {k}", flush=True)
                    print(f"=======================================================", flush=True)
                    print(v, flush=True)
                runner._last_state = {}
        last_author = author
        
        # Check function call (tool call)
        calls = event.get_function_calls() if hasattr(event, "get_function_calls") else []
        for call in calls:
            print(f"\n[{author}] TOOL CALL: {call.name}", flush=True)
            print(f"  args: {json.dumps(call.args, default=str)}", flush=True)

        # Check function responses (tool output)
        responses = event.get_function_responses() if hasattr(event, "get_function_responses") else []
        for resp in responses:
            print(f"\n[{author}] TOOL RESPONSE: {resp.name}", flush=True)
            resp_str = json.dumps(resp.response, default=str)
            if len(resp_str) > 1500:
                print(f"  output (first 1500 chars): {resp_str[:1500]}...", flush=True)
            else:
                print(f"  output: {resp_str}", flush=True)

        # Check text in message
        if hasattr(event, "message") and event.message and event.message.parts:
            for part in event.message.parts:
                if hasattr(part, "text") and part.text:
                    print(f"\n[{author}] TEXT:\n{part.text}", flush=True)

        # Check state changes (triage_findings, correlation_findings, triage_report)
        if hasattr(event, "actions") and event.actions:
            if hasattr(event.actions, "state_delta") and event.actions.state_delta:
                last_state = getattr(runner, "_last_state", {})
                last_state.update(event.actions.state_delta)
                runner._last_state = last_state

    if hasattr(runner, "_last_state") and runner._last_state:
        for k, v in runner._last_state.items():
            print(f"\n=======================================================", flush=True)
            print(f"[{last_author}] STAGE OUTPUT: {k}", flush=True)
            print(f"=======================================================", flush=True)
            print(v, flush=True)
        runner._last_state = {}

if __name__ == "__main__":
    asyncio.run(main())
