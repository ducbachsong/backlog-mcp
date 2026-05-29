"""Backlog MCP Server — exposes Backlog project management tools for Claude Desktop."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Optional

from mcp.server.fastmcp import FastMCP

import backlog_api as api

mcp = FastMCP(
    "Backlog Tools",
    instructions=(
        "You have access to Backlog project management tools. "
        "Source 'yst' = YST customer Backlog. Source 'vti' = VTI internal Backlog. "
        "Always confirm with the user before calling create_issue, update_issue, add_comment, or delete_comment."
    ),
)


# ── Project metadata ──────────────────────────────────────────────────────────

@mcp.tool()
def get_project(source: str = "yst") -> dict:
    """Get Backlog project info (id, name, projectKey).

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}")


@mcp.tool()
def get_project_statuses(source: str = "yst") -> list:
    """Get all valid ticket statuses for the project (Open, In Progress, Resolved, Closed, ...).

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}/statuses")


@mcp.tool()
def get_project_users(source: str = "yst") -> list:
    """Get all members of the Backlog project with their id and name.

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}/users")


@mcp.tool()
def get_issue_types(source: str = "yst") -> list:
    """Get all issue types (Bug, Task, Feature, ...) with their ids.
    Call this before create_issue to get valid issue_type_id values.

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}/issueTypes")


@mcp.tool()
def get_categories(source: str = "yst") -> list:
    """Get all categories of the project with their ids.

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}/categories")


@mcp.tool()
def get_milestones(source: str = "yst") -> list:
    """Get all milestones/sprints of the project with ids and dates.

    Args:
        source: Project to query — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/projects/{api.project_key(source)}/versions")


@mcp.tool()
def get_priorities() -> list:
    """Get all priority levels (Normal, High, Low, ...) with their ids."""
    return api._get("yst", "/priorities")


# ── Issues — read ─────────────────────────────────────────────────────────────

@mcp.tool()
def get_issues(
    source: str = "yst",
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
        source: Project — 'yst' (default) or 'vti'
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

    assignee_ids    = api.resolve_users(source, assignee)
    created_by_ids  = api.resolve_users(source, created_by)

    pkey = api.project_key(source)
    issue_type_ids  = api.resolve_names(source, f"issue_types:{source}", f"/projects/{pkey}/issueTypes", issue_type)
    priority_ids    = api.resolve_names("yst", "priorities", "/priorities", priority)
    category_ids    = api.resolve_names(source, f"categories:{source}", f"/projects/{pkey}/categories", category)
    milestone_ids   = api.resolve_names(source, f"milestones:{source}", f"/projects/{pkey}/versions", milestone)

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
def get_issue(issue_key: str, source: str = "yst") -> dict:
    """Get full details of a single issue: description, assignee, status, priority, due date, etc.

    Args:
        issue_key: Full issue key, e.g. 'KANTAKIWIZKEIZOKUKAIHATSU-123'
        source: Project containing the issue — 'yst' (default) or 'vti'
    """
    return api._get(source, f"/issues/{issue_key}")


@mcp.tool()
def get_issues_by_keys(issue_keys: list[str], source: str = "yst") -> dict:
    """Fetch multiple issues at once by a list of issue keys — faster than individual calls.
    Issues are fetched in parallel and returned in input order. Max 50 keys.

    Args:
        issue_keys: List of issue keys, e.g. ['KEY-123', 'KEY-456']
        source: Project — 'yst' (default) or 'vti'
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
def get_parent_issue(issue_key: str, source: str = "yst") -> dict:
    """Get the parent issue of a sub-task.
    Returns a clear message if the issue has no parent.

    Args:
        issue_key: Child issue key
        source: Project — 'yst' (default) or 'vti'
    """
    issue = api._get(source, f"/issues/{issue_key}")
    parent_id = issue.get("parentIssueId")
    if not parent_id:
        return {"message": f"{issue_key} has no parent issue"}
    return api._get(source, f"/issues/{parent_id}")


@mcp.tool()
def get_child_issues(issue_key: str, source: str = "yst") -> list:
    """Get all sub-tasks (child issues) of a parent issue.

    Args:
        issue_key: Parent issue key
        source: Project — 'yst' (default) or 'vti'
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


# ── Comments ──────────────────────────────────────────────────────────────────

@mcp.tool()
def get_issue_comments(issue_key: str, source: str = "yst") -> list:
    """Get all comments of an issue in chronological order (oldest to newest).

    Args:
        issue_key: Issue key, e.g. 'KANTAKIWIZKEIZOKUKAIHATSU-123'
        source: Project — 'yst' (default) or 'vti'
    """
    return api.fetch_all_comments(source, issue_key)


@mcp.tool()
def get_recent_comments_bulk(
    issue_keys: list[str],
    last_n: int = 3,
    source: str = "yst",
) -> dict:
    """Get the N most recent comments for multiple issues at once — parallel fetch.
    Much faster than calling get_issue_comments for each issue individually.
    Useful for weekly reports, sprint reviews, or any bulk status check.

    Args:
        issue_keys: List of issue keys (max 50)
        last_n: Number of most recent comments per issue (default 3, max 10)
        source: Project — 'yst' (default) or 'vti'
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
        source: Target project — 'yst' or 'vti' (required)
        summary: Issue title
        description: Detailed description
        issue_type_id: Issue type ID from get_issue_types
        priority_id: Priority ID from get_priorities
        assignee_id: Assignee user ID from get_project_users. 0 = unassigned.
    """
    project = api.cached_meta(f"project:{source}",
                              lambda: api._get(source, f"/projects/{api.project_key(source)}"))
    data = {
        "projectId": project["id"],
        "summary": summary,
        "description": description or "",
        "issueTypeId": issue_type_id,
        "priorityId": priority_id,
    }
    if assignee_id:
        data["assigneeId"] = assignee_id
    return api._post(source, "/issues", data)


@mcp.tool()
def update_issue(
    issue_key: str,
    source: str = "yst",
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
        issue_key: Issue key to update, e.g. 'KANTAKIWIZKEIZOKUKAIHATSU-123'
        source: Project — 'yst' (default) or 'vti'
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
def add_comment(issue_key: str, content: str, source: str = "yst") -> dict:
    """Add a comment to a Backlog issue.
    ⚠️ CONFIRM WITH USER — show comment content before posting.

    Args:
        issue_key: Issue key, e.g. 'KANTAKIWIZKEIZOKUKAIHATSU-123'
        content: Comment text (supports Backlog Markdown)
        source: Project — 'yst' (default) or 'vti'
    """
    return api._post(source, f"/issues/{issue_key}/comments", {"content": content})


@mcp.tool()
def delete_comment(issue_key: str, comment_id: int, source: str = "yst") -> dict:
    """Delete a comment from a Backlog issue.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        issue_key: Issue key containing the comment
        comment_id: Comment ID from get_issue_comments
        source: Project — 'yst' (default) or 'vti'
    """
    return api._delete(source, f"/issues/{issue_key}/comments/{comment_id}")


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    mcp.run()


if __name__ == "__main__":
    main()
