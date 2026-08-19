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
#
# WHY uvx AND NOT A GO BUILD
#
# An earlier revision built mcp-grafana from source in a golang builder stage.
# That was unnecessary: it is installable with uvx, which is exactly how the
# local dev setup and the IDE launch it. Matching the local launch command is
# worth more than a marginally smaller image, because it removes the class of bug
# where the MCP server behaves differently in Cloud Run than on the laptop the
# demo was rehearsed on.

FROM python:3.12-slim-bookworm

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv
COPY --from=ghcr.io/astral-sh/uv:latest /uvx /usr/local/bin/uvx

ENV PATH="/root/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    AGENT_ENV=cloudrun \
    UV_LINK_MODE=copy

WORKDIR /app

COPY agent/pyproject.toml /app/pyproject.toml
RUN uv pip install --system --no-cache -r pyproject.toml

# Pre-warm the uvx cache so the first MCP call does not pay a download. The agent
# still launches it as `uvx mcp-grafana`, identical to local development.
RUN uv tool install mcp-grafana

COPY agent/second_unit /app/second_unit

EXPOSE 8080

# VERIFY the flags with `adk api_server --help` for ADK 2.7.1 before the first
# deploy. Do not guess at them.
CMD ["sh", "-c", "adk api_server --host 0.0.0.0 --port ${PORT:-8080} /app"]
