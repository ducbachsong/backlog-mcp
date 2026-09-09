"""Sentinels and small conversions shared by every tool module."""


D = ""  # sentinel for "use default source"


KEEP = -1.0


def normalize_keys(issue_keys, limit: int = 50) -> list[str]:
    """Normalise a single key or list of keys into a capped list of strings.

    Input:
        issue_keys: str, list of str, or None.
        limit: Maximum number of keys to keep (protects against huge batches).
    Output:
        List of non-empty issue keys, at most `limit` long.
    """
    if issue_keys is None:
        return []
    if isinstance(issue_keys, str):
        issue_keys = [issue_keys]
    return [str(k).strip() for k in issue_keys if str(k).strip()][:limit]
