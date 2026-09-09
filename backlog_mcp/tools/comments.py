"""Tools: reading and posting issue comments.

`add_comment` can carry field changes and a real Backlog mention in the same
request as the comment itself.
"""

from typing import Optional

from ..app import mcp
from .. import api
from ..common import D
from ..common import KEEP, normalize_keys
from ..fields import build_issue_fields, apply_mentions


@mcp.tool()
def get_comments(issue_keys: list[str], source: str = D, last_n: int = 0) -> dict:
    """Read comments of one or many issues. Several issues are fetched in parallel.

    Args:
        issue_keys: Issue key or list of keys, e.g. ['PROJECT-123']. Max 50.
        source: Source name from get_sources. Empty = default source.
        last_n: 0 (default) = every comment, oldest first, with full bodies.
                N > 0 = only the N newest comments per issue, slimmed
                (id / author / created / body truncated to 300 chars).

    Returns:
        dict: {'total': number of issues, 'comments': {issue key: [comments]}}.
        A failed key maps to {'error': message}.
    """
    keys = normalize_keys(issue_keys)
    if not keys:
        return {"total": 0, "comments": {}, "error": "issue_keys is required"}

    if last_n and last_n > 0:
        n = min(int(last_n), 100)
        fetch = lambda k: api.fetch_recent_comments(source, k, n)
    else:
        fetch = lambda k: api.fetch_all_comments(source, k)

    results = api.run_parallel(keys, fetch)
    return {"total": len(keys), "comments": {k: results.get(k, []) for k in keys}}


@mcp.tool()
def add_comment(
    issue_key: str,
    content: str,
    source: str = D,
    mention_user_ids: Optional[list[int]] = None,
    status: str = "",
    assignee: str = "",
    priority: str = "",
    resolution: str = "",
    milestone: str = "",
    category: str = "",
    version: str = "",
    start_date: str = "",
    due_date: str = "",
    estimated_hours: float = KEEP,
    actual_hours: float = KEEP,
    clear_fields: str = "",
) -> dict:
    """Post a comment on an issue, optionally mentioning users AND changing ticket
    fields in the very same request.

    Mentions: pass mention_user_ids and the users are really notified (bell +
    email) with a highlighted mention, exactly like typing '@' in the Backlog UI.
    A hand-typed '@Name' alone is plain text and notifies nobody.

    Fields: any of 状態 / 担当者 / 優先度 / マイルストーン / カテゴリー / 発生バージョン /
    開始日 / 期限日 / 予定時間 / 実績時間 / 完了理由 given here are applied together with
    the comment in one PATCH, so 課題の変更履歴 records a single entry instead of one
    per field. With no field arguments this is a plain comment POST.
    ⚠️ CONFIRM WITH USER — show the comment, the field changes and who gets notified.

    Args:
        issue_key: Issue key, e.g. 'PROJECT-123'.
        content: Comment body (Backlog Markdown). Write '@Display Name' where a
                 mention belongs, or omit it — mentions are prepended then.
        source: Source name from get_sources. Empty = default source.
        mention_user_ids: User ids to mention and notify, from
                          get_project_metadata (kinds='users'). Empty = notify nobody.
        status: 状態 — name or id.
        assignee: 担当者 — member name or user id.
        priority: 優先度 — name or id.
        resolution: 完了理由 — name or id.
        milestone: マイルストーン — name(s) or id(s), comma-separated.
        category: カテゴリー — name(s) or id(s), comma-separated.
        version: 発生バージョン — name(s) or id(s), comma-separated.
        start_date: 開始日 (YYYY-MM-DD).
        due_date: 期限日 (YYYY-MM-DD).
        estimated_hours: 予定時間 in hours.
        actual_hours: 実績時間 in hours.
        clear_fields: Comma-separated fields to blank out — see update_issues.

    Returns:
        dict: {'issueKey', 'commentId', 'content': the posted body,
               'notified': [user names], 'fieldsChanged': [Backlog params]}.
        'commentId' is null when field changes were included, because Backlog's
        update endpoint returns the issue rather than the new comment — read it
        back with get_comments if you need the id.
        Returns {'error': ...} if a name cannot be resolved or a mentioned user
        is not a project member (the error then lists the valid members).
    """
    if not content and not mention_user_ids:
        return {"error": "content is required"}

    try:
        fields = build_issue_fields(
            source, status=status, assignee=assignee, priority=priority,
            resolution=resolution, milestone=milestone, category=category,
            version=version, start_date=start_date, due_date=due_date,
            estimated_hours=estimated_hours, actual_hours=actual_hours,
            clear_fields=clear_fields,
        )
    except ValueError as e:
        return {"error": str(e)}

    body, ids, err = apply_mentions(source, content, mention_user_ids)
    if err:
        return err

    if fields:
        # One PATCH carries the comment, the mention and every field change.
        data = dict(fields, comment=body)
        if ids:
            data["notifiedUserId[]"] = ids
        res = api.patch(source, f"/issues/{issue_key}", data)
        posted = (res.get("comment") or {}) if isinstance(res.get("comment"), dict) else {}
        comment_id = posted.get("id")
    else:
        data = {"content": body}
        if ids:
            data["notifiedUserId[]"] = ids
        res = api.post(source, f"/issues/{issue_key}/comments", data)
        comment_id = res.get("id")

    by_id = {u["id"]: u["name"] for u in api.meta(source, "users")} if ids else {}
    return {
        "issueKey":      issue_key,
        "commentId":     comment_id,
        "content":       body,
        "notified":      [by_id.get(i, i) for i in ids],
        "fieldsChanged": list(fields.keys()),
    }


@mcp.tool()
def manage_comment(issue_key: str, comment_id: int, action: str, content: str = "", source: str = D) -> dict:
    """Edit or delete an existing comment on an issue.
    ⚠️ CONFIRM WITH USER — deleting a comment is IRREVERSIBLE.

    Args:
        issue_key: Issue key containing the comment, e.g. 'PROJECT-123'.
        comment_id: Comment id from get_comments.
        action: 'update' to replace the text, 'delete' to remove the comment.
        content: New comment text. Required for action='update', ignored otherwise.
        source: Source name from get_sources. Empty = default source.

    Returns:
        dict: the updated or deleted comment as returned by Backlog,
        or {'error': message} for an unknown action or missing content.
    """
    if action == "update":
        if not content:
            return {"error": "content is required for action='update'"}
        return api.patch(source, f"/issues/{issue_key}/comments/{comment_id}", {"content": content})
    if action == "delete":
        return api.delete(source, f"/issues/{issue_key}/comments/{comment_id}")
    return {"error": f"Unknown action '{action}'. Use 'update' or 'delete'."}
