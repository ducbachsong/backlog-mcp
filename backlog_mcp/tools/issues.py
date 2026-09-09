"""Tools: reading, creating, updating and deleting issues.

`update_issues` is the single write path for every ticket field — see
`..fields.build_issue_fields` for why they are all sent in one request.
"""

from typing import Optional

from ..app import mcp
from .. import api
from ..common import D
from ..common import KEEP, normalize_keys
from ..fields import build_issue_fields, apply_mentions, issue_filter_ids


@mcp.tool()
def get_issues(
    source: str = D,
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
    count_only: bool = False,
) -> dict:
    """Search and list Backlog issues with filters. Main tool for listing/filtering tickets.
    Set count_only=True to get just the number of matches (dashboards, progress checks).

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
        limit: Max issues to return (default 20, max 100). Ignored when count_only=True.
        count_only: True = return only the match count, skipping issue bodies.

    Returns:
        dict: {'count': int} when count_only=True, otherwise
              {'total': int, 'issues': [slim issue dicts]} where each issue holds
              issueKey, summary, status, issueType, priority, resolution, assignee,
              category, milestone, version, dates and hours.
    """
    pid = api.project_id(source)
    f = issue_filter_ids(source, status, assignee, created_by,
                          issue_type, priority, category, milestone)

    if count_only:
        base = {}
        for k, v in [("keyword", keyword), ("updatedSince", updated_since),
                     ("updatedUntil", updated_until), ("createdSince", created_since),
                     ("createdUntil", created_until), ("dueDateSince", due_date_since),
                     ("dueDateUntil", due_date_until)]:
            if v:
                base[k] = v
        list_p = {"projectId[]": [pid]}
        for param, key in [("assigneeId[]", "assignee_ids"), ("createdUserId[]", "created_by_ids"),
                           ("statusId[]", "status_ids"), ("issueTypeId[]", "issue_type_ids"),
                           ("priorityId[]", "priority_ids"), ("categoryId[]", "category_ids"),
                           ("milestoneId[]", "milestone_ids")]:
            if f[key]:
                list_p[param] = f[key]
        return {"count": api.get(source, "/issues/count", base, list_p).get("count", 0)}

    issues = api.fetch_issues_raw(
        source, pid,
        keyword=keyword or None,
        updated_since=updated_since or None, updated_until=updated_until or None,
        created_since=created_since or None, created_until=created_until or None,
        due_date_since=due_date_since or None, due_date_until=due_date_until or None,
        sort=sort, order=order, max_count=min(max(1, limit), 100), **f,
    )
    return {"total": len(issues), "issues": [api.slim_issue(i) for i in issues]}


@mcp.tool()
def get_issue(issue_keys: list[str], source: str = D, full: bool = True) -> dict:
    """Get one or many issues by key. Multiple keys are fetched in parallel and
    returned in input order — always prefer one call with N keys over N calls.

    Args:
        issue_keys: Issue keys, e.g. ['PROJECT-123'] or ['KEY-1', 'KEY-2']. Max 50.
        source: Source name from get_sources. Empty = default source.
        full: True (default) = complete issue records including description and
              custom fields. False = slim records (same shape as get_issues).

    Returns:
        dict: {'total': int, 'issues': [...]} in the order the keys were given.
        A key that failed appears as {'issueKey': key, 'error': message} instead
        of an issue, so one bad key never fails the batch.
    """
    keys = normalize_keys(issue_keys)
    if not keys:
        return {"total": 0, "issues": [], "error": "issue_keys is required"}

    results = api.run_parallel(keys, lambda k: api.get(source, f"/issues/{k}"))
    out = []
    for k in keys:
        issue = results.get(k, {"error": "not fetched"})
        if isinstance(issue, dict) and "error" in issue and "issueKey" not in issue:
            out.append({"issueKey": k, "error": issue["error"]})
        else:
            out.append(issue if full else api.slim_issue(issue))
    return {"total": len(out), "issues": out}


@mcp.tool()
def get_related_issues(issue_key: str, source: str = D, relation: str = "children") -> dict:
    """Walk the parent/child (sub-task) relationship of an issue.

    Args:
        issue_key: Issue key to start from, e.g. 'PROJECT-123'.
        source: Source name from get_sources. Empty = default source.
        relation: 'children' (default) = its sub-tasks, 'parent' = its parent
                  issue, 'both' = both directions in one call.

    Returns:
        dict: {'parent': issue dict or None, 'children': [issue dicts]} — only the
        requested directions are present. 'parent' is None when the issue is not
        a sub-task, and 'children' is [] when it has no sub-tasks.
    """
    out: dict = {}

    if relation in ("parent", "both"):
        issue = api.get(source, f"/issues/{issue_key}")
        parent_id = issue.get("parentIssueId")
        out["parent"] = api.get(source, f"/issues/{parent_id}") if parent_id else None

    if relation in ("children", "both"):
        children, offset = [], 0
        while True:
            batch = api.get(source, f"/issues/{issue_key}/childIssues",
                             {"count": 100, "offset": offset})
            children.extend(batch)
            if len(batch) < 100:
                break
            offset += 100
        out["children"] = children

    if not out:
        return {"error": f"Unknown relation '{relation}'. Use 'children', 'parent' or 'both'."}
    return out


@mcp.tool()
def create_issue(
    source: str,
    summary: str,
    description: str = "",
    issue_type: str = "",
    priority: str = "Normal",
    assignee: str = "",
    milestone: str = "",
    category: str = "",
    version: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours: float = KEEP,
    actual_hours: float = KEEP,
    parent_issue_id: int = 0,
    mention_user_ids: Optional[list[int]] = None,
) -> dict:
    """Create a new issue, setting every field in one request.
    ⚠️ CONFIRM WITH USER before calling — show the issue details first.
    Workflow: get_project_metadata → confirm → create_issue.

    Args:
        source: Target source from get_sources (required — must be explicit).
        summary: Issue title (required).
        description: Detailed description (Backlog Markdown).
        issue_type: 種別 — name or id from get_project_metadata (kinds='issue_types').
                    Required by Backlog; empty falls back to the project's first type.
        priority: 優先度 — name or id, default 'Normal'.
        assignee: 担当者 — member name or user id. Empty = unassigned.
        milestone: マイルストーン — name(s) or id(s), comma-separated for several.
        category: カテゴリー — name(s) or id(s), comma-separated.
        version: 発生バージョン — name(s) or id(s), comma-separated.
        start_date: 開始日 (YYYY-MM-DD).
        due_date: 期限日 (YYYY-MM-DD).
        estimated_hours: 予定時間 in hours. Omit to leave unset.
        actual_hours: 実績時間 in hours. Omit to leave unset.
        parent_issue_id: Numeric id of the parent issue to file this under as a sub-task.
        mention_user_ids: User ids to notify about the new issue (bell + email).

    Returns:
        dict: the created issue as returned by Backlog (id, issueKey, summary, ...),
        or {'error': message, ...} when a field name could not be resolved.
    """
    try:
        data = build_issue_fields(
            source, summary=summary, description=description, issue_type=issue_type,
            priority=priority, assignee=assignee, milestone=milestone, category=category,
            version=version, start_date=start_date, due_date=due_date,
            estimated_hours=estimated_hours, actual_hours=actual_hours,
            parent_issue_id=parent_issue_id,
        )
    except ValueError as e:
        return {"error": str(e)}

    data["projectId"] = api.project_id(source)
    data.setdefault("description", "")
    if "issueTypeId" not in data:
        types = api.meta(source, "issue_types")
        if not types:
            return {"error": "Project has no issue types configured"}
        data["issueTypeId"] = types[0]["id"]
    if "priorityId" not in data:
        data["priorityId"] = api.resolve_field_id(source, "priority", "Normal")

    ids = [int(u) for u in (mention_user_ids or []) if u]
    if ids:
        data["notifiedUserId[]"] = ids
    return api.post(source, "/issues", data)


@mcp.tool()
def update_issues(
    issue_keys: list[str],
    source: str = D,
    summary: str = "",
    description: str = "",
    status: str = "",
    assignee: str = "",
    priority: str = "",
    issue_type: str = "",
    resolution: str = "",
    milestone: str = "",
    category: str = "",
    version: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours: float = KEEP,
    actual_hours: float = KEEP,
    parent_issue_id: int = 0,
    comment: str = "",
    mention_user_ids: Optional[list[int]] = None,
    clear_fields: str = "",
) -> dict:
    """Update any combination of ticket fields on one or many issues — the single
    write tool for 状態 / 担当者 / 優先度 / マイルストーン / カテゴリー / 発生バージョン /
    開始日 / 期限日 / 予定時間 / 実績時間 / 完了理由, plus an optional comment and mention.

    Everything you pass is sent in ONE request per issue, so the Backlog change
    history (課題の変更履歴) gets a single entry. Do not call this repeatedly to
    change one field at a time.
    ⚠️ CONFIRM WITH USER before calling — list which issues and fields change.
    Fields left at their default ('' / -1 / 0) are NOT modified.

    Args:
        issue_keys: Issue key or list of keys, e.g. ['PROJECT-123']. Max 50 —
                    several keys are updated in parallel with the same values.
        source: Source name from get_sources. Empty = default source.
        summary: New title.
        description: New description (replaces the whole body).
        status: 状態 — name or id, e.g. 'Closed' / '4'.
        assignee: 担当者 — member name or user id.
        priority: 優先度 — name or id, e.g. 'High'.
        issue_type: 種別 — name or id.
        resolution: 完了理由 — name or id, e.g. 'Fixed'. Usually set together with
                    status='Closed'.
        milestone: マイルストーン — name(s) or id(s), comma-separated to set several.
        category: カテゴリー — name(s) or id(s), comma-separated.
        version: 発生バージョン — name(s) or id(s), comma-separated.
        start_date: 開始日 (YYYY-MM-DD).
        due_date: 期限日 (YYYY-MM-DD).
        estimated_hours: 予定時間 in hours (0 is a valid value; omit to keep current).
        actual_hours: 実績時間 in hours (0 is a valid value; omit to keep current).
        parent_issue_id: Numeric id of a new parent issue.
        comment: Comment posted as part of this same update.
        mention_user_ids: User ids to mention and notify (bell + email), from
                          get_project_metadata (kinds='users'). The mention is
                          rendered as a real Backlog mention inside `comment`:
                          write '@Display Name' where it belongs, or omit it and
                          the mention is prepended.
        clear_fields: Comma-separated fields to blank out instead of setting:
                      assignee, resolution, start_date, due_date, estimated_hours,
                      actual_hours, category, milestone, version.

    Returns:
        dict: {'updated': int, 'failed': int, 'fields': [changed Backlog params],
               'notified': [user names] (only when mention_user_ids was used),
               'issues': [slim issue dicts for the successes],
               'failures': {issue key: error message}}.
    """
    keys = normalize_keys(issue_keys)
    if not keys:
        return {"error": "issue_keys is required"}

    try:
        data = build_issue_fields(
            source, summary=summary, description=description, status=status,
            assignee=assignee, priority=priority, issue_type=issue_type,
            resolution=resolution, milestone=milestone, category=category,
            version=version, start_date=start_date, due_date=due_date,
            estimated_hours=estimated_hours, actual_hours=actual_hours,
            parent_issue_id=parent_issue_id, clear_fields=clear_fields,
        )
    except ValueError as e:
        return {"error": str(e)}

    body, ids, err = apply_mentions(source, comment, mention_user_ids)
    if err:
        return err
    if body:
        data["comment"] = body
    if ids:
        data["notifiedUserId[]"] = ids

    if not data:
        return {"error": "Nothing to update — pass at least one field, a comment, or clear_fields"}

    results = api.run_parallel(keys, lambda k: api.patch(source, f"/issues/{k}", data))
    ok      = [k for k in keys if "error" not in (results.get(k) or {"error": "not run"})]
    failed  = {k: results[k]["error"] for k in keys
               if isinstance(results.get(k), dict) and "error" in results[k]}

    out = {
        "updated":  len(ok),
        "failed":   len(failed),
        "fields":   [k for k in data if k not in ("comment", "notifiedUserId[]")],
        "issues":   [api.slim_issue(results[k]) for k in ok],
        "failures": failed,
    }
    if ids:
        users = api.meta(source, "users")
        by_id = {u["id"]: u["name"] for u in users}
        out["notified"] = [by_id.get(i, i) for i in ids]
    return out


@mcp.tool()
def delete_issue(issue_keys: list[str], source: str = D) -> dict:
    """Delete one or more Backlog issues permanently.
    ⚠️ IRREVERSIBLE — confirm with user before calling.

    Args:
        issue_keys: Issue key or list of keys to delete, e.g. ['PROJECT-123']. Max 50.
        source: Source name from get_sources. Empty = default source.

    Returns:
        dict: {'deleted': int, 'failed': int, 'failures': {issue key: error message}}.
    """
    keys = normalize_keys(issue_keys)
    if not keys:
        return {"error": "issue_keys is required"}
    results = api.run_parallel(keys, lambda k: api.delete(source, f"/issues/{k}"))
    failed = {k: results[k]["error"] for k in keys
              if isinstance(results.get(k), dict) and "error" in results[k]}
    return {"deleted": len(keys) - len(failed), "failed": len(failed), "failures": failed}
