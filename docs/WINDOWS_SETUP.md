# Windows setup

The `Makefile` and the shell scripts in `scripts/` assume a Unix shell. On
Windows you have two options. **Option A is recommended** — it is what the
project is developed against and it avoids a class of path and line-ending bugs.

---

## Option A — WSL (recommended)

One-time, in PowerShell **as Administrator**:

```powershell
wsl --install -d Ubuntu
```

Reboot if prompted, set a username and password, then inside the Ubuntu shell:

```bash
sudo apt update && sudo apt install -y make git
curl -LsSf https://astral.sh/uv/install.sh | sh
exec $SHELL

git clone https://github.com/Vexx-bit/second-unit.git
cd second-unit
```

Everything in the README now works verbatim: `make backfill`, `make verify-mcp`,
`make inject-incident`.

> Clone **inside** the WSL filesystem (`~/second-unit`), not under `/mnt/c/`.
> Cross-filesystem access is slow and causes permission oddities.

---

## Option B — native Windows PowerShell

Works fine for `telemetry-sim`. You skip `make` and call `uv` directly.

### 1. Install uv

In PowerShell:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Close and reopen PowerShell afterwards so `uv` is on your PATH.

### 2. Create `.env`

**Use PowerShell, not `cmd`.** Open PowerShell in the repo folder and paste this
as a single block. Fill in the two blank values as you obtain them.

```powershell
@'
GRAFANA_URL=https://YOURSTACK.grafana.net
GRAFANA_SERVICE_ACCOUNT_TOKEN=

OTEL_EXPORTER_OTLP_ENDPOINT=https://otlp-gateway-prod-eu-west-2.grafana.net/otlp
OTEL_EXPORTER_OTLP_HEADERS=Authorization=Basic%20YOUR_BASE64_TOKEN
OTEL_EXPORTER_OTLP_PROTOCOL=http/protobuf

GOOGLE_CLOUD_PROJECT=second-unit
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_GENAI_USE_VERTEXAI=true

GRAFANA_MCP_URL=
'@ | Set-Content -Path .env -Encoding utf8
```

Verify it wrote correctly:

```powershell
Get-Content .env
```

### 3. Run the simulator

```powershell
cd telemetry-sim

# Backfill 30 minutes of history in ~3 minutes
uv run farm.py --duration 1800 --speed 10

# Healthy farm, real time
uv run farm.py --duration 600

# Healthy baseline, then the asset v7 incident at t+120s
uv run farm.py --duration 600 --inject-incident --incident-at 120
```

### 4. Makefile equivalents

| Makefile target | PowerShell equivalent |
| --- | --- |
| `make backfill` | `cd telemetry-sim; uv run farm.py --duration 1800 --speed 10` |
| `make sim` | `cd telemetry-sim; uv run farm.py --duration 600` |
| `make inject-incident` | `cd telemetry-sim; uv run farm.py --duration 600 --inject-incident` |
| `make verify-mcp` | see below |

### 5. Verifying the MCP connection on Windows

`scripts/verify-grafana-mcp.sh` is bash-only. The PowerShell equivalent:

```powershell
$env:GRAFANA_URL = "https://YOURSTACK.grafana.net"
$env:GRAFANA_SERVICE_ACCOUNT_TOKEN = "glsa_your_token"

@(
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"verify","version":"0.1.0"}}}'
  '{"jsonrpc":"2.0","method":"notifications/initialized"}'
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'
) | uvx mcp-grafana
```

A long JSON blob listing tools like `query_prometheus`, `query_loki_logs`,
`list_datasources`, and `create_annotation` means success. An auth error means
the token is wrong or the role is below Editor.

---

## Common Windows gotchas

| Symptom | Cause | Fix |
| --- | --- | --- |
| `'cp' is not recognized` | you are in `cmd`, not PowerShell | use PowerShell; `cp` there is an alias for `Copy-Item` |
| `<< was unexpected at this time` | bash heredoc pasted into `cmd` | use the PowerShell `@'...'@` block above |
| `'make' is not recognized` | `make` is not a Windows program | use Option A, or the table in step 4 |
| `uv: command not found` | PATH not refreshed | close and reopen the terminal |
| 401 from the OTLP endpoint | header mangled | keep `Authorization=Basic%20...` exactly, including `%20`; no quotes inside `.env` |
| `.env` values have stray quotes | editor added them | values in `.env` must be bare, unquoted |
