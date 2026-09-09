"""Tools: listing and downloading issue / wiki attachments."""

import base64

from mcp import types as mcp_types

from ..app import mcp
from .. import api
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


@mcp.tool()
def get_attachments(target: str, source: str = D, kind: str = "issue", attachment_id: int = 0):
    """List the files attached to an issue or wiki page, or download one of them.
    Call once without attachment_id to see what is there, then again with the id.

    Args:
        target: Issue key (kind='issue', e.g. 'PROJECT-123') or wiki page id
                (kind='wiki', e.g. '12345').
        source: Source name from get_sources. Empty = default source.
        kind: 'issue' (default) or 'wiki'.
        attachment_id: 0 (default) = list attachments. Non-zero = download that file.

    Returns:
        When listing — list of {'id', 'name', 'size', 'created', ...}.
        When downloading — images come back inline as viewable image content,
        text files as {'content_type', 'text'}, other binaries as
        {'content_type', 'size_bytes', 'data_base64'}.
    """
    base = f"/issues/{target}" if kind == "issue" else f"/wikis/{target}"
    if not attachment_id:
        return api.get(source, f"{base}/attachments")
    data, ct = api.get_raw(source, f"{base}/attachments/{attachment_id}")
    return _decode_attachment(data, ct)
