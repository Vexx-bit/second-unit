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
        query_url = f"{url}/api/datasources/uid/grafanacloud-prom/resources/api/v1/query?query=render_queue_depth"
        req = urllib.request.Request(query_url)
        req.add_header("Authorization", f"Bearer {token}")
        try:
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                if not data.get("data", {}).get("result"):
                    print("TELEMETRY STALE — start telemetry-sim first, then re-run.", flush=True)
                    sys.exit(1)
        except Exception as e:
            print(f"Failed to check telemetry freshness: {e}", flush=True)

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
    async for event in runner.run_async(
        user_id="supervisor",
        session_id=session.id,
        new_message=content,
    ):
        author = getattr(event, "author", None) or getattr(event, "node_name", None) or "agent"
        
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
                for k, v in event.actions.state_delta.items():
                    print(f"\n=======================================================", flush=True)
                    print(f"[{author}] STAGE OUTPUT: {k}", flush=True)
                    print(f"=======================================================", flush=True)
                    print(v, flush=True)


if __name__ == "__main__":
    asyncio.run(main())
