"""Every MCP tool, grouped by subject.

Importing this package is what registers the tools: each module decorates its
functions with `@mcp.tool()` at import time, so the imports below are the
registration, not a convenience.

    metadata          — get_sources, get_project_metadata
    issues            — get_issues, get_issue, get_related_issues,
                        create_issue, update_issues, delete_issue
    comments          — get_comments, add_comment, manage_comment
    attachments       — get_attachments
    project_settings  — manage_project_setting
    wiki              — get_wikis, manage_wiki_page
    activity          — get_activities, get_recently_viewed,
                        get_notifications, mark_notifications_read
    social            — manage_watchers, add_star
"""

from . import (  # noqa: F401  — imported for the @mcp.tool() side effect
    metadata,
    issues,
    comments,
    attachments,
    project_settings,
    wiki,
    activity,
    social,
)
