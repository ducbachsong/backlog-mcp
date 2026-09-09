"""Resolving a source name to the Backlog space it stands for.

A "source" is one configured Backlog space. Every helper in this package takes
one as its first argument; an empty string means config.DEFAULT_SOURCE.
"""

from .. import config


def source_config(source: str) -> dict:
    """Resolve a source name to its configuration entry.

    Input:
        source: Source name (e.g. 'main'). Empty string = config.DEFAULT_SOURCE.
    Output:
        dict with keys: api_key, base_url, project_key, host.
    Raises:
        ValueError if the name is not configured (message lists valid names).
    """
    name = (source or "").strip() or config.DEFAULT_SOURCE
    cfg = config.SOURCES.get(name)
    if not cfg:
        available = list(config.SOURCES.keys())
        raise ValueError(f"Source '{name}' not configured. Available: {available}")
    return cfg


def available_sources() -> list[str]:
    """List every configured source name.

    Input:  none.
    Output: list of source names, e.g. ['main', 'client_a'].
    """
    return list(config.SOURCES.keys())


def project_key(source: str) -> str:
    """Return the Backlog project key bound to a source.

    Input:  source: Source name. Empty = default source.
    Output: project key string, e.g. 'MYPROJ'.
    """
    return source_config(source)["project_key"]
