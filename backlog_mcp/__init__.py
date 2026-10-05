"""Backlog MCP server.

Layering (each layer only imports the ones above it):

    config      — declares the Backlog spaces ("sources") read from .env
    api/        — HTTP client, caching, name -> id resolution
    stash       — per-run temp folder for files; local-path allowlist
    common,     — sentinels shared by tools; ticket-field body building;
    fields,       attachment refs -> uploaded ids
    attach
    app         — the FastMCP object
    tools/      — the MCP tools themselves

Importing this package registers every tool and exposes `mcp` and `main`.
"""

from .app import mcp, main
from . import tools  # noqa: F401  — importing registers every @mcp.tool()

__all__ = ["mcp", "main"]
