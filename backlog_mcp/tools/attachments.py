"""Tools: listing and downloading issue / wiki attachments."""

import base64

from mcp import types as mcp_types

from ..app import mcp
from .. import api, config, stash
from ..common import D


_IMAGE_MIMES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/svg+xml", "image/bmp"}


_TEXT_PREFIXES = ("text/", "application/json", "application/xml", "application/javascript")


def _decode_attachment(data: bytes, content_type: str):
    """Return downloaded attachment bytes in the most useful form for the model.

    Input:
        data: Raw file bytes.
        content_type: Content-Type header from the download response.
    Output:
        list[ImageContent] for images (so the model can actually look at them),
        {'content_type', 'text'} for text-ish files,
        {'content_type', 'size_bytes', 'data_base64'} for anything else.
    """
    mime = content_type.split(";")[0].strip()
    if mime in _IMAGE_MIMES:
        return [mcp_types.ImageContent(
            type="image",
            data=base64.b64encode(data).decode(),
            mimeType=mime,
        )]
    if any(mime.startswith(p) for p in _TEXT_PREFIXES):
        return {"content_type": mime, "text": data.decode("utf-8", errors="replace")}
    return {
        "content_type": mime,
        "size_bytes": len(data),
        "data_base64": base64.b64encode(data).decode(),
    }


def _save_one(source: str, base: str, att: dict, origin: dict) -> dict:
    """Download one attachment straight into the stash and return its handle."""
    if (att.get("size") or 0) > stash.max_file_bytes():
        return {"error": f"'{att.get('name')}' is larger than the size limit "
                         "(BACKLOG_MCP_MAX_FILE_MB)"}
    with api.stream(source, f"{base}/attachments/{att['id']}") as (ct, chunks):
        entry = stash.write_stream(att.get("name") or f"attachment-{att['id']}", chunks, ct,
                                   dict(origin, attachmentId=att["id"]))
    return entry.public()


@mcp.tool()
def get_attachments(
    target: str,
    source: str = D,
    kind: str = "issue",
    attachment_id: int = 0,
    comment_id: int = 0,
    save: bool = False,
):
    """List, view, or save the files attached to an issue or wiki page.

    To copy files to another issue / comment / wiki page, call with save=True:
    the files are downloaded into the local stash and you get handles ('f1')
    to pass as `attachments` to add_comment / create_issue / update_issues /
    manage_wiki_page. The bytes never go through the conversation.

    Args:
        target: Issue key (kind='issue', e.g. 'PROJECT-123') or wiki page id
                (kind='wiki', e.g. '12345').
        source: Source name from get_sources. Empty = default source.
        kind: 'issue' (default) or 'wiki'.
        attachment_id: One attachment id. With save=False the file is returned
                       for viewing; with save=True it is stashed.
        comment_id: Issue comment id (get_comments shows which comments have
                    'attachments'). Selects exactly the files that comment
                    attached — listed with save=False, stashed with save=True.
        save: False (default) = list / view. True = download into the stash;
              with neither attachment_id nor comment_id, every file of the target.

    Returns:
        Listing — [{'id', 'name', 'size', 'created', ...}] ([{'id', 'name'}]
        for a comment).
        Viewing — images inline as viewable image content, text files as
        {'content_type', 'text'}, other binaries as
        {'content_type', 'size_bytes', 'data_base64'}.
        Saving — {'saved': [{'handle', 'name', 'size', 'mime', 'path', 'origin'}],
        'failures': {attachment id: error}}.
    """
    if kind not in ("issue", "wiki"):
        return {"error": f"Unknown kind '{kind}'. Use 'issue' or 'wiki'."}
    if comment_id and kind != "issue":
        return {"error": "comment_id only applies to kind='issue'"}
    base = f"/issues/{target}" if kind == "issue" else f"/wikis/{target}"

    if not save:
        if attachment_id:
            data, ct = api.get_raw(source, f"{base}/attachments/{attachment_id}")
            return _decode_attachment(data, ct)
        if comment_id:
            return api.comment_attachments(api.get(source, f"{base}/comments/{comment_id}"))
        return api.get(source, f"{base}/attachments")

    listing = {a["id"]: a for a in api.get(source, f"{base}/attachments")}
    if attachment_id:
        wanted = [listing.get(attachment_id) or {"id": attachment_id}]
    elif comment_id:
        refs = api.comment_attachments(api.get(source, f"{base}/comments/{comment_id}"))
        wanted = [listing.get(r["id"]) or r for r in refs]
        if not wanted:
            return {"saved": [], "failures": {}, "note": f"Comment {comment_id} attached no files"}
    else:
        wanted = list(listing.values())

    origin = {"source": source or config.DEFAULT_SOURCE, kind: target}
    if comment_id:
        origin["commentId"] = comment_id
    by_id = {a["id"]: a for a in wanted}
    results = api.run_parallel(list(by_id), lambda i: _save_one(source, base, by_id[i], origin))
    saved = [results[i] for i in by_id if "error" not in results[i]]
    failures = {i: results[i]["error"] for i in by_id if "error" in results[i]}
    return {"saved": saved, "failures": failures}
