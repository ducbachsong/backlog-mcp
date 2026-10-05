"""The FastMCP application object and its process entry point.

Kept separate from the tool modules so they can import `mcp` without a cycle:
app.py never imports tools; `backlog_mcp/__init__.py` wires the two together.
"""

from mcp.server.fastmcp import FastMCP

from . import config, stash

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
        "Files: get_attachments(save=True) and manage_files put files in a local "
        "stash and return handles ('f1'); pass handles or allowlisted local paths "
        "as `attachments` to add_comment / create_issue / update_issues / "
        "manage_wiki_page. To copy a comment with its images: get_comments → "
        "get_attachments(comment_id=..., save=True) → add_comment(attachments=...). "
        "Images pasted into the chat cannot be attached — ask the user to save "
        "them to disk, then find them with manage_files(action='list_dir'). "
        "Always confirm with the user before calling create_issue, update_issues, "
        "add_comment, manage_comment, delete_issue, or any delete/bulk operation."
    ),
)


def main():
    """Start the MCP server on stdio (the entry point Claude Desktop launches).

    Input:  none — configuration comes from .env via config.py.
    Output: never returns; runs until the client disconnects. The stash folder
            is removed on exit (see stash.py).
    """
    stash.sweep_stale()
    mcp.run()
