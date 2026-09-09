# Backlog MCP Server

An [MCP](https://modelcontextprotocol.io) server that exposes [Backlog](https://backlog.com/) project management as tools for Claude Desktop (or any MCP-compatible client). Search and manage issues, comments, wiki pages, milestones, custom fields, notifications, and more — directly from a conversation with Claude.

## Features

- **21 tools** covering issues, comments, wiki, categories, issue types, milestones, custom fields, attachments, activity feeds, notifications, watchers, and stars. Tools are grouped by subject with a `kind`/`action` selector rather than split one-per-endpoint, so there is less schema for the model to scan.
- **Multi-space support** — configure any number of Backlog spaces (e.g. separate client/company instances) and target them by name per tool call, without restarting or reconfiguring.
- **One request per change** — `update_issues` and `add_comment` send every field change *plus* the comment *plus* the mention notification in a single PATCH, so Backlog's 課題の変更履歴 gets one entry instead of one per field.
- **Full ticket field coverage** — 状態 / 担当者 / 優先度 / 種別 / マイルストーン / カテゴリー / 発生バージョン / 開始日 / 期限日 / 予定時間 / 実績時間 / 完了理由, each settable by display name *or* numeric id ('Closed', 'clos' and '4' all work), with a `clear_fields` argument to blank them out.
- **Real mentions** — passing `mention_user_ids` posts a comment that renders as a highlighted `@Name` mention *and* triggers a real Backlog notification (bell + email), matching what you get from typing `@` in the Backlog UI. Plain `@Name` text does neither.
- Parallel fetching and updating for bulk operations (`get_issue`, `get_comments`, `update_issues`, `delete_issue` all accept a list of keys).
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
- `get_sources` — list the configured Backlog spaces.
- `get_project_metadata` — one call for every lookup list: `project`, `statuses`, `users`, `issue_types`, `categories`, `milestones`, `versions`, `priorities`, `resolutions`, `custom_fields`, plus space-level `projects` and `myself`. Cached per server run, so `kinds='all'` is cheap.

### Issues
- `get_issues` — search/filter; `count_only=True` returns just the match count.
- `get_issue` — one or many keys, fetched in parallel; `full=False` for slim records.
- `get_related_issues` — parent, children, or both.
- `get_recently_viewed` — recently viewed issues or wikis.
- `create_issue` — create with every field set at once.
- `update_issues` — **the write tool.** One or many keys; sets any combination of 状態 / 担当者 / 優先度 / 種別 / 完了理由 / マイルストーン / カテゴリー / 発生バージョン / 開始日 / 期限日 / 予定時間 / 実績時間, plus `summary`, `description`, `parent_issue_id`, a `comment`, `mention_user_ids` and `clear_fields` — all in a single request per issue.
- `delete_issue` — one or many keys.

### Comments
- `get_comments` — one or many issues; `last_n=0` for the full thread, `last_n=N` for the newest N (slimmed).
- `add_comment` — comment + optional mention + optional field changes, all in one request.
- `manage_comment` — `action='update'` or `'delete'`.

### Attachments
- `get_attachments` — lists an issue's or wiki page's attachments; pass `attachment_id` to download one. Images come back inline, text files as text, other binaries as base64.

### Project admin
- `manage_project_setting` — `kind` of `category` / `issue_type` / `milestone` / `custom_field` × `action` of `add` / `update` / `delete`. Clears the metadata cache on success.

### Wiki
- `get_wikis` — list, read one page (`wiki_id`), or `count_only`.
- `manage_wiki_page` — `action='create'` / `'update'` / `'delete'`.

### Activity & notifications
- `get_activities` — `scope='project'` or `'space'`.
- `get_notifications` — list, or `count_only`.
- `mark_notifications_read` — one notification, or all when `notification_id=0`.

### Watchers & stars
- `manage_watchers` — `action='list'` / `'add'` / `'delete'`.
- `add_star` — star an issue, comment, or wiki page.

## Project layout

```
server.py               entry point — Claude Desktop configs point here
backlog_mcp/
  config.py             builds the multi-space source registry from env vars
  app.py                the FastMCP object and process entry point
  common.py             sentinels shared by tools (default source, "unchanged")
  fields.py             ticket-field value -> Backlog form body; mention rewriting
  api/                  everything below the tool definitions
    secrets.py          API-key redaction (security-critical — read this first)
    sources.py          source name -> configured Backlog space
    http.py             the retrying request path all traffic goes through
    meta.py             project lookup lists, caching, name -> id resolution
    slim.py             payload trimming
    issues.py           paginated issue / comment fetching
    parallel.py         fan-out for multi-key tools
  tools/                the MCP tools, one module per subject
    metadata.py         get_sources, get_project_metadata
    issues.py           get_issues, get_issue, get_related_issues,
                        create_issue, update_issues, delete_issue
    comments.py         get_comments, add_comment, manage_comment
    attachments.py      get_attachments
    project_settings.py manage_project_setting
    wiki.py             get_wikis, manage_wiki_page
    activity.py         get_activities, get_recently_viewed,
                        get_notifications, mark_notifications_read
    social.py           manage_watchers, add_star
```

Each layer only imports the ones above it: `config` → `api/` → `common`/`fields` →
`app` → `tools/`. Importing `backlog_mcp` registers every tool, because each tool
module applies `@mcp.tool()` at import time.

**Adding a tool:** put it in the matching `tools/` module (or add a new module and
list it in `tools/__init__.py`). Reach Backlog through `api.get` / `api.post` /
`api.patch` / `api.delete` rather than `requests` directly — that request path is
what keeps the API key out of error messages.

## Security note

Backlog authenticates with a `?apiKey=` query parameter, so the key is part of
every request URL, and `requests` puts the full URL into its exception messages.
Those messages reach the MCP client. `api/secrets.py` scrubs the key out of every
error leaving the HTTP layer — if you add a code path that talks to Backlog
outside `api/http.py`, scrub it there too.

## License

No license specified — all rights reserved by default.
