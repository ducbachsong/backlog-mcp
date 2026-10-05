"""Tools: reading and editing wiki pages."""

from typing import Any, Optional

from ..app import mcp
from .. import api, attach
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


def _attach_to_wiki(source: str, wiki_id: int, files) -> list:
    """Link staged files to a wiki page (wikis take files on a separate endpoint)."""
    if not files:
        return []
    ids = attach.upload(source, files)
    return api.post(source, f"/wikis/{wiki_id}/attachments", {"attachmentId[]": ids})


@mcp.tool()
def manage_wiki_page(
    action: str,
    source: str = D,
    wiki_id: int = 0,
    name: str = "",
    content: str = "",
    mail_notify: bool = False,
    attachments: Optional[list[str]] = None,
    embed_images: bool = True,
) -> dict:
    """Create, update or delete a wiki page, optionally attaching files.
    ⚠️ CONFIRM WITH USER — show the page name, content and files first; delete is
    IRREVERSIBLE.

    Args:
        action: 'create', 'update' or 'delete'.
        source: Source name from get_sources. Empty = default source.
        wiki_id: Page id from get_wikis. Required for update and delete.
        name: Page title. Required for create; empty on update = keep current.
        content: Page body (Backlog Markdown). Required for create; empty on
                 update = keep current.
        mail_notify: True sends an email notification to project members.
        attachments: Files to attach (create / update) — stash handles ('f1',
                     from get_attachments save=True or manage_files) and/or local
                     file paths inside the upload allowlist. On update, files
                     alone are enough; name/content may stay empty.
        embed_images: True (default) = image files not already referenced in
                      `content` are appended to it as inline images. Has no
                      effect when content is left unchanged on update.

    Returns:
        dict: the created / updated / deleted wiki page as returned by Backlog
        (plus 'attached': [file names] when files were given), or
        {'error': message} for an unknown action, a missing argument or a bad
        file ref.
    """
    notify = "true" if mail_notify else "false"
    try:
        files = attach.prepare(attachments) if action in ("create", "update") else []
    except ValueError as e:
        return {"error": str(e)}
    if files and embed_images and content:
        content = attach.embed_images(source, content, files)

    if action == "create":
        if not name or not content:
            return {"error": "name and content are required for action='create'"}
        page = api.post(source, "/wikis", {
            "projectId":  api.project_id(source),
            "name":       name,
            "content":    content,
            "mailNotify": notify,
        })
        if files:
            _attach_to_wiki(source, page["id"], files)
            page["attached"] = attach.names(files)
        return page

    if not wiki_id:
        return {"error": f"wiki_id is required for action='{action}'"}

    if action == "update":
        data: dict = {"mailNotify": notify}
        if name:
            data["name"] = name
        if content:
            data["content"] = content
        if len(data) == 1 and not files:
            return {"error": "Pass name, content and/or attachments to update"}
        page = api.patch(source, f"/wikis/{wiki_id}", data) if len(data) > 1 else {"id": wiki_id}
        if files:
            _attach_to_wiki(source, wiki_id, files)
            page["attached"] = attach.names(files)
        return page

    if action == "delete":
        return api.delete(source, f"/wikis/{wiki_id}", {"mailNotify": notify})

    return {"error": f"Unknown action '{action}'. Use 'create', 'update' or 'delete'."}
