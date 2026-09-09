"""Tools: activity feeds, notifications, and recently viewed items.

Everything here answers "what happened recently", from the space feed down to
the current user's own reading history.
"""

from typing import Any

from ..app import mcp
from .. import api
from ..common import D


@mcp.tool()
def get_activities(
    source: str = D,
    scope: str = "project",
    activity_type: str = "",
    count: int = 20,
    order: str = "desc",
    min_id: int = 0,
    max_id: int = 0,
) -> list:
    """Get the recent activity feed — who changed what, and when.

    Args:
        source: Source name from get_sources. Empty = default source.
        scope: 'project' (default) = this source's project only,
               'space' = every project in the Backlog space.
        activity_type: Comma-separated type ids to filter.
            1=IssueCreated 2=IssueUpdated 3=IssueCommented 4=IssueDeleted
            5=WikiCreated 6=WikiUpdated 7=WikiDeleted 12=GitPushed
            14=IssueBulkUpdated 18=PullRequestAdded 19=PullRequestUpdated
            Empty = all types.
        count: Number of activities (default 20, max 100).
        order: 'desc' (newest first, default) or 'asc'.
        min_id: Only activities with id >= this value. scope='space' only.
        max_id: Only activities with id <= this value. scope='space' only.

    Returns:
        list: slim activity dicts — {'id', 'type', 'project', 'summary',
        'createdUser', 'created'}, summary truncated to 100 characters.
    """
    params: dict = {"count": min(max(1, count), 100), "order": order}
    if min_id:
        params["minId"] = min_id
    if max_id:
        params["maxId"] = max_id

    list_p = {}
    if activity_type:
        type_ids = [int(t.strip()) for t in activity_type.split(",") if t.strip().isdigit()]
        if type_ids:
            list_p["activityTypeId[]"] = type_ids

    endpoint = ("/space/activities" if scope == "space"
                else f"/projects/{api.project_key(source)}/activities")
    return [api.slim_activity(a) for a in api.get(source, endpoint, params, list_p or None)]


@mcp.tool()
def get_recently_viewed(source: str = D, kind: str = "issues", count: int = 20) -> list:
    """Get what the authenticated user looked at most recently — handy for
    "the ticket I was just on" without knowing its key.

    Args:
        source: Source name from get_sources. Empty = default source.
        kind: 'issues' (default) or 'wikis'.
        count: Number of items (default 20, max 100).

    Returns:
        list: slim issue dicts (kind='issues') or slim wiki dicts (kind='wikis'),
        newest first.
    """
    n = min(max(1, count), 100)
    if kind == "wikis":
        items = api.get(source, "/users/myself/recentlyViewedWikis", {"count": n, "order": "desc"})
        return [api.slim_wiki(i.get("page", {})) for i in items]
    items = api.get(source, "/users/myself/recentlyViewedIssues", {"count": n, "order": "desc"})
    return [api.slim_issue(i.get("issue", {})) for i in items]


@mcp.tool()
def get_notifications(
    source: str = D,
    already_read: bool = False,
    count: int = 20,
    order: str = "desc",
    count_only: bool = False,
) -> Any:
    """Get the authenticated user's Backlog notifications, or just their count.

    Args:
        source: Source name from get_sources. Empty = default source.
        already_read: False (default) = unread only. True = already-read only.
        count: Number of notifications (default 20, max 100). Ignored when count_only=True.
        order: 'desc' (newest first, default) or 'asc'.
        count_only: True = return only how many notifications match.

    Returns:
        {'count': int} when count_only=True; otherwise a list of slim
        notification dicts — {'id', 'alreadyRead', 'reason', 'issueKey',
        'issueSummary', 'sender', 'created'}.
    """
    flag = "true" if already_read else "false"
    if count_only:
        result = api.get(source, "/notifications/count",
                          {"alreadyRead": flag, "resourceAlreadyRead": flag})
        return {"count": result.get("count", 0)}
    params = {"count": min(max(1, count), 100), "order": order, "alreadyRead": flag}
    return [api.slim_notification(n) for n in api.get(source, "/notifications", params)]


@mcp.tool()
def mark_notifications_read(source: str = D, notification_id: int = 0) -> dict:
    """Mark one notification — or every notification — as read.

    Args:
        source: Source name from get_sources. Empty = default source.
        notification_id: Id from get_notifications. 0 (default) marks ALL
                         notifications read and resets the unread counter to 0.

    Returns:
        dict: Backlog's response for the marked notification, or the reset result
        when notification_id=0.
    """
    if notification_id:
        return api.post(source, f"/notifications/{notification_id}/markAsRead", {})
    return api.post(source, "/notifications/markAsRead", {})
