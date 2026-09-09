"""Tools: source discovery and the project's lookup lists."""

from .. import config
from ..app import mcp
from .. import api
from ..common import D


@mcp.tool()
def get_sources() -> dict:
    """List all configured Backlog sources (spaces) available in this server.
    Use the returned source names as the 'source' argument in other tools.

    Args:
        (none)

    Returns:
        dict: {'default': source name used when source='',
               'sources': {name: {'host', 'projectKey'}}}
    """
    return {
        "default": config.DEFAULT_SOURCE,
        "sources": {
            name: {"host": cfg["host"], "projectKey": cfg["project_key"]}
            for name, cfg in config.SOURCES.items()
        },
    }


_META_KINDS = ["project", "statuses", "users", "issue_types", "categories",
               "milestones", "versions", "priorities", "resolutions", "custom_fields"]


@mcp.tool()
def get_project_metadata(source: str = D, kinds: str = "all", include_archived: bool = False) -> dict:
    """Get the project's lookup lists — statuses, members, priorities, and more.
    Call this before creating or updating issues to learn the valid values.
    Results are cached per server run, so asking for 'all' is cheap.

    Args:
        source: Source name from get_sources. Empty = default source.
        kinds: Comma-separated list of what to fetch, or 'all' for the project
               plus every list below. Valid values:
                 project       — project info (id, name, projectKey)
                 statuses      — 状態: Open / In Progress / Resolved / Closed / custom
                 users         — 担当者 candidates: project members with ids
                 issue_types   — 種別: Bug / Task / ...
                 categories    — カテゴリー
                 milestones    — マイルストーン (same list as versions)
                 versions      — 発生バージョン
                 priorities    — 優先度: High / Normal / Low
                 resolutions   — 完了理由: Fixed / Won't Fix / Duplicate / ...
                 custom_fields — custom fields defined on the project
               Two extras are space-level, so they are never part of 'all':
                 projects      — every project the API key can see
                 myself        — the authenticated user's own profile
        include_archived: Only affects kinds='projects'. True includes archived projects.

    Returns:
        dict: requested kind → its value. Lists of {'id', 'name', ...} for the
        lookup kinds, a single dict for 'project' and 'myself'. An unresolvable
        kind is reported as {'error': ...} under its own key instead of failing
        the whole call.
    """
    wanted = [k.strip() for k in (kinds or "all").split(",") if k.strip()]
    if "all" in wanted:
        wanted = _META_KINDS + [k for k in wanted if k not in _META_KINDS and k != "all"]

    out: dict = {}
    for kind in wanted:
        try:
            if kind == "projects":
                out[kind] = api.get(source, "/projects",
                                     {"archived": "true"} if include_archived else None)
            elif kind == "myself":
                out[kind] = api.get(source, "/users/myself")
            else:
                out[kind] = api.meta(source, kind)
        except Exception as e:
            out[kind] = {"error": api.scrub_secrets(e)}
    return out
