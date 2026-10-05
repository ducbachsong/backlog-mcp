"""Turning an `attachments=[...]` tool argument into Backlog attachment ids.

A ref is either a stash handle ('f1') or a local file path inside the upload
allowlist (see stash.resolve_local_path). The write tools use this in three
steps:

    prepare        validate every ref up front, before anything is written, so
                   a typo fails the call instead of leaving a half-done change
    embed_images   reference image files in the body so they render inline
    upload         stage each file in the *target* space just before the write
                   — which is what lets a file read from one space be attached
                   in another

Uploads are single-use in Backlog, so a caller writing to several issues calls
`upload` once per issue.
"""

import re

from . import api, stash
from .stash import Entry


def prepare(refs) -> list[Entry]:
    """Resolve and validate attachment refs without touching Backlog.

    Input:
        refs: None, one ref, or a list of refs — stash handles or local paths.
    Output:
        List of Entry, in input order, duplicates dropped.
    Raises:
        ValueError naming the first bad ref (unknown handle, path outside the
        allowlist, missing file, file over the size cap).
    """
    if not refs:
        return []
    if isinstance(refs, str):
        refs = [refs]
    out, seen = [], set()
    for ref in refs:
        r = str(ref).strip()
        if not r:
            continue
        entry = stash.get(r) if stash.HANDLE_RE.match(r) else stash.local_entry(r)
        if entry.size > stash.max_file_bytes():
            raise ValueError(f"'{entry.name}' is larger than the size limit "
                             "(BACKLOG_MCP_MAX_FILE_MB)")
        if entry.path not in seen:
            seen.add(entry.path)
            out.append(entry)
    return out


def upload(source: str, entries: list[Entry]) -> list[int]:
    """Stage each file in the source's space and return the attachment ids.

    Input:
        source: Target source — where the files will be attached.
        entries: From prepare().
    Output:
        Attachment ids for `attachmentId[]`, in the same order.
    """
    ids = []
    for e in entries:
        with open(e.path, "rb") as fh:
            ids.append(api.upload(source, e.name, fh.read(), e.mime)["id"])
    return ids


def embed_images(source: str, text: str, entries: list[Entry]) -> str:
    """Append an inline reference for each image the text does not already show.

    Backlog only renders an attached image inline when the body references it
    by filename, in the project's text format: '![image][name]' (markdown) or
    '#image(name)' (backlog). Text copied from another ticket usually already
    holds those references — they are left alone, and still resolve because
    files keep their original names.

    Input:
        source: Target source; its project's textFormattingRule picks the syntax.
        text: Body the files are posted with.
        entries: From prepare(). Non-images are ignored.
    Output:
        The text with references appended on new lines (unchanged if none needed).
    """
    images = [e for e in entries if e.mime.startswith("image/")]
    if not images:
        return text
    rule = (api.meta(source, "project") or {}).get("textFormattingRule", "markdown")
    lines = []
    for e in images:
        if re.search(rf"\[{re.escape(e.name)}\]|#(?:image|thumbnail)\({re.escape(e.name)}\)", text or ""):
            continue
        lines.append(f"#image({e.name})" if rule == "backlog" else f"![image][{e.name}]")
    if not lines:
        return text
    return f"{text}\n\n" + "\n".join(lines) if text else "\n".join(lines)


def names(entries: list[Entry]) -> list[str]:
    return [e.name for e in entries]
