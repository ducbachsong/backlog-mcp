"""The FastMCP application object and its process entry point.

Kept separate from the tool modules so they can import `mcp` without a cycle:
app.py never imports tools; `backlog_mcp/__init__.py` wires the two together.
"""

from mcp.server.fastmcp import FastMCP

from . import config

# Build dynamic instruction string listing all configured sources
_source_list = "; ".join(
    f"'{k}' → {v['host']} (project: {v['project_key']})"
    for k, v in config.SOURCES.items()
) or "no sources configured"

mcp = FastMCP(
    "Backlog Tools",
    instructions=(
        "You have access to Backlog project management tools. "
        f"Configured sources: {_source_list}. "
        f"Default source: '{config.DEFAULT_SOURCE}'. "
        "Call get_sources to list all available sources at runtime, and "
        "get_project_metadata to learn valid statuses / users / priorities / "
        "milestones / categories / versions / resolutions. "
        "When changing several fields of one issue, pass them all to a single "
        "update_issues call (optionally with comment + mention_user_ids) so the "
        "issue history records one change, not one per field. "
        "Always confirm with the user before calling create_issue, update_issues, "
        "add_comment, manage_comment, delete_issue, or any delete/bulk operation."
    ),
)


def main():
    """Start the MCP server on stdio (the entry point Claude Desktop launches).

    Input:  none — configuration comes from .env via config.py.
    Output: never returns; runs until the client disconnects.
    """
    mcp.run()
