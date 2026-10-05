"""Dynamically build source registry from environment variables.

Pattern — declare a new Backlog space by adding three env vars:
  BACKLOG_API_KEY_<NAME>=...
  BACKLOG_HOST_<NAME>=...
  PROJECT_KEY_<NAME>=...

<NAME> becomes the source identifier (lowercased). Any number of spaces.
Set DEFAULT_SOURCE=<name> to control which source is used when source="" is passed.
"""

import os
import re
import tempfile
from dotenv import load_dotenv

load_dotenv()


def _build_sources() -> dict[str, dict]:
    sources: dict[str, dict] = {}
    for key, val in os.environ.items():
        m = re.match(r"^BACKLOG_API_KEY_([A-Z0-9_]+)$", key)
        if m and val.strip():
            suffix = m.group(1)
            name = suffix.lower()
            host = os.environ.get(f"BACKLOG_HOST_{suffix}", "").strip()
            project_key = os.environ.get(f"PROJECT_KEY_{suffix}", "").strip()
            if host:
                sources[name] = {
                    "api_key":     val.strip(),
                    "base_url":    f"https://{host}/api/v2",
                    "project_key": project_key,
                    "host":        host,
                }
    return sources


SOURCES: dict[str, dict] = _build_sources()
DEFAULT_SOURCE: str = os.environ.get("DEFAULT_SOURCE", next(iter(SOURCES), "")).lower()


# ── Local file handling ──────────────────────────────────────────────────────
# See backlog_mcp/stash.py. Every value can be overridden from .env.

def _float_env(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, "") or default)
    except ValueError:
        return default


def _upload_dirs() -> list[str]:
    """Folders a caller may hand files in from, besides the stash itself.

    BACKLOG_MCP_UPLOAD_DIRS is a os.pathsep-separated list (';' on Windows).
    Default: the user's Downloads and Desktop, including a OneDrive-redirected
    Desktop when one exists.
    """
    raw = os.environ.get("BACKLOG_MCP_UPLOAD_DIRS", "").strip()
    if raw:
        dirs = [os.path.expanduser(d.strip()) for d in raw.split(os.pathsep) if d.strip()]
    else:
        home = os.path.expanduser("~")
        dirs = [os.path.join(home, "Downloads"), os.path.join(home, "Desktop"),
                os.path.join(home, "OneDrive", "Desktop")]
    return [d for d in dirs if os.path.isdir(d)]


TEMP_ROOT: str = (os.environ.get("BACKLOG_MCP_TEMP_DIR", "").strip()
                  or os.path.join(tempfile.gettempdir(), "backlog-mcp"))
MAX_FILE_MB: float = _float_env("BACKLOG_MCP_MAX_FILE_MB", 50)
STASH_MAX_MB: float = _float_env("BACKLOG_MCP_STASH_MAX_MB", 500)
UPLOAD_DIRS: list[str] = _upload_dirs()
