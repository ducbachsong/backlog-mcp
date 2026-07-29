"""Backlog MCP Server — exposes Backlog project management tools for Claude Desktop."""

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from mcp import types as mcp_types

from mcp.server.fastmcp import FastMCP

import config
import backlog_api as api

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
        "Call get_sources to list all available sources at runtime. "
        "Always confirm with the user before calling create_issue, update_issue, "
        "add_comment, add_comment_with_mention, delete_comment, delete_issue, "
        "or any delete/bulk operation."
    ),
)

# Convenience: use empty string as default so callers get DEFAULT_SOURCE automatically.
# All tools accept source="" which resolves to config.DEFAULT_SOURCE inside backlog_api._src().
_D = ""  # sentinel for "use default source"


# ── Source discovery ──────────────────────────────────────────────────────────

@mcp.tool()
def get_sources() -> dict:
    """List all configured Backlog sources (spaces) available in this server.
    Use the returned source names as the 'source' argument in other tools.
    """
    return {
        "default": config.DEFAULT_SOURCE,
        "sources": {
            name: {"host": cfg["host"], "projectKey": cfg["project_key"]}
            for name, cfg in config.SOURCES.items()
        },
    }


# ── Project metadata ──────────────────────────────────────────────────────────

@mcp.tool()
def get_project(source: str = _D) -> dict:
    """Get Backlog project info (id, name, projectKey).

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}")


@mcp.tool()
def get_project_statuses(source: str = _D) -> list:
    """Get all valid ticket statuses for the project (Open, In Progress, Resolved, Closed, ...).

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/statuses")


@mcp.tool()
def get_project_users(source: str = _D) -> list:
    """Get all members of the Backlog project with their id and name.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/users")


@mcp.tool()
def get_issue_types(source: str = _D) -> list:
    """Get all issue types (Bug, Task, Feature, ...) with their ids.
    Call this before create_issue to get valid issue_type_id values.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/issueTypes")


@mcp.tool()
def get_categories(source: str = _D) -> list:
    """Get all categories of the project with their ids.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/categories")


@mcp.tool()
def get_milestones(source: str = _D) -> list:
    """Get all milestones/sprints of the project with ids and dates.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/versions")


@mcp.tool()
def get_priorities(source: str = _D) -> list:
    """Get all priority levels (Normal, High, Low, ...) with their ids.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, "/priorities")


# ── Issues — read ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_issues(
    source: str = _D,
    status: str = "all",
    assignee: str = "",
    created_by: str = "",
    keyword: str = "",
    issue_type: str = "",
    priority: str = "",
    category: str = "",
    milestone: str = "",
    updated_since: str = "",
    updated_until: str = "",
    created_since: str = "",
    created_until: str = "",
    due_date_since: str = "",
    due_date_until: str = "",
    sort: str = "updated",
    order: str = "desc",
    limit: int = 20,
) -> dict:
    """Search and list Backlog issues with filters. Main tool for listing/filtering tickets.

    Args:
        source: Source name from get_sources. Empty = default source.
        status: Filter by status. Values: 'open', 'in_progress', 'resolved', 'closed', 'all'.
                Combine multiple with comma, e.g. 'open,in_progress'.
        assignee: Assignee name (partial match, case-insensitive). Empty = all.
        created_by: Creator name (partial match). Empty = all.
        keyword: Keyword to search in title and description. Empty = all.
        issue_type: Issue type name (partial match: 'Bug', 'Task', 'Feature'). Empty = all.
        priority: Priority name (partial match: 'High', 'Normal', 'Low'). Empty = all.
        category: Category name (partial match). Empty = all.
        milestone: Milestone/sprint name (partial match). Empty = all.
        updated_since: Issues updated from this date (YYYY-MM-DD format).
        updated_until: Issues updated until this date (YYYY-MM-DD format).
        created_since: Issues created from this date (YYYY-MM-DD format).
        created_until: Issues created until this date (YYYY-MM-DD format).
        due_date_since: Issues with due date from this date (YYYY-MM-DD format).
        due_date_until: Issues with due date until this date (YYYY-MM-DD format).
        sort: Sort by field — 'updated' (default), 'created', 'priority', 'status', 'dueDate'.
        order: Sort order — 'desc' (default, newest first) or 'asc'.
        limit: Max issues to return (default 20, max 100).
    """
    project = api.cached_meta(f"project:{source}",
                              lambda: api._get(source, f"/projects/{api.project_key(source)}"))

    status_ids = None
    if status and status != "all":
        ids = [api.STATUS_MAP[s.strip()] for s in status.split(",") if s.strip() in api.STATUS_MAP]
        status_ids = ids or None

    assignee_ids   = api.resolve_users(source, assignee)
    created_by_ids = api.resolve_users(source, created_by)

    pkey = api.project_key(source)
    issue_type_ids = api.resolve_names(source, f"issue_types:{source}", f"/projects/{pkey}/issueTypes", issue_type)
    priority_ids   = api.resolve_names(source, f"priorities:{source}", "/priorities", priority)
    category_ids   = api.resolve_names(source, f"categories:{source}", f"/projects/{pkey}/categories", category)
    milestone_ids  = api.resolve_names(source, f"milestones:{source}", f"/projects/{pkey}/versions", milestone)

    cap = min(max(1, limit), 100)
    issues = api.fetch_issues_raw(
        source, project["id"],
        assignee_ids=assignee_ids, created_by_ids=created_by_ids,
        status_ids=status_ids, issue_type_ids=issue_type_ids,
        priority_ids=priority_ids, category_ids=category_ids,
        milestone_ids=milestone_ids,
        keyword=keyword or None,
        updated_since=updated_since or None, updated_until=updated_until or None,
        created_since=created_since or None, created_until=created_until or None,
        due_date_since=due_date_since or None, due_date_until=due_date_until or None,
        sort=sort, order=order, max_count=cap,
    )
    return {"total": len(issues), "issues": [api.slim_issue(i) for i in issues]}


@mcp.tool()
def get_issue(issue_key: str, source: str = _D) -> dict:
    """Get full details of a single issue: description, assignee, status, priority, due date, etc.

    Args:
        issue_key: Full issue key, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/issues/{issue_key}")


@mcp.tool()
def get_issues_by_keys(issue_keys: list[str], source: str = _D) -> dict:
    """Fetch multiple issues at once by a list of issue keys — faster than individual calls.
    Issues are fetched in parallel and returned in input order. Max 50 keys.

    Args:
        issue_keys: List of issue keys, e.g. ['KEY-123', 'KEY-456']
        source: Source name from get_sources. Empty = default source.
    """
    keys = list(issue_keys)[:50]

    def _fetch(key):
        try:
            return key, api._get(source, f"/issues/{key}")
        except Exception as e:
            return key, {"issueKey": key, "error": str(e)}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(keys), 10)) as ex:
        for key, data in (f.result() for f in as_completed({ex.submit(_fetch, k): k for k in keys})):
            results[key] = data

    ordered = [results.get(k, {"issueKey": k, "error": "not fetched"}) for k in keys]
    return {
        "total": len(ordered),
        "issues": [api.slim_issue(i) if "error" not in i else i for i in ordered],
    }


@mcp.tool()
def get_parent_issue(issue_key: str, source: str = _D) -> dict:
    """Get the parent issue of a sub-task.
    Returns a clear message if the issue has no parent.

    Args:
        issue_key: Child issue key
        source: Source name from get_sources. Empty = default source.
    """
    issue = api._get(source, f"/issues/{issue_key}")
    parent_id = issue.get("parentIssueId")
    if not parent_id:
        return {"message": f"{issue_key} has no parent issue"}
    return api._get(source, f"/issues/{parent_id}")


@mcp.tool()
def get_child_issues(issue_key: str, source: str = _D) -> list:
    """Get all sub-tasks (child issues) of a parent issue.

    Args:
        issue_key: Parent issue key
        source: Source name from get_sources. Empty = default source.
    """
    all_children, offset, count = [], 0, 100
    while True:
        batch = api._get(source, f"/issues/{issue_key}/childIssues",
                         {"count": count, "offset": offset})
        all_children.extend(batch)
        if len(batch) < count:
            break
        offset += count
    return all_children


@mcp.tool()
def get_issue_count(
    source: str = _D,
    status: str = "all",
    assignee: str = "",
    created_by: str = "",
    keyword: str = "",
    issue_type: str = "",
    priority: str = "",
    category: str = "",
    milestone: str = "",
    updated_since: str = "",
    updated_until: str = "",
    created_since: str = "",
    created_until: str = "",
) -> dict:
    """Count issues matching the given filters — same filter params as get_issues.
    Useful for dashboards and progress tracking.

    Args:
        source: Source name from get_sources. Empty = default source.
        status: 'open', 'in_progress', 'resolved', 'closed', 'all' (comma-separate multiple)
        assignee: Assignee name (partial match). Empty = all.
        created_by: Creator name (partial match). Empty = all.
        keyword: Keyword in title/description. Empty = all.
        issue_type: Issue type name (partial match). Empty = all.
        priority: Priority name (partial match). Empty = all.
        category: Category name (partial match). Empty = all.
        milestone: Milestone name (partial match). Empty = all.
        updated_since: Filter updated from date (YYYY-MM-DD).
        updated_until: Filter updated until date (YYYY-MM-DD).
        created_since: Filter created from date (YYYY-MM-DD).
        created_until: Filter created until date (YYYY-MM-DD).
    """
    project = api.cached_meta(f"project:{source}",
                              lambda: api._get(source, f"/projects/{api.project_key(source)}"))
    status_ids = None
    if status and status != "all":
        ids = [api.STATUS_MAP[s.strip()] for s in status.split(",") if s.strip() in api.STATUS_MAP]
        status_ids = ids or None
    pkey = api.project_key(source)
    assignee_ids   = api.resolve_users(source, assignee)
    created_by_ids = api.resolve_users(source, created_by)
    issue_type_ids = api.resolve_names(source, f"issue_types:{source}", f"/projects/{pkey}/issueTypes", issue_type)
    priority_ids   = api.resolve_names(source, f"priorities:{source}", "/priorities", priority)
    category_ids   = api.resolve_names(source, f"categories:{source}", f"/projects/{pkey}/categories", category)
    milestone_ids  = api.resolve_names(source, f"milestones:{source}", f"/projects/{pkey}/versions", milestone)
    base = {}
    for k, v in [
        ("keyword", keyword or None),
        ("updatedSince", updated_since or None), ("updatedUntil", updated_until or None),
        ("createdSince", created_since or None), ("createdUntil", created_until or None),
    ]:
        if v:
            base[k] = v
    list_p = {"projectId[]": [project["id"]]}
    for k, v in [
        ("assigneeId[]", assignee_ids), ("createdUserId[]", created_by_ids),
        ("statusId[]", status_ids), ("issueTypeId[]", issue_type_ids),
        ("priorityId[]", priority_ids), ("categoryId[]", category_ids),
        ("milestoneId[]", milestone_ids),
    ]:
        if v:
            list_p[k] = v
    result = api._get(source, "/issues/count", base, list_p)
    return {"count": result.get("count", 0)}


# ── Comments ──────────────────────────────────────────────────────────────────

@mcp.tool()
def get_issue_comments(issue_key: str, source: str = _D) -> list:
    """Get all comments of an issue in chronological order (oldest to newest).

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
    """
    return api.fetch_all_comments(source, issue_key)


@mcp.tool()
def get_recent_comments_bulk(
    issue_keys: list[str],
    last_n: int = 3,
    source: str = _D,
) -> dict:
    """Get the N most recent comments for multiple issues at once — parallel fetch.
    Much faster than calling get_issue_comments for each issue individually.

    Args:
        issue_keys: List of issue keys (max 50)
        last_n: Number of most recent comments per issue (default 3, max 10)
        source: Source name from get_sources. Empty = default source.
    """
    keys = list(issue_keys)[:50]
    n = min(int(last_n or 3), 10)

    def _fetch(key):
        try:
            return key, api.fetch_recent_comments(source, key, n)
        except Exception as e:
            return key, {"error": str(e)}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(keys), 10)) as ex:
        for key, data in (f.result() for f in as_completed({ex.submit(_fetch, k): k for k in keys})):
            results[key] = data

    return {"total": len(keys), "comments": {k: results.get(k, []) for k in keys}}


# ── Issues — write ────────────────────────────────────────────────────────────

@mcp.tool()
def create_issue(
    source: str,
    summary: str,
    description: str,
    issue_type_id: int,
    priority_id: int,
    assignee_id: int = 0,
) -> dict:
    """Create a new issue in Backlog.
    ⚠️ CONFIRM WITH USER before calling — show the issue details first.
    Workflow: get_issue_types → get_priorities → confirm → create_issue.

    Args:
        source: Target source from get_sources (required — must be explicit)
        summary: Issue title
        description: Detailed description
        issue_type_id: Issue type ID from get_issue_types
        priority_id: Priority ID from get_priorities
        assignee_id: Assignee user ID from get_project_users. 0 = unassigned.
    """
    project = api.cached_meta(f"project:{source}",
                              lambda: api._get(source, f"/projects/{api.project_key(source)}"))
    data = {
        "projectId":   project["id"],
        "summary":     summary,
        "description": description or "",
        "issueTypeId": issue_type_id,
        "priorityId":  priority_id,
    }
    if assignee_id:
        data["assigneeId"] = assignee_id
    return api._post(source, "/issues", data)


@mcp.tool()
def update_issue(
    issue_key: str,
    source: str = _D,
    summary: str = "",
    description: str = "",
    status_id: int = 0,
    priority_id: int = 0,
    assignee_id: int = 0,
    clear_assignee: bool = False,
    due_date: str = "",
    clear_due_date: bool = False,
    comment: str = "",
) -> dict:
    """Update fields of an existing Backlog issue.
    ⚠️ CONFIRM WITH USER before calling — list which fields will change.
    Only fill fields you want to change — defaults (0/''/False) are NOT modified.

    Args:
        issue_key: Issue key to update, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
        summary: New title. Empty = keep current.
        description: New description. Empty = keep current.
        status_id: New status ID from get_project_statuses. 0 = keep current.
        priority_id: New priority ID from get_priorities. 0 = keep current.
        assignee_id: New assignee ID from get_project_users. 0 = keep current.
        clear_assignee: True to remove the assignee.
        due_date: New due date YYYY-MM-DD. Empty = keep current.
        clear_due_date: True to remove due date.
        comment: Comment to add when updating.
    """
    data: dict = {}
    if summary:
        data["summary"] = summary
    if description:
        data["description"] = description
    if status_id:
        data["statusId"] = status_id
    if priority_id:
        data["priorityId"] = priority_id
    if assignee_id:
        data["assigneeId"] = assignee_id
    elif clear_assignee:
        data["assigneeId"] = ""
    if due_date:
        data["dueDate"] = due_date
    elif clear_due_date:
        data["dueDate"] = ""
    if comment:
        data["comment"] = comment
    return api._patch(source, f"/issues/{issue_key}", data)


@mcp.tool()
def delete_issue(issue_key: str, source: str = _D) -> dict:
    """Delete a Backlog issue permanently.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        issue_key: Issue key to delete, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/issues/{issue_key}")


@mcp.tool()
def bulk_update_issue_status(
    issue_keys: list[str],
    status_id: int,
    source: str = _D,
    comment: str = "",
) -> dict:
    """Update the status of multiple issues at once. Runs updates in parallel.
    ⚠️ CONFIRM WITH USER — list all issues and the new status before calling.

    Args:
        issue_keys: List of issue keys to update (max 50)
        status_id: New status ID from get_project_statuses
        source: Source name from get_sources. Empty = default source.
        comment: Optional comment to add to each issue
    """
    keys = list(issue_keys)[:50]
    data: dict = {"statusId": status_id}
    if comment:
        data["comment"] = comment

    def _upd(key):
        try:
            return key, api._patch(source, f"/issues/{key}", data)
        except Exception as e:
            return key, {"issueKey": key, "error": str(e)}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(keys), 10)) as ex:
        for key, res in (f.result() for f in as_completed({ex.submit(_upd, k): k for k in keys})):
            results[key] = res

    ok     = [k for k in keys if "error" not in results.get(k, {})]
    failed = {k: results[k]["error"] for k in keys if "error" in results.get(k, {})}
    return {"updated": len(ok), "failed": len(failed), "failures": failed}


@mcp.tool()
def get_issue_attachments(issue_key: str, source: str = _D) -> list:
    """List all file attachments of a Backlog issue.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/issues/{issue_key}/attachments")


_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "image/bmp"}
_TEXT_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")


def _decode_attachment(data: bytes, content_type: str):
    """Return attachment content in the most useful form for the AI."""
    mime = content_type.split(";")[0].strip()
    if mime in _IMAGE_MIMES:
        return [mcp_types.ImageContent(
            type="image",
            data=base64.b64encode(data).decode(),
            mimeType=mime,
        )]
    if any(mime.startswith(p) for p in _TEXT_PREFIXES):
        return {"content_type": mime, "text": data.decode("utf-8", errors="replace")}
    return {
        "content_type": mime,
        "size_bytes": len(data),
        "data_base64": base64.b64encode(data).decode(),
    }


@mcp.tool()
def download_issue_attachment(issue_key: str, attachment_id: int, source: str = _D):
    """Download a file attached to a Backlog issue.
    Images are returned inline so the AI can view them directly.
    Text files (csv, json, txt, …) are returned as text.
    Other binary files are returned as base64-encoded data.
    Use get_issue_attachments to list available attachment IDs first.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        attachment_id: Attachment ID from get_issue_attachments
        source: Source name from get_sources. Empty = default source.
    """
    data, ct = api._get_raw(source, f"/issues/{issue_key}/attachments/{attachment_id}")
    return _decode_attachment(data, ct)


@mcp.tool()
def get_wiki_attachments(wiki_id: int, source: str = _D) -> list:
    """List all file attachments of a Backlog wiki page.

    Args:
        wiki_id: Wiki page ID from get_wiki_pages
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/wikis/{wiki_id}/attachments")


@mcp.tool()
def download_wiki_attachment(wiki_id: int, attachment_id: int, source: str = _D):
    """Download a file attached to a Backlog wiki page.
    Same return behaviour as download_issue_attachment.
    Use get_wiki_attachments to list available attachment IDs first.

    Args:
        wiki_id: Wiki page ID from get_wiki_pages
        attachment_id: Attachment ID from get_wiki_attachments
        source: Source name from get_sources. Empty = default source.
    """
    data, ct = api._get_raw(source, f"/wikis/{wiki_id}/attachments/{attachment_id}")
    return _decode_attachment(data, ct)


@mcp.tool()
def add_comment(issue_key: str, content: str, source: str = _D) -> dict:
    """Add a comment to a Backlog issue.
    ⚠️ CONFIRM WITH USER — show comment content before posting.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        content: Comment text (supports Backlog Markdown)
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, f"/issues/{issue_key}/comments", {"content": content})


@mcp.tool()
def add_comment_with_mention(
    issue_key: str,
    content: str,
    mention_user_ids: list[int],
    source: str = _D,
) -> dict:
    """Add a comment that mentions users exactly like typing '@' in the Backlog UI:
    the name renders as a highlighted mention AND the users really get notified
    (bell + email). Use this instead of add_comment whenever someone must be notified —
    a hand-typed '@Name' is plain text: it stays unhighlighted and notifies nobody.
    Mentions are sent as Backlog's mention token '<@U{userId}>' (Backlog expands it back
    to the display name on read). If content already contains a plain '@Display Name' for
    one of the users, it is converted to a token in place so the wording is kept;
    otherwise the mention is prepended on its own line.
    ⚠️ CONFIRM WITH USER — show the comment and who will be notified before posting.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        content: Comment body (Backlog Markdown). Write '@Display Name' where the mention
                 belongs, or omit it — the mention is prepended then.
        mention_user_ids: User IDs to mention and notify, from get_project_users. Required.
        source: Source name from get_sources. Empty = default source.
    """
    ids = [int(u) for u in (mention_user_ids or []) if u]
    if not ids:
        return {"error": "mention_user_ids is required — use add_comment to post without a mention"}

    users = api.cached_meta(f"users:{source}",
                            lambda: api._get(source, f"/projects/{api.project_key(source)}/users"))
    by_id = {u["id"]: u["name"] for u in users}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        return {"error": f"User id(s) not in project: {unknown}",
                "available": [{"id": u["id"], "name": u["name"]} for u in users]}

    body, prepend = content, []
    for i in ids:
        token = f"<@U{i}>"
        if token in body:
            continue
        plain = f"@{by_id[i]}"
        if plain in body:
            body = body.replace(plain, token, 1)
        else:
            prepend.append(token)
    if prepend:
        body = " ".join(prepend) + "\n" + body

    res = api._post(source, f"/issues/{issue_key}/comments",
                    {"content": body, "notifiedUserId[]": ids})
    return {
        "commentId": res.get("id"),
        "notified":  [(n.get("user") or {}).get("name") for n in (res.get("notifications") or [])],
        "content":   res.get("content"),
    }


@mcp.tool()
def update_comment(issue_key: str, comment_id: int, content: str, source: str = _D) -> dict:
    """Edit the text of an existing comment on a Backlog issue.
    ⚠️ CONFIRM WITH USER — show the new content before updating.

    Args:
        issue_key: Issue key containing the comment
        comment_id: Comment ID from get_issue_comments
        content: New comment text
        source: Source name from get_sources. Empty = default source.
    """
    return api._patch(source, f"/issues/{issue_key}/comments/{comment_id}", {"content": content})


@mcp.tool()
def delete_comment(issue_key: str, comment_id: int, source: str = _D) -> dict:
    """Delete a comment from a Backlog issue.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        issue_key: Issue key containing the comment
        comment_id: Comment ID from get_issue_comments
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/issues/{issue_key}/comments/{comment_id}")


# ── Project admin — categories ────────────────────────────────────────────────

@mcp.tool()
def add_category(name: str, source: str = _D) -> dict:
    """Add a new category to the project.

    Args:
        name: Category name
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, f"/projects/{api.project_key(source)}/categories", {"name": name})


@mcp.tool()
def update_category(category_id: int, name: str, source: str = _D) -> dict:
    """Rename an existing category.

    Args:
        category_id: Category ID from get_categories
        name: New category name
        source: Source name from get_sources. Empty = default source.
    """
    return api._patch(source, f"/projects/{api.project_key(source)}/categories/{category_id}", {"name": name})


@mcp.tool()
def delete_category(category_id: int, source: str = _D) -> dict:
    """Delete a category from the project.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        category_id: Category ID from get_categories
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/projects/{api.project_key(source)}/categories/{category_id}")


# ── Project admin — issue types ───────────────────────────────────────────────

@mcp.tool()
def add_issue_type(name: str, color: str = "#e30000", source: str = _D) -> dict:
    """Add a new issue type to the project.

    Args:
        name: Issue type name
        color: Display color hex. Allowed: #e30000 #990000 #934981 #814fbc
               #2779c4 #007e9a #7ea800 #ff9200 #ff3265 #666665
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, f"/projects/{api.project_key(source)}/issueTypes",
                     {"name": name, "color": color})


@mcp.tool()
def update_issue_type(issue_type_id: int, name: str = "", color: str = "", source: str = _D) -> dict:
    """Update an issue type's name or color.

    Args:
        issue_type_id: Issue type ID from get_issue_types
        name: New name. Empty = keep current.
        color: New color hex. Empty = keep current.
        source: Source name from get_sources. Empty = default source.
    """
    data: dict = {}
    if name:
        data["name"] = name
    if color:
        data["color"] = color
    return api._patch(source, f"/projects/{api.project_key(source)}/issueTypes/{issue_type_id}", data)


@mcp.tool()
def delete_issue_type(issue_type_id: int, substitute_issue_type_id: int, source: str = _D) -> dict:
    """Delete an issue type. All existing issues of this type are migrated to the substitute type.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        issue_type_id: Issue type ID to delete (from get_issue_types)
        substitute_issue_type_id: ID of the issue type to migrate existing issues to
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source,
                       f"/projects/{api.project_key(source)}/issueTypes/{issue_type_id}",
                       {"substituteIssueTypeId": substitute_issue_type_id})


# ── Project admin — milestones ────────────────────────────────────────────────

@mcp.tool()
def add_milestone(
    name: str,
    description: str = "",
    start_date: str = "",
    release_due_date: str = "",
    source: str = _D,
) -> dict:
    """Add a new milestone/version to the project.

    Args:
        name: Milestone name
        description: Milestone description
        start_date: Start date (YYYY-MM-DD)
        release_due_date: Release due date (YYYY-MM-DD)
        source: Source name from get_sources. Empty = default source.
    """
    data: dict = {"name": name}
    if description:
        data["description"] = description
    if start_date:
        data["startDate"] = start_date
    if release_due_date:
        data["releaseDueDate"] = release_due_date
    return api._post(source, f"/projects/{api.project_key(source)}/versions", data)


@mcp.tool()
def update_milestone(
    milestone_id: int,
    name: str = "",
    description: str = "",
    start_date: str = "",
    release_due_date: str = "",
    archived: bool = False,
    source: str = _D,
) -> dict:
    """Update a milestone/version.

    Args:
        milestone_id: Milestone ID from get_milestones
        name: New name. Empty = keep current.
        description: New description. Empty = keep current.
        start_date: New start date YYYY-MM-DD. Empty = keep current.
        release_due_date: New release due date YYYY-MM-DD. Empty = keep current.
        archived: Set True to archive this milestone.
        source: Source name from get_sources. Empty = default source.
    """
    data: dict = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if start_date:
        data["startDate"] = start_date
    if release_due_date:
        data["releaseDueDate"] = release_due_date
    if archived:
        data["archived"] = "true"
    return api._patch(source, f"/projects/{api.project_key(source)}/versions/{milestone_id}", data)


@mcp.tool()
def delete_milestone(milestone_id: int, source: str = _D) -> dict:
    """Delete a milestone/version from the project.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        milestone_id: Milestone ID from get_milestones
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/projects/{api.project_key(source)}/versions/{milestone_id}")


# ── Project admin — custom fields ─────────────────────────────────────────────

@mcp.tool()
def get_custom_fields(source: str = _D) -> list:
    """Get all custom fields defined in the project.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/projects/{api.project_key(source)}/customFields")


@mcp.tool()
def add_custom_field(
    name: str,
    field_type_id: int,
    description: str = "",
    required: bool = False,
    source: str = _D,
) -> dict:
    """Add a new custom field to the project.

    Args:
        name: Field name
        field_type_id: 1=Text 2=TextArea 3=Numeric 4=Date 5=SingleList 6=MultipleList 7=CheckBox 8=Radio
        description: Field description
        required: Whether this field is required on issue creation
        source: Source name from get_sources. Empty = default source.
    """
    data: dict = {"typeId": field_type_id, "name": name}
    if description:
        data["description"] = description
    if required:
        data["required"] = "true"
    return api._post(source, f"/projects/{api.project_key(source)}/customFields", data)


@mcp.tool()
def update_custom_field(
    custom_field_id: int,
    name: str = "",
    description: str = "",
    required: bool = False,
    source: str = _D,
) -> dict:
    """Update a custom field's name, description, or required flag.

    Args:
        custom_field_id: Custom field ID from get_custom_fields
        name: New name. Empty = keep current.
        description: New description. Empty = keep current.
        required: Set True to make this field required.
        source: Source name from get_sources. Empty = default source.
    """
    data: dict = {}
    if name:
        data["name"] = name
    if description:
        data["description"] = description
    if required:
        data["required"] = "true"
    return api._patch(source, f"/projects/{api.project_key(source)}/customFields/{custom_field_id}", data)


@mcp.tool()
def delete_custom_field(custom_field_id: int, source: str = _D) -> dict:
    """Delete a custom field from the project. All data in this field will be lost.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        custom_field_id: Custom field ID from get_custom_fields
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/projects/{api.project_key(source)}/customFields/{custom_field_id}")


# ── Wiki ──────────────────────────────────────────────────────────────────────

@mcp.tool()
def get_wiki_pages(source: str = _D, keyword: str = "") -> list:
    """List all wiki pages in the project. Returns slim summary (no full content).
    Use get_wiki_page to read full content of a specific page.

    Args:
        source: Source name from get_sources. Empty = default source.
        keyword: Search keyword in page names. Empty = all.
    """
    params: dict = {"projectIdOrKey": api.project_key(source)}
    if keyword:
        params["keyword"] = keyword
    pages = api._get(source, "/wikis", params)
    return [api.slim_wiki(p) for p in pages]


@mcp.tool()
def get_wiki_count(source: str = _D) -> dict:
    """Get the total number of wiki pages in the project.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    result = api._get(source, "/wikis/count", {"projectIdOrKey": api.project_key(source)})
    return {"count": result.get("count", 0)}


@mcp.tool()
def get_wiki_page(wiki_id: int, source: str = _D) -> dict:
    """Get full content of a wiki page by its ID.
    Use get_wiki_pages to find the wiki ID first.

    Args:
        wiki_id: Wiki page ID from get_wiki_pages
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/wikis/{wiki_id}")


@mcp.tool()
def create_wiki_page(
    name: str,
    content: str,
    source: str = _D,
    mail_notify: bool = False,
) -> dict:
    """Create a new wiki page in the project.
    ⚠️ CONFIRM WITH USER — show page name and content summary first.

    Args:
        name: Wiki page name/title
        content: Page content (supports Backlog Markdown)
        source: Source name from get_sources. Empty = default source.
        mail_notify: Send email notification to project members
    """
    project = api.cached_meta(f"project:{source}",
                              lambda: api._get(source, f"/projects/{api.project_key(source)}"))
    return api._post(source, "/wikis", {
        "projectId":  project["id"],
        "name":       name,
        "content":    content,
        "mailNotify": "true" if mail_notify else "false",
    })


@mcp.tool()
def update_wiki_page(
    wiki_id: int,
    name: str = "",
    content: str = "",
    source: str = _D,
    mail_notify: bool = False,
) -> dict:
    """Update an existing wiki page's name or content.
    ⚠️ CONFIRM WITH USER before calling.

    Args:
        wiki_id: Wiki page ID from get_wiki_pages
        name: New page name. Empty = keep current.
        content: New page content. Empty = keep current.
        source: Source name from get_sources. Empty = default source.
        mail_notify: Send email notification to project members
    """
    data: dict = {"mailNotify": "true" if mail_notify else "false"}
    if name:
        data["name"] = name
    if content:
        data["content"] = content
    return api._patch(source, f"/wikis/{wiki_id}", data)


@mcp.tool()
def delete_wiki_page(wiki_id: int, source: str = _D, mail_notify: bool = False) -> dict:
    """Delete a wiki page permanently.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        wiki_id: Wiki page ID from get_wiki_pages
        source: Source name from get_sources. Empty = default source.
        mail_notify: Send email notification to project members
    """
    return api._delete(source, f"/wikis/{wiki_id}", {"mailNotify": "true" if mail_notify else "false"})


# ── Activity ──────────────────────────────────────────────────────────────────

@mcp.tool()
def get_space_activities(
    source: str = _D,
    activity_type: str = "",
    count: int = 20,
    order: str = "desc",
    min_id: int = 0,
    max_id: int = 0,
) -> list:
    """Get recent activity feed across all projects in the Backlog space.

    Args:
        source: Source name from get_sources. Empty = default source.
        activity_type: Comma-separated type IDs to filter.
            1=IssueCreated 2=IssueUpdated 3=IssueCommented 4=IssueDeleted
            5=WikiCreated 6=WikiUpdated 7=WikiDeleted 12=GitPushed
            14=IssueBulkUpdated 18=PullRequestAdded 19=PullRequestUpdated
        count: Number of activities (default 20, max 100)
        order: 'desc' (newest first, default) or 'asc'
        min_id: Return activities with ID >= this value
        max_id: Return activities with ID <= this value
    """
    params: dict = {"count": min(count, 100), "order": order}
    if min_id:
        params["minId"] = min_id
    if max_id:
        params["maxId"] = max_id
    list_p = {}
    if activity_type:
        type_ids = [int(t.strip()) for t in activity_type.split(",") if t.strip().isdigit()]
        if type_ids:
            list_p["activityTypeId[]"] = type_ids
    activities = api._get(source, "/space/activities", params, list_p or None)
    return [api.slim_activity(a) for a in activities]


@mcp.tool()
def get_project_activities(
    source: str = _D,
    activity_type: str = "",
    count: int = 20,
    order: str = "desc",
) -> list:
    """Get recent activity feed for a specific project.

    Args:
        source: Source name from get_sources. Empty = default source.
        activity_type: Comma-separated type IDs (same codes as get_space_activities)
        count: Number of activities (default 20, max 100)
        order: 'desc' (newest first, default) or 'asc'
    """
    params: dict = {"count": min(count, 100), "order": order}
    list_p = {}
    if activity_type:
        type_ids = [int(t.strip()) for t in activity_type.split(",") if t.strip().isdigit()]
        if type_ids:
            list_p["activityTypeId[]"] = type_ids
    activities = api._get(source, f"/projects/{api.project_key(source)}/activities",
                          params, list_p or None)
    return [api.slim_activity(a) for a in activities]


@mcp.tool()
def get_recently_viewed_issues(source: str = _D, count: int = 20) -> list:
    """Get the authenticated user's recently viewed issues.

    Args:
        source: Source name from get_sources. Empty = default source.
        count: Number of items (default 20, max 100)
    """
    items = api._get(source, "/users/myself/recentlyViewedIssues",
                     {"count": min(count, 100), "order": "desc"})
    return [api.slim_issue(item.get("issue", {})) for item in items]


@mcp.tool()
def get_recently_viewed_wikis(source: str = _D, count: int = 20) -> list:
    """Get the authenticated user's recently viewed wiki pages.

    Args:
        source: Source name from get_sources. Empty = default source.
        count: Number of items (default 20, max 100)
    """
    items = api._get(source, "/users/myself/recentlyViewedWikis",
                     {"count": min(count, 100), "order": "desc"})
    return [api.slim_wiki(item.get("page", {})) for item in items]


# ── Notifications ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_notifications(
    source: str = _D,
    already_read: bool = False,
    count: int = 20,
    order: str = "desc",
) -> list:
    """Get notifications for the authenticated user.

    Args:
        source: Source name from get_sources. Empty = default source.
        already_read: False (default) = unread only. True = already-read only.
        count: Number of notifications (default 20, max 100)
        order: 'desc' (newest first, default) or 'asc'
    """
    params = {
        "count":       min(count, 100),
        "order":       order,
        "alreadyRead": "true" if already_read else "false",
    }
    notifications = api._get(source, "/notifications", params)
    return [api.slim_notification(n) for n in notifications]


@mcp.tool()
def get_notification_count(source: str = _D, already_read: bool = False) -> dict:
    """Get notification count for the authenticated user.

    Args:
        source: Source name from get_sources. Empty = default source.
        already_read: False (default) = count unread. True = count already-read.
    """
    result = api._get(source, "/notifications/count",
                      {"alreadyRead": "true" if already_read else "false",
                       "resourceAlreadyRead": "true" if already_read else "false"})
    return {"count": result.get("count", 0)}


@mcp.tool()
def mark_notification_read(notification_id: int, source: str = _D) -> dict:
    """Mark a specific notification as read.

    Args:
        notification_id: Notification ID from get_notifications
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, f"/notifications/{notification_id}/markAsRead", {})


@mcp.tool()
def reset_notification_count(source: str = _D) -> dict:
    """Mark ALL notifications as read (resets unread count to 0).

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, "/notifications/markAsRead", {})


# ── Watchers ──────────────────────────────────────────────────────────────────

@mcp.tool()
def get_issue_watchers(issue_key: str, source: str = _D) -> list:
    """Get all users watching an issue.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, f"/issues/{issue_key}/watchers")


@mcp.tool()
def add_issue_watcher(issue_key: str, user_id: int, source: str = _D) -> dict:
    """Add a user as a watcher to an issue.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'
        user_id: User ID from get_project_users
        source: Source name from get_sources. Empty = default source.
    """
    return api._post(source, f"/issues/{issue_key}/watchers", {"userId": user_id})


@mcp.tool()
def delete_issue_watcher(issue_key: str, user_id: int, source: str = _D) -> dict:
    """Remove a user from the watchers of an issue.

    Args:
        issue_key: Issue key
        user_id: User ID to remove from watchers (from get_issue_watchers)
        source: Source name from get_sources. Empty = default source.
    """
    return api._delete(source, f"/issues/{issue_key}/watchers/{user_id}")


# ── Stars ─────────────────────────────────────────────────────────────────────

@mcp.tool()
def add_star(
    source: str = _D,
    issue_id: int = 0,
    comment_id: int = 0,
    wiki_page_id: int = 0,
) -> dict:
    """Add a star (like) to an issue, comment, or wiki page.
    Provide exactly one of: issue_id, comment_id, or wiki_page_id.

    Args:
        source: Source name from get_sources. Empty = default source.
        issue_id: Issue ID (numeric, not key like 'PROJECT-123') to star
        comment_id: Comment ID to star
        wiki_page_id: Wiki page ID to star
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
    return api._post(source, "/stars", data)


# ── Space / User ──────────────────────────────────────────────────────────────

@mcp.tool()
def get_projects(source: str = _D, archived: bool = False) -> list:
    """List all Backlog projects accessible with the current API key.

    Args:
        source: Source name from get_sources. Empty = default source.
        archived: True = include archived projects. Default = active only.
    """
    params: dict = {}
    if archived:
        params["archived"] = "true"
    return api._get(source, "/projects", params or None)


@mcp.tool()
def get_my_info(source: str = _D) -> dict:
    """Get the authenticated user's profile: id, name, email, role, etc.

    Args:
        source: Source name from get_sources. Empty = default source.
    """
    return api._get(source, "/users/myself")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
