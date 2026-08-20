"""Pre-sim clean-window gate.

Run this BEFORE starting telemetry-sim. If the 30-minute lookback window
contains data from a prior run, this script aborts with the number of minutes
remaining until the window is clear.

Usage:
    uv run python check_window.py
"""
from __future__ import annotations
import json, os, sys, time, urllib.parse, urllib.request
from pathlib import Path
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

def _prom_instant(url, token, expr):
    q = urllib.parse.urlencode({"query": expr})
    req = urllib.request.Request(f"{url}/api/datasources/uid/grafanacloud-prom/resources/api/v1/query?{q}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("data", {}).get("result", [])

def _loki_instant(url, token, expr):
    q = urllib.parse.urlencode({"query": expr})
    req = urllib.request.Request(f"{url}/api/datasources/proxy/uid/grafanacloud-logs/loki/api/v1/query?{q}")
    req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode()).get("data", {}).get("result", [])

def main():
    url = os.getenv("GRAFANA_URL", "").rstrip("/")
    token = os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN", "")
    if not url or not token:
        print("GRAFANA_URL or GRAFANA_SERVICE_ACCOUNT_TOKEN not set."); sys.exit(1)
    
    try:
        prom_result = _prom_instant(url, token, "sum(increase(render_frames_completed_total[30m]))")
    except Exception as e:
        print(f"Prometheus window check failed: {e}"); sys.exit(1)
        
    has_metrics = prom_result and float(prom_result[0]["value"][1]) > 0
    
    try:
        loki_result = _loki_instant(url, token, 'sum(count_over_time({service_name="render-farm"}[30m]))')
    except Exception as e:
        print(f"Loki window check failed: {e}"); sys.exit(1)
        
    has_logs = False
    if loki_result:
        for r in loki_result:
            if float(r["value"][1]) > 0:
                has_logs = True
                break
                
    if not has_metrics and not has_logs:
        print("Window is clean -- no prior run data in the 30m lookback."); return

    wait_min = 30
    if has_metrics:
        try:
            ts_result = _prom_instant(url, token, "timestamp(render_frames_completed_total)")
            last_ts = max(float(r["value"][1]) for r in ts_result) if ts_result else time.time()
            wait_min = max(1, (int(last_ts + 30*60 - time.time()) + 59) // 60)
        except Exception:
            wait_min = 30
            
    if has_logs:
        print(f"PRIOR RUN LOGS IN LOOKBACK WINDOW -- wait {wait_min} minute(s) before the demo run."); sys.exit(1)
    else:
        print(f"PRIOR RUN IN LOOKBACK WINDOW -- wait {wait_min} minute(s) before the demo run."); sys.exit(1)

if __name__ == "__main__":
    main()
