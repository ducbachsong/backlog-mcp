"""Backlog HTTP helpers — internal module, not exposed as MCP tools."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config

# ── Base URLs / API keys ──────────────────────────────────────────────────────

_BASE_URLS = {
    "yst": config.BACKLOG_BASE_URL_YST,
    "vti": config.BACKLOG_BASE_URL_VTI,
}
_API_KEYS = {
    "yst": config.BACKLOG_API_KEY_YST,
    "vti": config.BACKLOG_API_KEY_VTI,
}
_PROJECT_KEYS = {
    "yst": config.PROJECT_KEY_YST,
    "vti": config.PROJECT_KEY_VTI,
}


# ── HTTP helpers ──────────────────────────────────────────────────────────────

def _request(method: str, url: str, **kwargs) -> requests.Response:
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except requests.exceptions.Timeout:
            if attempt == 2:
                raise
            time.sleep(1)
    raise RuntimeError(f"Max retries exceeded for {url}")


def _get(source: str, endpoint: str, params: dict = None, list_params: dict = None) -> any:
    key = _API_KEYS.get(source)
    if not key:
        raise ValueError(f"API key not configured for source '{source}'")
    p = list((params or {}).items()) + [("apiKey", key)]
    for k, vals in (list_params or {}).items():
        for v in (vals if isinstance(vals, list) else [vals]):
            p.append((k, v))
    return _request("GET", f"{_BASE_URLS[source]}{endpoint}", params=p).json()


def _post(source: str, endpoint: str, data: dict = None, files=None, extra_params: list = None) -> any:
    p = (extra_params or []) + [("apiKey", _API_KEYS[source])]
    return _request("POST", f"{_BASE_URLS[source]}{endpoint}", params=p, data=data, files=files).json()


def _patch(source: str, endpoint: str, data: dict = None, extra_params: list = None) -> any:
    p = (extra_params or []) + [("apiKey", _API_KEYS[source])]
    return _request("PATCH", f"{_BASE_URLS[source]}{endpoint}", params=p, data=data).json()


def _delete(source: str, endpoint: str) -> any:
    return _request("DELETE", f"{_BASE_URLS[source]}{endpoint}",
                    params=[("apiKey", _API_KEYS[source])]).json()


def project_key(source: str) -> str:
    return _PROJECT_KEYS.get(source, "")


# ── Session metadata cache ────────────────────────────────────────────────────

_meta_cache: dict = {}


def cached_meta(key: str, fetch_fn):
    if key not in _meta_cache:
        _meta_cache[key] = fetch_fn()
    return _meta_cache[key]


# ── Slim helpers ──────────────────────────────────────────────────────────────

def slim_issue(issue: dict) -> dict:
    return {
        "issueKey":       issue.get("issueKey"),
        "summary":        issue.get("summary"),
        "status":         (issue.get("status") or {}).get("name"),
        "issueType":      (issue.get("issueType") or {}).get("name"),
        "priority":       (issue.get("priority") or {}).get("name"),
        "assignee":       (issue.get("assignee") or {}).get("name"),
        "createdUser":    (issue.get("createdUser") or {}).get("name"),
        "category":       [c.get("name") for c in (issue.get("category") or [])],
        "milestone":      [m.get("name") for m in (issue.get("milestone") or [])],
        "created":        issue.get("created"),
        "updated":        issue.get("updated"),
        "startDate":      issue.get("startDate"),
        "dueDate":        issue.get("dueDate"),
        "estimatedHours": issue.get("estimatedHours"),
        "actualHours":    issue.get("actualHours"),
    }


def slim_comment(c: dict) -> dict:
    return {
        "id":      c.get("id"),
        "author":  (c.get("createdUser") or {}).get("name", ""),
        "created": (c.get("created") or "")[:16],
        "content": (c.get("content") or "")[:300],
    }


# ── Paginated issue fetch ─────────────────────────────────────────────────────

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
        batch = _get(source, "/issues", base, list_p)
        all_issues.extend(batch)
        if len(batch) < count:
            break
        offset += count
    return all_issues


def resolve_users(source: str, name: str) -> list | None:
    if not name:
        return None
    users = cached_meta(f"users:{source}", lambda: _get(source, f"/projects/{project_key(source)}/users"))
    matched = [u for u in users if name.lower() in u["name"].lower()]
    return [str(u["id"]) for u in matched] if matched else ["-1"]


def resolve_names(source: str, cache_key: str, endpoint: str, name: str) -> list | None:
    if not name:
        return None
    items = cached_meta(cache_key, lambda: _get(source, endpoint))
    matched = [i for i in items if name.lower() in i.get("name", "").lower()]
    return [str(i["id"]) for i in matched] if matched else ["-1"]


def fetch_recent_comments(source: str, key: str, n: int) -> list:
    batch = _get(source, f"/issues/{key}/comments", {"count": n, "order": "desc"})
    return [slim_comment(c) for c in batch]


def fetch_all_comments(source: str, key: str) -> list:
    all_comments, min_id = [], None
    while True:
        base = {"count": 100, "order": "asc"}
        if min_id is not None:
            base["minId"] = min_id
        batch = _get(source, f"/issues/{key}/comments", base)
        all_comments.extend(batch)
        if len(batch) < 100:
            break
        min_id = batch[-1]["id"] + 1
    return all_comments
