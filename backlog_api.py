"""Backlog HTTP helpers — internal module, not exposed as MCP tools."""

import time
from concurrent.futures import ThreadPoolExecutor, as_completed

import requests

import config


# ── Source resolution ─────────────────────────────────────────────────────────

def _src(source: str) -> dict:
    """Resolve source name → config dict. Empty string uses DEFAULT_SOURCE."""
    name = (source or "").strip() or config.DEFAULT_SOURCE
    cfg = config.SOURCES.get(name)
    if not cfg:
        available = list(config.SOURCES.keys())
        raise ValueError(f"Source '{name}' not configured. Available: {available}")
    return cfg


def available_sources() -> list[str]:
    return list(config.SOURCES.keys())


def project_key(source: str) -> str:
    return _src(source)["project_key"]


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
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            if attempt == 2:
                raise
            time.sleep(1)
    raise RuntimeError(f"Max retries exceeded for {url}")


def _get(source: str, endpoint: str, params: dict = None, list_params: dict = None) -> any:
    cfg = _src(source)
    p = list((params or {}).items()) + [("apiKey", cfg["api_key"])]
    for k, vals in (list_params or {}).items():
        for v in (vals if isinstance(vals, list) else [vals]):
            p.append((k, v))
    return _request("GET", f"{cfg['base_url']}{endpoint}", params=p).json()


def _post(source: str, endpoint: str, data: dict = None, files=None, extra_params: list = None) -> any:
    cfg = _src(source)
    p = (extra_params or []) + [("apiKey", cfg["api_key"])]
    return _request("POST", f"{cfg['base_url']}{endpoint}", params=p, data=data, files=files).json()


def _patch(source: str, endpoint: str, data: dict = None, extra_params: list = None) -> any:
    cfg = _src(source)
    p = (extra_params or []) + [("apiKey", cfg["api_key"])]
    return _request("PATCH", f"{cfg['base_url']}{endpoint}", params=p, data=data).json()


def _delete(source: str, endpoint: str, params: dict = None) -> any:
    cfg = _src(source)
    p = list((params or {}).items()) + [("apiKey", cfg["api_key"])]
    return _request("DELETE", f"{cfg['base_url']}{endpoint}", params=p).json()


def _get_raw(source: str, endpoint: str) -> tuple[bytes, str]:
    """Download binary content without JSON parsing. Returns (bytes, content_type)."""
    cfg = _src(source)
    r = _request("GET", f"{cfg['base_url']}{endpoint}", params=[("apiKey", cfg["api_key"])])
    return r.content, r.headers.get("Content-Type", "application/octet-stream")


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


def slim_wiki(w: dict) -> dict:
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
