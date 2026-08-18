#!/usr/bin/env bash
# Smoke test for the Grafana MCP connection.
#
# Confirms that GRAFANA_URL + GRAFANA_SERVICE_ACCOUNT_TOKEN in .env can drive
# mcp-grafana, and prints the tools it exposes. Run this BEFORE writing any
# agent code — if this fails, nothing downstream can work.
#
# Requires: uv (https://docs.astral.sh/uv/getting-started/installation/)

set -euo pipefail

if [ ! -f .env ]; then
  echo "ERROR: no .env found. Copy .env.example to .env and fill it in." >&2
  exit 1
fi

set -a
# shellcheck disable=SC1091
. ./.env
set +a

: "${GRAFANA_URL:?GRAFANA_URL is not set in .env}"
: "${GRAFANA_SERVICE_ACCOUNT_TOKEN:?GRAFANA_SERVICE_ACCOUNT_TOKEN is not set in .env}"

case "$GRAFANA_SERVICE_ACCOUNT_TOKEN" in
  glsa_*) ;;
  *) echo "WARNING: token does not start with 'glsa_' — is this a service account token?" >&2 ;;
esac

echo "Stack:  $GRAFANA_URL"
echo "Probing mcp-grafana over stdio..."
echo

response=$(printf '%s\n' \
  '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2024-11-05","capabilities":{},"clientInfo":{"name":"second-unit-verify","version":"0.1.0"}}}' \
  '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
  '{"jsonrpc":"2.0","id":2,"method":"tools/list"}' \
  | uvx mcp-grafana 2>/dev/null || true)

if [ -z "$response" ]; then
  echo "FAILED: no response from mcp-grafana." >&2
  echo "Check that uv is installed and that GRAFANA_URL has no trailing slash." >&2
  exit 1
fi

tool_count=$(printf '%s' "$response" | grep -o '"name":"[a-z_]*"' | sort -u | wc -l | tr -d ' ')

if [ "$tool_count" -lt 5 ]; then
  echo "FAILED: only $tool_count tools discovered. Raw response:" >&2
  printf '%s\n' "$response" >&2
  exit 1
fi

echo "SUCCESS: mcp-grafana exposed $tool_count tools."
echo
echo "Sample of available tools:"
printf '%s' "$response" | grep -o '"name":"[a-z_]*"' | sort -u | head -20 | sed 's/"name":"/  - /; s/"$//'
echo
echo "Next: confirm your OTLP variables are set, then build telemetry-sim/."
