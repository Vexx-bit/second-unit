"""Grafana MCP toolset construction.

The agent reaches Grafana ONLY through MCP — never via direct HTTP calls to the
Grafana API. That is the hackathon track requirement and the architectural point
of the project.

Two transports are supported:

- **stdio** (local development): spawns `uvx mcp-grafana` as a subprocess.
  Requires GRAFANA_URL and GRAFANA_SERVICE_ACCOUNT_TOKEN.
- **streamable-http** (deployed): connects to a self-hosted mcp-grafana on Cloud
  Run. Requires GRAFANA_MCP_URL.

If GRAFANA_MCP_URL is set, HTTP is used. Otherwise stdio.

---

WHY THE IMPORT SHIM BELOW EXISTS

ADK renamed and moved these classes across releases: `MCPToolset` vs
`McpToolset`, and `StreamableHTTPConnectionParams` vs `StreamableHTTPServerParams`
vs `RemoteMcpServer`. Guessing wrong produces a confusing ImportError deep in a
call stack.

So resolution happens once, here, with an explicit error naming the API reference
to check. When the installed ADK version is pinned and confirmed, collapse this
shim into a single direct import — see TASK-06 in docs/TASKS-SPRINT2.md.
"""

from __future__ import annotations

import os
from typing import Any

from google.adk.tools.mcp_tool import (
    McpToolset,
    StdioConnectionParams,
    StreamableHTTPConnectionParams,
)
from mcp import StdioServerParameters

# Tools each sub-agent is allowed to touch. Narrow allowlists keep the model from
# wandering into unrelated capabilities and make the investigation reproducible.
#
# Verified against mcp-grafana tool names on the live stack (TASK-06):
TRIAGE_TOOLS = [
    "list_datasources",
    "query_prometheus",
    "alerting_manage_rules",
]

CORRELATE_TOOLS = [
    "list_datasources",
    "query_prometheus",
    "query_loki_logs",
    "query_loki_stats",
    "list_loki_label_values",
    "tempo_traceql-search",
    "tempo_get-trace",
]

REPORT_TOOLS = [
    "list_datasources",
    "search_dashboards",
    "get_dashboard_by_uid",
    "create_annotation",
    "query_prometheus",
]


def build_grafana_toolset(tool_filter: list[str] | None = None) -> Any:
    """Build an MCP toolset pointed at Grafana.

    Args:
        tool_filter: optional allowlist of tool names for this toolset.

    Raises:
        RuntimeError: if the required environment variables are missing.
    """
    mcp_url = os.getenv("GRAFANA_MCP_URL", "").strip()

    if mcp_url:
        params = StreamableHTTPConnectionParams(url=mcp_url)
        return McpToolset(connection_params=params, tool_filter=tool_filter)

    grafana_url = os.getenv("GRAFANA_URL", "").strip()
    token = os.getenv("GRAFANA_SERVICE_ACCOUNT_TOKEN", "").strip()

    if not grafana_url or not token:
        raise RuntimeError(
            "Set GRAFANA_MCP_URL for a remote MCP server, or both GRAFANA_URL and "
            "GRAFANA_SERVICE_ACCOUNT_TOKEN to run mcp-grafana locally over stdio. "
            "See .env.example."
        )

    if grafana_url.endswith("/"):
        raise RuntimeError(
            f"GRAFANA_URL must not end with a slash (got {grafana_url!r}). "
            "mcp-grafana builds malformed request paths otherwise."
        )

    server_params = StdioServerParameters(
        command="uvx",
        args=["mcp-grafana"],
        env={
            "GRAFANA_URL": grafana_url,
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": token,
        },
    )
    params = StdioConnectionParams(server_params=server_params, timeout=30.0)
    return McpToolset(connection_params=params, tool_filter=tool_filter)
