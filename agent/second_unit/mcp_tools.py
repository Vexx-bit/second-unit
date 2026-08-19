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

_API_REFERENCE = "https://adk.dev/api-reference/python/"


def _resolve(names: list[tuple[str, str]], what: str) -> Any:
    """Import the first name that exists, or raise a directive error.

    Args:
        names: (module_path, attribute_name) candidates, in preference order.
        what: human description used in the error message.
    """
    import importlib

    attempted = []
    for module_path, attr in names:
        attempted.append(f"{module_path}.{attr}")
        try:
            module = importlib.import_module(module_path)
        except ImportError:
            continue
        resolved = getattr(module, attr, None)
        if resolved is not None:
            return resolved

    raise ImportError(
        f"Could not resolve {what} in the installed google-adk.\n"
        f"Tried: {', '.join(attempted)}\n"
        f"Check the API reference at {_API_REFERENCE} for the current name, then "
        f"update agent/second_unit/mcp_tools.py. Do NOT invent a name."
    )


def _mcp_toolset_cls() -> Any:
    return _resolve(
        [
            ("google.adk.tools.mcp_tool", "McpToolset"),
            ("google.adk.tools.mcp_tool", "MCPToolset"),
            ("google.adk.tools.mcp_tool.mcp_toolset", "MCPToolset"),
            ("google.adk.tools", "McpToolset"),
        ],
        "the MCP toolset class",
    )


def _http_params_cls() -> Any:
    return _resolve(
        [
            ("google.adk.tools.mcp_tool", "StreamableHTTPConnectionParams"),
            ("google.adk.tools.mcp_tool", "StreamableHTTPServerParams"),
            (
                "google.adk.tools.mcp_tool.mcp_session_manager",
                "StreamableHTTPConnectionParams",
            ),
        ],
        "the streamable-http connection params class",
    )


def _stdio_params_cls() -> Any:
    return _resolve(
        [
            ("google.adk.tools.mcp_tool", "StdioConnectionParams"),
            ("google.adk.tools.mcp_tool.mcp_session_manager", "StdioConnectionParams"),
            ("google.adk.tools.mcp_tool", "StdioServerParameters"),
        ],
        "the stdio connection params class",
    )


# Tools each sub-agent is allowed to touch. Narrow allowlists keep the model from
# wandering into unrelated capabilities and make the investigation reproducible.
#
# NOTE: these names must match the tools your mcp-grafana build actually exposes.
# Verify with a tools/list call before relying on them — see TASK-06.
TRIAGE_TOOLS = [
    "list_datasources",
    "query_prometheus",
    "list_alert_rules",
    "get_alert_rule_by_uid",
]

CORRELATE_TOOLS = [
    "list_datasources",
    "query_prometheus",
    "query_loki_logs",
    "query_loki_stats",
    "list_loki_label_values",
    "query_tempo_traces",
    "get_trace",
]

REPORT_TOOLS = [
    "list_datasources",
    "search_dashboards",
    "get_dashboard_by_uid",
    "create_annotation",
]


def build_grafana_toolset(tool_filter: list[str] | None = None) -> Any:
    """Build an MCP toolset pointed at Grafana.

    Args:
        tool_filter: optional allowlist of tool names for this toolset.

    Raises:
        RuntimeError: if the required environment variables are missing.
    """
    toolset_cls = _mcp_toolset_cls()
    mcp_url = os.getenv("GRAFANA_MCP_URL", "").strip()

    if mcp_url:
        params = _http_params_cls()(url=mcp_url)
        return toolset_cls(connection_params=params, tool_filter=tool_filter)

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

    params_cls = _stdio_params_cls()
    params = params_cls(
        command="uvx",
        args=["mcp-grafana"],
        env={
            "GRAFANA_URL": grafana_url,
            "GRAFANA_SERVICE_ACCOUNT_TOKEN": token,
        },
    )
    return toolset_cls(connection_params=params, tool_filter=tool_filter)
