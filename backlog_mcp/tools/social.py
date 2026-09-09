"""Tools: watchers and stars — who is following an issue, and what is liked."""

from typing import Any

from ..app import mcp
from .. import api
from ..common import D


@mcp.tool()
def manage_watchers(issue_key: str, source: str = D, action: str = "list", user_id: int = 0) -> Any:
    """List, add or remove the users watching an issue.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'.
        source: Source name from get_sources. Empty = default source.
        action: 'list' (default), 'add' or 'delete'.
        user_id: User id from get_project_metadata (kinds='users'). Required for
                 'add' and 'delete'.

    Returns:
        list of watcher dicts for action='list'; the affected watcher record for
        'add'/'delete'; {'error': message} for an unknown action or missing user_id.
    """
    if action == "list":
        return api.get(source, f"/issues/{issue_key}/watchers")
    if not user_id:
        return {"error": f"user_id is required for action='{action}'"}
    if action == "add":
        return api.post(source, f"/issues/{issue_key}/watchers", {"userId": user_id})
    if action == "delete":
        return api.delete(source, f"/issues/{issue_key}/watchers/{user_id}")
    return {"error": f"Unknown action '{action}'. Use 'list', 'add' or 'delete'."}


@mcp.tool()
def add_star(
    source: str = D,
    issue_id: int = 0,
    comment_id: int = 0,
    wiki_page_id: int = 0,
) -> dict:
    """Add a star (like) to an issue, comment, or wiki page.
    Provide exactly one of: issue_id, comment_id, or wiki_page_id.

    Args:
        source: Source name from get_sources. Empty = default source.
        issue_id: Numeric issue id — NOT the key like 'PROJECT-123'. Get it from
                  get_issue (the 'id' field of the full record).
        comment_id: Comment id from get_comments.
        wiki_page_id: Wiki page id from get_wikis.

    Returns:
        dict: Backlog's response (empty on success), or {'error': message} when
        no target was given.
    """
    data: dict = {}
    if issue_id:
        data["issueId"] = issue_id
    elif comment_id:
        data["commentId"] = comment_id
    elif wiki_page_id:
        data["wikiPageId"] = wiki_page_id
    else:
        return {"error": "Provide one of: issue_id, comment_id, wiki_page_id"}
    return api.post(source, "/stars", data)
