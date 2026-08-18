# Wiring the Grafana MCP server into your IDE agent

This gives your AI coding assistant **live read access to your Grafana stack**
while it writes code. It can list your real datasources, run a PromQL query, and
check whether telemetry actually arrived — instead of guessing and handing you
queries that do not run.

This is separate from the agent you are building. This is tooling for *you*.

---

## Prerequisites

1. **A Grafana service account token.** In your stack:
   **Administration → Users and access → Service accounts → Add service account**
   → name `second-unit-mcp`, role **Editor** → **Add service account token** →
   **Generate**. Copy the `glsa_…` value immediately; it is shown once.
2. **`uv` installed**, which provides `uvx`. See `docs/WINDOWS_SETUP.md`.

The token needs **Editor**, not Viewer — Viewer cannot write annotations, and
annotation-writing is a core feature of this project.

---

## ⚠️ Before you paste a token into any config file

MCP config files hold the token in plaintext. Two of the paths below live
**inside this repository**, which is public.

`.gitignore` already excludes `.cursor/mcp.json` and `.vscode/mcp.json`, and CI
rejects any commit containing a `glsa_` or `glc_` string. Do not disable either
guard. If you prefer belt and braces, use a user-level config outside the repo.

---

## Cursor

Create `.cursor/mcp.json` in the repo root (gitignored), or
`%USERPROFILE%\.cursor\mcp.json` for all projects:

```json
{
  "mcpServers": {
    "grafana": {
      "command": "uvx",
      "args": ["mcp-grafana"],
      "env": {
        "GRAFANA_URL": "https://YOURSTACK.grafana.net",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": "glsa_your_token_here"
      }
    }
  }
}
```

Then **Settings → MCP** and confirm `grafana` shows a green indicator with a
tool count. Restart Cursor if it does not appear.

## VS Code (GitHub Copilot agent mode)

Create `.vscode/mcp.json` (gitignored). VS Code can prompt for the token instead
of storing it in the file, which is the safer pattern:

```json
{
  "inputs": [
    {
      "id": "grafana-token",
      "type": "promptString",
      "description": "Grafana service account token",
      "password": true
    }
  ],
  "servers": {
    "grafana": {
      "type": "stdio",
      "command": "uvx",
      "args": ["mcp-grafana"],
      "env": {
        "GRAFANA_URL": "https://YOURSTACK.grafana.net",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": "${input:grafana-token}"
      }
    }
  }
}
```

Open Copilot Chat, switch to **Agent** mode, and check the tools picker.

## Windsurf

Edit `%USERPROFILE%\.codeium\windsurf\mcp_config.json` — same shape as the
Cursor config above.

## Claude Code

```bash
claude mcp add grafana \
  --env GRAFANA_URL=https://YOURSTACK.grafana.net \
  --env GRAFANA_SERVICE_ACCOUNT_TOKEN=glsa_your_token \
  -- uvx mcp-grafana
```

Verify with `/mcp` inside a session.

## Gemini CLI

Edit `%USERPROFILE%\.gemini\settings.json`:

```json
{
  "mcpServers": {
    "grafana": {
      "command": "uvx",
      "args": ["mcp-grafana"],
      "env": {
        "GRAFANA_URL": "https://YOURSTACK.grafana.net",
        "GRAFANA_SERVICE_ACCOUNT_TOKEN": "glsa_your_token"
      }
    }
  }
}
```

---

## Also add the GitHub MCP server

Useful for letting your assistant open PRs and read CI failures directly:

```json
{
  "mcpServers": {
    "github": {
      "command": "npx",
      "args": ["-y", "@modelcontextprotocol/server-github"],
      "env": {
        "GITHUB_PERSONAL_ACCESS_TOKEN": "github_pat_your_token"
      }
    }
  }
}
```

Use a **fine-grained PAT scoped to the `second-unit` repository only**, with
Contents, Pull requests, Actions, and Workflows permissions. Do not use a
classic token with full `repo` scope.

---

## Confirming it works

Ask your assistant, in chat:

> List my Grafana datasources, then run this query against the Prometheus one:
> `sum by (status) (rate(render_frames_completed_total[5m]))`

If it returns real datasource names and real numbers, you are wired up. If it
returns plausible-looking but invented names, the server is not connected — the
model is hallucinating. Check the tool indicator in your IDE rather than trusting
the reply.

---

## Getting good output from your assistant

This repo ships two files written specifically for AI agents:

- **`AGENTS.md`** — hard constraints, forbidden dependencies, stack decisions,
  reference doc URLs. Cursor and Claude Code read it automatically.
- **`docs/PROJECT_BRIEF.md`** — what the project is, the incident scenario, and
  the definition of done.

Start each session by asking it to read both. The most common failure mode on
this project is an assistant that invents ADK method names; the reference links
in `AGENTS.md` exist to prevent exactly that. When in doubt, tell it to fetch
https://adk.dev/api-reference/python/ rather than recall from memory.
