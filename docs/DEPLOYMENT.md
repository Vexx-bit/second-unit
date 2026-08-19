# Deployment

## The short answer

Run the agent and `mcp-grafana` **in the same container**, with MCP over stdio.
Deploy that one container to Cloud Run, private. Do not expose the MCP server on
a URL, and do not use a tunnel.

```powershell
$env:GOOGLE_CLOUD_PROJECT = "second-unit"
$env:GOOGLE_CLOUD_LOCATION = "us-central1"
$env:GRAFANA_URL = "https://violetheron2036.grafana.net"
bash infra/deploy.sh
```

## Why not a public MCP URL

An `mcp-grafana` process holds a Grafana service-account token with **Editor**
rights. Put it behind a public URL and you have published an unauthenticated
proxy to your observability stack: anyone who finds the hostname can read every
dashboard, query every datasource, and write annotations.

The MCP protocol has no built-in authentication on the streamable-http transport.
Authentication is the deployment's job, so "just make it public" means "no
authentication at all."

## Why not cloudflared

A tunnel is the right tool for reaching a service on a machine you cannot give a
public address to — a laptop behind NAT, a homelab. Here the agent and the MCP
server run in the same process tree, so there is no network gap to bridge.
Adding a tunnel would create the gap and then span it.

It also adds a failure mode you do not want during a recorded demo: a tunnel that
drops, or a free hostname that rotates, takes the whole investigation down
mid-take.

## The three options, honestly

| Option | Auth story | Complexity | Verdict |
| --- | --- | --- | --- |
| **stdio, same container** | Token never leaves the process tree | Low | **Use this** |
| Separate Cloud Run service, IAM + ingress internal | Agent must mint and attach Google ID tokens per call | High | Defensible, unnecessary |
| Public streamable-http, or a tunnel | None | Low | Do not |

The middle option is a legitimate architecture — it is what you would build if
several distinct agents shared one MCP server. With one agent it is pure
overhead, and the ID-token plumbing is exactly the kind of thing that breaks
quietly the night before a deadline.

If a judge asks why the MCP server is not its own service, that table is the
answer. Having considered and rejected the distributed version reads better than
not having thought about it.

## Local development

Identical transport, no container:

```powershell
cd agent
uv run adk web
```

With `GRAFANA_MCP_URL` unset, `mcp_tools.py` spawns the MCP server over stdio.
The only difference in Cloud Run is that the binary is baked into the image
instead of fetched at runtime — so "works locally, breaks deployed" is not a
class of bug this project can have.

## Secrets

Two secrets in Secret Manager, never in env vars on the service definition
(Cloud Run env vars are readable by anyone with project view access):

| Secret | Contents |
| --- | --- |
| `grafana-token` | the `glsa_` service-account token, Editor role |
| `otlp-headers` | the `Authorization=Basic%20...` OTLP header value |

```bash
printf '%s' "$GRAFANA_SERVICE_ACCOUNT_TOKEN" | gcloud secrets create grafana-token --data-file=-
printf '%s' "$OTEL_EXPORTER_OTLP_HEADERS"    | gcloud secrets create otlp-headers  --data-file=-
```

Use `printf`, not `echo` — `echo` appends a newline, and a trailing newline in a
bearer token produces a 401 that looks like a permissions problem.

Keep `%20` intact in the OTLP header value. It is W3C-baggage encoding; the SDK
decodes it. "Fixing" it to a space breaks ingestion.

## Service account IAM

The Cloud Run runtime service account needs:

| Role | Why |
| --- | --- |
| `roles/aiplatform.user` | Gemini calls through Vertex AI |
| `roles/secretmanager.secretAccessor` | read the two secrets above |

Nothing else. If a deploy fails on permissions, add the specific role — do not
grant Editor to make an error go away.

## Calling the deployed service

It is private, so requests need an identity token:

```bash
URL=$(gcloud run services describe second-unit-agent \
  --region=us-central1 --format='value(status.url)')

curl -H "Authorization: Bearer $(gcloud auth print-identity-token)" "$URL/list-apps"
```

For a browser UI against the deployed service:

```bash
gcloud run services proxy second-unit-agent --region=us-central1
```

## Recording the demo

Record against **local `adk web`**, not the deployed service.

`adk web` shows each stage's tool calls and reasoning as they happen, which is
what makes the investigation legible to a judge. A deployed API server returns
JSON. The Cloud Run deployment exists to prove the thing runs in production; the
video exists to show what it does. Those are different jobs.

Mention the deployment in the video, show the dashboard annotation the agent
wrote, and keep the runtime visible.
