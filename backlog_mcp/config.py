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
