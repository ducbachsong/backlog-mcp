"""Project metadata: the lookup lists, their cache, and name -> id resolution.

Ticket fields are addressed by display name or numeric id interchangeably
throughout the server; this module is what makes that work.
"""

from typing import Any

from .http import get
from .sources import project_key


_meta_cache: dict = {}


def cached_meta(key: str, fetch_fn):
    """Memoise a metadata fetch for the lifetime of the server process.

    Input:
        key: Cache key, e.g. 'users:main'.
        fetch_fn: Zero-arg callable performing the actual fetch on a cache miss.
    Output:
        The cached value (fresh on first call, cached afterwards).
    """
    if key not in _meta_cache:
        _meta_cache[key] = fetch_fn()
    return _meta_cache[key]


def clear_meta_cache() -> None:
    """Drop every cached metadata entry.

    Call after mutating project settings (categories, milestones, issue types)
    so later name→id lookups see the change.

    Input:  none.
    Output: None.
    """
    _meta_cache.clear()


META_ENDPOINTS = {
    "project":       lambda s: f"/projects/{project_key(s)}",
    "statuses":      lambda s: f"/projects/{project_key(s)}/statuses",
    "users":         lambda s: f"/projects/{project_key(s)}/users",
    "issue_types":   lambda s: f"/projects/{project_key(s)}/issueTypes",
    "categories":    lambda s: f"/projects/{project_key(s)}/categories",
    "milestones":    lambda s: f"/projects/{project_key(s)}/versions",
    "versions":      lambda s: f"/projects/{project_key(s)}/versions",
    "priorities":    lambda s: "/priorities",
    "resolutions":   lambda s: "/resolutions",
    "custom_fields": lambda s: f"/projects/{project_key(s)}/customFields",
}


FIELD_META = {
    "status":     "statuses",     # 状態
    "assignee":   "users",        # 担当者
    "priority":   "priorities",   # 優先度
    "milestone":  "milestones",   # マイルストーン
    "category":   "categories",   # カテゴリー
    "version":    "versions",     # 発生バージョン
    "resolution": "resolutions",  # 完了理由
    "issue_type": "issue_types",  # 種別
}


def meta(source: str, kind: str) -> Any:
    """Fetch (and cache) one kind of project metadata.

    Input:
        source: Source name. Empty = default source.
        kind: Key of META_ENDPOINTS, e.g. 'statuses', 'users', 'milestones'.
    Output:
        The endpoint's JSON — a list of {id, name, ...} for every kind except
        'project', which returns a single dict.
    Raises:
        ValueError for an unknown kind.
    """
    if kind not in META_ENDPOINTS:
        raise ValueError(f"Unknown metadata kind '{kind}'. Valid: {list(META_ENDPOINTS)}")
    return cached_meta(f"{kind}:{source}", lambda: get(source, META_ENDPOINTS[kind](source)))


def project_id(source: str) -> int:
    """Return the numeric project id of a source's project.

    Input:  source: Source name. Empty = default source.
    Output: project id as int.
    """
    return meta(source, "project")["id"]


def resolve_field_id(source: str, field: str, value: str) -> int:
    """Resolve one ticket-field value (name or numeric id) to its Backlog id.

    Matching is exact-name-first, then case-insensitive substring, so both
    'Closed' and 'clos' resolve. A purely numeric value is trusted as an id.

    Input:
        source: Source name. Empty = default source.
        field: Key of FIELD_META, e.g. 'status', 'assignee', 'milestone'.
        value: Display name or numeric id as a string.
    Output:
        The matching id as int.
    Raises:
        ValueError listing the available names when nothing matches.
    """
    val = str(value).strip()
    if val.isdigit():
        return int(val)
    if field not in FIELD_META:
        raise ValueError(f"Unknown field '{field}'. Valid: {list(FIELD_META)}")
    options = meta(source, FIELD_META[field])
    low = val.lower()
    exact = [o for o in options if (o.get("name") or "").lower() == low]
    hits = exact or [o for o in options if low in (o.get("name") or "").lower()]
    if not hits:
        raise ValueError(
            f"No {field} matching '{val}'. Available: {[o.get('name') for o in options]}"
        )
    return int(hits[0]["id"])


def resolve_field_ids(source: str, field: str, value: str) -> list[int]:
    """Resolve a comma-separated list of names/ids for a multi-value field.

    Used by カテゴリー (category), マイルストーン (milestone) and
    発生バージョン (version), which Backlog accepts as repeated params.

    Input:
        source: Source name. Empty = default source.
        field: Key of FIELD_META.
        value: Comma-separated names or ids, e.g. 'Sprint 1, Sprint 2'.
    Output:
        List of ids, in input order. Empty list when value is blank.
    """
    parts = [p.strip() for p in str(value).split(",") if p.strip()]
    return [resolve_field_id(source, field, p) for p in parts]


def resolve_users(source: str, name: str) -> list | None:
    """Resolve a partial user name to project member ids, for search filters.

    Input:
        source: Source name. Empty = default source.
        name: Partial display name, case-insensitive. Empty = no filter.
    Output:
        None when name is empty (meaning "do not filter"),
        list of matching id strings otherwise,
        ['-1'] when nothing matches so the search returns no rows instead of all.
    """
    if not name:
        return None
    users = meta(source, "users")
    matched = [u for u in users if name.lower() in u["name"].lower()]
    return [str(u["id"]) for u in matched] if matched else ["-1"]


def resolve_names(source: str, kind: str, name: str) -> list | None:
    """Resolve a partial name to metadata ids, for search filters.

    Input:
        source: Source name. Empty = default source.
        kind: Metadata kind, e.g. 'issue_types', 'priorities', 'categories'.
        name: Partial name, case-insensitive. Empty = no filter.
    Output:
        None when name is empty, list of matching id strings otherwise,
        ['-1'] when nothing matches (search then returns no rows).
    """
    if not name:
        return None
    items = meta(source, kind)
    matched = [i for i in items if name.lower() in (i.get("name") or "").lower()]
    return [str(i["id"]) for i in matched] if matched else ["-1"]
