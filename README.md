# Backlog MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [Backlog](https://backlog.com/) project management as tools for Claude Desktop (or any MCP-compatible client). Search and manage issues, comments, wiki pages, milestones, custom fields, notifications, and more — directly from a conversation with Claude.

## Features

- **61 tools** covering issues, comments, wiki, categories, issue types, milestones, custom fields, attachments, activity feeds, notifications, watchers, and stars.
- **Multi-space support** — configure any number of Backlog spaces (e.g. separate client/company instances) and target them by name per tool call, without restarting or reconfiguring.
- **Real mentions** — `add_comment_with_mention` posts a comment that renders as a highlighted `@Name` mention *and* triggers a real Backlog notification (bell + email), matching what you get from typing `@` in the Backlog UI. Plain `@Name` text (including from `add_comment`) does neither.
- Parallel fetching for bulk operations (`get_issues_by_keys`, `get_recent_comments_bulk`, `bulk_update_issue_status`).
- Read-only tools require no confirmation; every create/update/delete tool is marked in its docstring for the client to confirm with the user before calling.

## Setup

### 1. Install dependencies

```bash
uv sync
# or
pip install -e .
```

Requires Python 3.11+.

### 2. Configure Backlog spaces

Copy `.env.example` to `.env` and fill in your space(s). Each space needs three variables sharing a common `<NAME>` suffix:

```
BACKLOG_API_KEY_<NAME>=...
BACKLOG_HOST_<NAME>=...
PROJECT_KEY_<NAME>=...
```

`<NAME>` (lowercased) becomes the `source` argument you pass to tools. Add as many spaces as you need by repeating the pattern with a different `<NAME>`. Optionally set `DEFAULT_SOURCE=<name>` to control which space is used when `source` is omitted — otherwise the first configured space is used.

Get your API key from Backlog under **Personal Settings → API**.

### 3. Register with Claude Desktop

Copy [`claude_desktop_config.example.json`](claude_desktop_config.example.json) to your Claude Desktop config location, fill in the real `command`/`args` paths and credentials, and merge it into your existing `mcpServers` block if you already have other servers configured:

```json
{
  "mcpServers": {
    "backlog": {
      "command": "/path/to/backlog-mcp/.venv/Scripts/python.exe",
      "args": ["/path/to/backlog-mcp/server.py"],
      "env": {
        "BACKLOG_API_KEY_SPACE1": "your_api_key_here",
        "BACKLOG_HOST_SPACE1": "your-space.backlog.com",
        "PROJECT_KEY_SPACE1": "YOUR_PROJECT_KEY"
      }
    }
  }
}
```

Your filled-in `claude_desktop_config.json` is machine-specific and contains live credentials — keep it out of version control (already covered by `.gitignore`).

## Tools

### Discovery & metadata
`get_sources`, `get_project`, `get_project_statuses`, `get_project_users`, `get_issue_types`, `get_categories`, `get_milestones`, `get_priorities`

### Issues
`get_issues`, `get_issue`, `get_issues_by_keys`, `get_parent_issue`, `get_child_issues`, `get_issue_count`, `create_issue`, `update_issue`, `delete_issue`, `bulk_update_issue_status`

### Comments
`get_issue_comments`, `get_recent_comments_bulk`, `add_comment`, `add_comment_with_mention`, `update_comment`, `delete_comment`

### Attachments
`get_issue_attachments`, `download_issue_attachment`, `get_wiki_attachments`, `download_wiki_attachment` — images are returned inline, text files as text, other binaries as base64.

### Project admin
Categories: `add_category`, `update_category`, `delete_category`
Issue types: `add_issue_type`, `update_issue_type`, `delete_issue_type`
Milestones: `add_milestone`, `update_milestone`, `delete_milestone`
Custom fields: `get_custom_fields`, `add_custom_field`, `update_custom_field`, `delete_custom_field`

### Wiki
`get_wiki_pages`, `get_wiki_count`, `get_wiki_page`, `create_wiki_page`, `update_wiki_page`, `delete_wiki_page`

### Activity & notifications
`get_space_activities`, `get_project_activities`, `get_recently_viewed_issues`, `get_recently_viewed_wikis`, `get_notifications`, `get_notification_count`, `mark_notification_read`, `reset_notification_count`

### Watchers & stars
`get_issue_watchers`, `add_issue_watcher`, `delete_issue_watcher`, `add_star`

### Space / user
`get_projects`, `get_my_info`

## Project layout

- `server.py` — MCP tool definitions (FastMCP)
- `backlog_api.py` — HTTP client, pagination, retries, response slimming (not exposed as tools)
- `config.py` — builds the multi-space source registry from environment variables

## License

No license specified — all rights reserved by default.
