"""Tools: reading and editing wiki pages."""

from typing import Any

from ..app import mcp
from .. import api
from ..common import D


@mcp.tool()
def get_wikis(source: str = D, wiki_id: int = 0, keyword: str = "", count_only: bool = False) -> Any:
    """List the project's wiki pages, read one page in full, or just count them.

    Args:
        source: Source name from get_sources. Empty = default source.
        wiki_id: 0 (default) = list pages. Non-zero = return that page in full.
        keyword: Filter the listing by page name. Empty = all. Ignored when
                 wiki_id is given.
        count_only: True = return only how many wiki pages the project has.

    Returns:
        {'count': int} when count_only=True; the full page dict (including
        content and attachments) when wiki_id is given; otherwise a list of slim
        page dicts whose content is truncated to 500 characters.
    """
    if count_only:
        result = api.get(source, "/wikis/count", {"projectIdOrKey": api.project_key(source)})
        return {"count": result.get("count", 0)}
    if wiki_id:
        return api.get(source, f"/wikis/{wiki_id}")
    params: dict = {"projectIdOrKey": api.project_key(source)}
    if keyword:
        params["keyword"] = keyword
    return [api.slim_wiki(p) for p in api.get(source, "/wikis", params)]


@mcp.tool()
def manage_wiki_page(
    action: str,
    source: str = D,
    wiki_id: int = 0,
    name: str = "",
    content: str = "",
    mail_notify: bool = False,
) -> dict:
    """Create, update or delete a wiki page.
    ⚠️ CONFIRM WITH USER — show the page name and content first; delete is IRREVERSIBLE.

    Args:
        action: 'create', 'update' or 'delete'.
        source: Source name from get_sources. Empty = default source.
        wiki_id: Page id from get_wikis. Required for update and delete.
        name: Page title. Required for create; empty on update = keep current.
        content: Page body (Backlog Markdown). Required for create; empty on
                 update = keep current.
        mail_notify: True sends an email notification to project members.

    Returns:
        dict: the created / updated / deleted wiki page as returned by Backlog,
        or {'error': message} for an unknown action or a missing argument.
    """
    notify = "true" if mail_notify else "false"

    if action == "create":
        if not name or not content:
            return {"error": "name and content are required for action='create'"}
        return api.post(source, "/wikis", {
            "projectId":  api.project_id(source),
            "name":       name,
            "content":    content,
            "mailNotify": notify,
        })

    if not wiki_id:
        return {"error": f"wiki_id is required for action='{action}'"}

    if action == "update":
        data: dict = {"mailNotify": notify}
        if name:
            data["name"] = name
        if content:
            data["content"] = content
        if len(data) == 1:
            return {"error": "Pass name and/or content to update"}
        return api.patch(source, f"/wikis/{wiki_id}", data)

    if action == "delete":
        return api.delete(source, f"/wikis/{wiki_id}", {"mailNotify": notify})

    return {"error": f"Unknown action '{action}'. Use 'create', 'update' or 'delete'."}
