"""Reduce verbose Backlog payloads to the fields worth putting in the model's context.

Backlog returns deeply nested objects; these helpers flatten them, collapsing
nested records to their names and truncating free text.
"""


def slim_issue(issue: dict) -> dict:
    """Reduce a full Backlog issue to the fields worth showing in a list.

    Input:  issue: Raw issue dict from the Backlog API.
    Output: Flat dict — nested objects collapsed to their names, lists to name lists.
    """
    return {
        "issueKey":       issue.get("issueKey"),
        "summary":        issue.get("summary"),
        "status":         (issue.get("status") or {}).get("name"),
        "issueType":      (issue.get("issueType") or {}).get("name"),
        "priority":       (issue.get("priority") or {}).get("name"),
        "resolution":     (issue.get("resolution") or {}).get("name"),
        "assignee":       (issue.get("assignee") or {}).get("name"),
        "createdUser":    (issue.get("createdUser") or {}).get("name"),
        "category":       [c.get("name") for c in (issue.get("category") or [])],
        "milestone":      [m.get("name") for m in (issue.get("milestone") or [])],
        "version":        [v.get("name") for v in (issue.get("versions") or [])],
        "parentIssueId":  issue.get("parentIssueId"),
        "created":        issue.get("created"),
        "updated":        issue.get("updated"),
        "startDate":      issue.get("startDate"),
        "dueDate":        issue.get("dueDate"),
        "estimatedHours": issue.get("estimatedHours"),
        "actualHours":    issue.get("actualHours"),
    }


def slim_comment(c: dict) -> dict:
    """Reduce a comment to id / author / timestamp / truncated body.

    Input:  c: Raw comment dict from the Backlog API.
    Output: Flat dict; content truncated to 300 characters.
    """
    return {
        "id":      c.get("id"),
        "author":  (c.get("createdUser") or {}).get("name", ""),
        "created": (c.get("created") or "")[:16],
        "content": (c.get("content") or "")[:300],
    }


def slim_wiki(w: dict) -> dict:
    """Reduce a wiki page to a listing entry.

    Input:  w: Raw wiki page dict from the Backlog API.
    Output: Flat dict; content truncated to 500 characters.
    """
    content = w.get("content") or ""
    return {
        "id":          w.get("id"),
        "name":        w.get("name"),
        "tags":        [t.get("name") for t in (w.get("tags") or [])],
        "content":     content[:500] if content else "",
        "createdUser": (w.get("createdUser") or {}).get("name"),
        "created":     w.get("created"),
        "updated":     w.get("updated"),
    }


def slim_activity(a: dict) -> dict:
    """Reduce an activity-feed entry to a one-line summary.

    Input:  a: Raw activity dict from the Backlog API.
    Output: Flat dict; summary truncated to 100 characters.
    """
    content = a.get("content") or {}
    summary = content.get("summary") or content.get("key_id") or ""
    return {
        "id":          a.get("id"),
        "type":        a.get("type"),
        "project":     (a.get("project") or {}).get("projectKey", ""),
        "summary":     str(summary)[:100],
        "createdUser": (a.get("createdUser") or {}).get("name", ""),
        "created":     a.get("created"),
    }


def slim_notification(n: dict) -> dict:
    """Reduce a notification to id / read flag / reason / originating issue.

    Input:  n: Raw notification dict from the Backlog API.
    Output: Flat dict.
    """
    issue = n.get("issue") or {}
    return {
        "id":           n.get("id"),
        "alreadyRead":  n.get("alreadyRead"),
        "reason":       n.get("reason"),
        "issueKey":     issue.get("issueKey", ""),
        "issueSummary": issue.get("summary", ""),
        "sender":       (n.get("sender") or {}).get("name", ""),
        "created":      n.get("created"),
    }
