"""Entry point for the Backlog MCP server.

The implementation lives in the `backlog_mcp` package — start at
`backlog_mcp/__init__.py` for the layering, or `backlog_mcp/tools/` for the
tools themselves. This file stays at the repo root because existing Claude
Desktop configs point at it by path.
"""

from backlog_mcp import main, mcp  # noqa: F401 — `mcp` is what MCP tooling looks for here

if __name__ == "__main__":
    main()
