"""Paginated issue and comment fetching.

Backlog caps every list endpoint at 100 rows, so these helpers page until the
filter is exhausted or a caller-supplied cap is reached.
"""

from .http import get
from .slim import slim_comment


STATUS_MAP = {"open": 1, "in_progress": 2, "resolved": 3, "closed": 4}


def fetch_issues_raw(
    source: str, project_id: int,
    assignee_ids=None, created_by_ids=None,
    status_ids=None, issue_type_ids=None, priority_ids=None,
    category_ids=None, milestone_ids=None, parent_issue_ids=None,
    keyword=None, updated_since=None, updated_until=None,
    created_since=None, created_until=None,
    due_date_since=None, due_date_until=None,
    sort="updated", order="desc", max_count=None,
) -> list:
    """Fetch issues page by page until the filters are exhausted or max_count is hit.

    Input:
        source: Source name. Empty = default source.
        project_id: Numeric project id to search inside.
        *_ids: Optional id lists for the corresponding filters (None = no filter).
        keyword: Free-text search over title and description.
        *_since / *_until: YYYY-MM-DD range bounds.
        sort: Sort field ('updated', 'created', 'priority', 'status', 'dueDate').
        order: 'desc' or 'asc'.
        max_count: Stop after this many issues. None = fetch everything.
    Output:
        List of raw issue dicts (not slimmed).
    """
    all_issues, offset, count = [], 0, 100
    while True:
        if max_count is not None:
            remaining = max_count - len(all_issues)
            if remaining <= 0:
                break
            count = min(100, remaining)
        base = {"count": count, "offset": offset, "sort": sort, "order": order}
        for k, v in [
            ("keyword", keyword), ("updatedSince", updated_since), ("updatedUntil", updated_until),
            ("createdSince", created_since), ("createdUntil", created_until),
            ("dueDateSince", due_date_since), ("dueDateUntil", due_date_until),
        ]:
            if v:
                base[k] = v
        list_p = {"projectId[]": [project_id]}
        for k, v in [
            ("assigneeId[]", assignee_ids), ("createdUserId[]", created_by_ids),
            ("statusId[]", status_ids), ("issueTypeId[]", issue_type_ids),
            ("priorityId[]", priority_ids), ("categoryId[]", category_ids),
            ("milestoneId[]", milestone_ids), ("parentIssueId[]", parent_issue_ids),
        ]:
            if v:
                list_p[k] = v
        batch = get(source, "/issues", base, list_p)
        all_issues.extend(batch)
        if len(batch) < count:
            break
        offset += count
    return all_issues


def fetch_recent_comments(source: str, key: str, n: int) -> list:
    """Fetch the N newest comments of one issue.

    Input:
        source: Source name. Empty = default source.
        key: Issue key, e.g. 'PROJECT-123'.
        n: How many comments to return, newest first.
    Output:
        List of slimmed comment dicts (see slim_comment).
    """
    batch = get(source, f"/issues/{key}/comments", {"count": n, "order": "desc"})
    return [slim_comment(c) for c in batch]


def fetch_all_comments(source: str, key: str) -> list:
    """Fetch every comment of one issue, oldest first, paging through the API.

    Input:
        source: Source name. Empty = default source.
        key: Issue key, e.g. 'PROJECT-123'.
    Output:
        List of raw comment dicts in chronological order.
    """
    all_comments, min_id = [], None
    while True:
        base = {"count": 100, "order": "asc"}
        if min_id is not None:
            base["minId"] = min_id
        batch = get(source, f"/issues/{key}/comments", base)
        all_comments.extend(batch)
        if len(batch) < 100:
            break
        min_id = batch[-1]["id"] + 1
    return all_comments
