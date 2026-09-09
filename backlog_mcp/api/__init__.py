"""Backlog HTTP layer — everything below the MCP tool definitions.

Split by concern:
    secrets  — API-key redaction (see the module docstring; this is security-critical)
    sources  — source name -> configured space
    http     — the retrying request path every call goes through
    meta     — project lookup lists, caching, name -> id resolution
    slim     — payload trimming
    issues   — paginated issue / comment fetching
    parallel — fan-out for multi-key tools

Re-exported here so tool modules can just say `from .. import api` and reach
everything as `api.<name>`.
"""

from .secrets import scrub_secrets, scrubbed_error
from .sources import available_sources, project_key, source_config
from .http import get, post, patch, delete, get_raw
from .meta import (
    META_ENDPOINTS, FIELD_META, cached_meta, clear_meta_cache, meta, project_id,
    resolve_field_id, resolve_field_ids, resolve_names, resolve_users,
)
from .slim import slim_activity, slim_comment, slim_issue, slim_notification, slim_wiki
from .issues import STATUS_MAP, fetch_all_comments, fetch_issues_raw, fetch_recent_comments
from .parallel import run_parallel

__all__ = [
    "scrub_secrets", "scrubbed_error",
    "available_sources", "project_key", "source_config",
    "get", "post", "patch", "delete", "get_raw",
    "META_ENDPOINTS", "FIELD_META", "cached_meta", "clear_meta_cache", "meta",
    "project_id", "resolve_field_id", "resolve_field_ids", "resolve_names", "resolve_users",
    "slim_activity", "slim_comment", "slim_issue", "slim_notification", "slim_wiki",
    "STATUS_MAP", "fetch_all_comments", "fetch_issues_raw", "fetch_recent_comments",
    "run_parallel",
]
