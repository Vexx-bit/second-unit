# Second Unit — agent + Grafana MCP server in one container.
#
# WHY BOTH IN ONE IMAGE
#
# The obvious design is two Cloud Run services: the agent, and mcp-grafana over
# streamable-http. That is worse here, because an mcp-grafana instance holds a
# Grafana service-account token with Editor rights. Exposing it as a reachable
# HTTP endpoint means anything that finds the URL can read every dashboard and
# write annotations in the stack. Cloud Run IAM can lock that down, but then the
# agent has to mint and attach Google ID tokens on every MCP call — real
# complexity for no capability gain.
#
# Running mcp-grafana as a child process over stdio keeps the transport inside
# the container. Nothing listens on a network port but the agent itself, and the
# Grafana token never crosses a network boundary. This still satisfies the
# hackathon requirement to self-host the OSS Grafana MCP server with a service
# token.
#
# docs/DEPLOYMENT.md records the alternative and why it was rejected.

# --------------------------------------------------------------------------- #
# Stage 1 — build the mcp-grafana binary
# --------------------------------------------------------------------------- #
FROM golang:1.23-bookworm AS mcp-builder

# VERIFY THIS PATH before trusting the build. Check the install instructions in
# https://github.com/grafana/mcp-grafana — if the cmd path differs, fix it here
# rather than working around a build failure.
RUN go install github.com/grafana/mcp-grafana/cmd/mcp-grafana@latest

# --------------------------------------------------------------------------- #
# Stage 2 — the agent runtime
# --------------------------------------------------------------------------- #
FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=mcp-builder /go/bin/mcp-grafana /usr/local/bin/mcp-grafana

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

WORKDIR /app

COPY agent/pyproject.toml /app/pyproject.toml
RUN uv pip install --system --no-cache -r pyproject.toml

COPY agent/second_unit /app/second_unit

# The toolset spawns the MCP server by command name. With the binary on PATH,
# stdio works identically here and on a laptop — so "works locally, breaks in
# Cloud Run" is not a class of bug this project can have.
ENV GRAFANA_MCP_COMMAND=mcp-grafana \
    PYTHONUNBUFFERED=1 \
    AGENT_ENV=cloudrun

EXPOSE 8080

# VERIFY the flags with `adk api_server --help` for your pinned ADK version
# before the first deploy. Do not guess at them.
CMD ["sh", "-c", "adk api_server --host 0.0.0.0 --port ${PORT:-8080} /app"]
