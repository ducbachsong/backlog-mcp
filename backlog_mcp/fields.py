"""Turning human-friendly ticket field values into Backlog form bodies.

This is the heart of the "one request per change" behaviour: `build_issue_fields`
collects every field the caller supplied into a single dict, so `update_issues`
and `add_comment` can send one PATCH and have Backlog record one entry in the
issue history instead of one per field.
"""

from typing import Optional

from . import api
from .common import KEEP


CLEARABLE = {
    "assignee":        ("assigneeId", ""),        # 担当者
    "resolution":      ("resolutionId", ""),      # 完了理由
    "start_date":      ("startDate", ""),         # 開始日
    "due_date":        ("dueDate", ""),           # 期限日
    "estimated_hours": ("estimatedHours", ""),    # 予定時間
    "actual_hours":    ("actualHours", ""),       # 実績時間
    "category":        ("categoryId[]", [""]),    # カテゴリー
    "milestone":       ("milestoneId[]", [""]),   # マイルストーン
    "version":         ("versionId[]", [""]),     # 発生バージョン
}


def build_issue_fields(
    source: str,
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
    clear_fields: str = "",
) -> dict:
    """Translate human-friendly ticket field values into a Backlog form body.

    Names are resolved to ids via api.resolve_field_id, so callers may
    pass either. Blank / sentinel arguments are omitted from the result, which is
    what makes a single PATCH able to carry "only what changed".

    Input:
        source: Source name. Empty = default source.
        summary..parent_issue_id: Field values; '' or KEEP means "leave alone".
        clear_fields: Comma-separated names from CLEARABLE to blank out.
    Output:
        dict of Backlog form params, ready for _post / _patch. Empty when nothing
        was supplied.
    Raises:
        ValueError when a name cannot be resolved (message lists valid names).
    """
    data: dict = {}

    if summary:
        data["summary"] = summary
    if description:
        data["description"] = description
    if start_date:
        data["startDate"] = start_date
    if due_date:
        data["dueDate"] = due_date
    if estimated_hours != KEEP:
        data["estimatedHours"] = estimated_hours
    if actual_hours != KEEP:
        data["actualHours"] = actual_hours
    if parent_issue_id:
        data["parentIssueId"] = parent_issue_id

    # Single-value fields resolved by name or id.
    for value, field, param in [
        (status,     "status",     "statusId"),
        (assignee,   "assignee",   "assigneeId"),
        (priority,   "priority",   "priorityId"),
        (issue_type, "issue_type", "issueTypeId"),
        (resolution, "resolution", "resolutionId"),
    ]:
        if value:
            data[param] = api.resolve_field_id(source, field, value)

    # Multi-value fields — Backlog expects repeated params.
    for value, field, param in [
        (milestone, "milestone", "milestoneId[]"),
        (category,  "category",  "categoryId[]"),
        (version,   "version",   "versionId[]"),
    ]:
        if value:
            data[param] = api.resolve_field_ids(source, field, value)

    # Explicit clears win over "unchanged", but never over an explicit new value.
    for name in [c.strip() for c in (clear_fields or "").split(",") if c.strip()]:
        if name not in CLEARABLE:
            raise ValueError(f"Cannot clear '{name}'. Clearable: {list(CLEARABLE)}")
        param, blank = CLEARABLE[name]
        if param not in data:
            data[param] = blank

    return data


def apply_mentions(source: str, content: str, mention_user_ids) -> tuple[str, list[int], Optional[dict]]:
    """Rewrite a comment body so the named users are really mentioned and notified.

    Backlog renders '<@U{userId}>' as a highlighted mention; a hand-typed
    '@Name' is plain text and notifies nobody. If the body already contains
    '@Display Name' for a user, it is replaced in place so the wording survives;
    otherwise the mention tokens are prepended on their own line.

    Input:
        source: Source name. Empty = default source.
        content: Comment body as written by the caller.
        mention_user_ids: User ids to mention. None/empty = no mention.
    Output:
        (body, ids, error) — `error` is None on success, otherwise a dict to
        return straight to the caller and `body`/`ids` are meaningless.
    """
    ids = [int(u) for u in (mention_user_ids or []) if u]
    if not ids:
        return content, [], None

    users = api.meta(source, "users")
    by_id = {u["id"]: u["name"] for u in users}
    unknown = [i for i in ids if i not in by_id]
    if unknown:
        return content, ids, {
            "error": f"User id(s) not in project: {unknown}",
            "available": [{"id": u["id"], "name": u["name"]} for u in users],
        }

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
        body = " ".join(prepend) + "\n" + body if body else " ".join(prepend)
    return body, ids, None


def issue_filter_ids(source: str, status: str, assignee: str, created_by: str,
                      issue_type: str, priority: str, category: str, milestone: str) -> dict:
    """Resolve the shared get_issues / count filter names into id lists.

    Input:
        source: Source name. Empty = default source.
        status: Comma-separated keys of api.STATUS_MAP, or 'all'.
        assignee..milestone: Partial names; empty means "no filter".
    Output:
        dict of filter name → list of id strings (or None for "no filter"),
        keyed as status_ids, assignee_ids, created_by_ids, issue_type_ids,
        priority_ids, category_ids, milestone_ids.
    """
    status_ids = None
    if status and status != "all":
        ids = [api.STATUS_MAP[s.strip()] for s in status.split(",") if s.strip() in api.STATUS_MAP]
        status_ids = ids or None
    return {
        "status_ids":     status_ids,
        "assignee_ids":   api.resolve_users(source, assignee),
        "created_by_ids": api.resolve_users(source, created_by),
        "issue_type_ids": api.resolve_names(source, "issue_types", issue_type),
        "priority_ids":   api.resolve_names(source, "priorities", priority),
        "category_ids":   api.resolve_names(source, "categories", category),
        "milestone_ids":  api.resolve_names(source, "milestones", milestone),
    }
