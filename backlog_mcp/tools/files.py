"""Tool: the local file stash — files kept between tool calls for later upload.

Anything that should end up attached in Backlog but does not come from Backlog
lands here: a file the user saved to Downloads, something found on the web, or
content the model wrote itself. See ..stash for lifetime and the path allowlist.
"""

import base64
import binascii
import ipaddress
import mimetypes
import os
import re
import socket
from datetime import datetime
from urllib.parse import unquote, urljoin, urlparse

import requests

from ..app import mcp
from .. import stash
from ..api import scrub_secrets
from .attachments import _decode_attachment


_TEXT_VIEW_LIMIT = 20_000


def _check_public_url(url: str) -> None:
    """Refuse non-http(s) URLs and hosts that resolve to private addresses.

    Ticket text can steer the model, so a URL fetch must not become a way to
    pull intranet or cloud-metadata content into a Backlog attachment.
    """
    p = urlparse(url)
    if p.scheme not in ("http", "https") or not p.hostname:
        raise ValueError("Only http:// and https:// URLs can be fetched")
    try:
        infos = socket.getaddrinfo(p.hostname, p.port or (443 if p.scheme == "https" else 80))
    except socket.gaierror as e:
        raise ValueError(f"Cannot resolve host '{p.hostname}': {e}") from None
    for info in infos:
        addr = ipaddress.ip_address(info[4][0].split("%")[0])
        if not addr.is_global:
            raise ValueError(f"'{p.hostname}' resolves to a non-public address ({addr}); "
                             "download the file manually and pass its path instead")


def _filename_from(r: requests.Response, url: str) -> str:
    cd = r.headers.get("Content-Disposition") or ""
    m = re.search(r"filename\*=(?:UTF-8'')?([^;]+)", cd, re.I) or re.search(r'filename="?([^";]+)', cd, re.I)
    if m:
        return unquote(m.group(1).strip())
    return unquote(os.path.basename(urlparse(url).path)) or "download"


def _fetch_url(url: str, filename: str) -> stash.Entry:
    """Download a public URL into the stash, re-checking every redirect hop."""
    for _ in range(5):
        _check_public_url(url)
        try:
            r = requests.get(url, stream=True, timeout=30, allow_redirects=False,
                             headers={"User-Agent": "backlog-mcp"})
        except requests.exceptions.RequestException as e:
            raise ValueError(f"Download failed: {scrub_secrets(e)}") from None
        if r.is_redirect:
            url = urljoin(url, r.headers.get("Location", ""))
            r.close()
            continue
        try:
            if r.status_code >= 400:
                raise ValueError(f"Download failed: HTTP {r.status_code} for {scrub_secrets(url)}")
            mime = (r.headers.get("Content-Type") or "").split(";")[0].strip()
            name = filename or _filename_from(r, url)
            if "." not in name and mime:
                name += mimetypes.guess_extension(mime) or ""
            try:
                return stash.write_stream(name, r.iter_content(1 << 16), mime,
                                          {"url": scrub_secrets(url)})
            except requests.exceptions.RequestException as e:
                raise ValueError(f"Download failed: {scrub_secrets(e)}") from None
        finally:
            r.close()
    raise ValueError("Too many redirects")


_DIR_ALIASES = {"downloads": "Downloads", "desktop": "Desktop"}


def _list_dir(folder: str, limit: int) -> dict:
    if folder.lower() == "stash" or not folder:
        path = stash.root()
    elif folder.lower() in _DIR_ALIASES:
        want = _DIR_ALIASES[folder.lower()]
        path = next((d for d in stash.allowed_dirs() if os.path.basename(d.rstrip("\\/")) == want), "")
        if not path:
            return {"error": f"No '{want}' folder in the upload allowlist", "allowed": stash.allowed_dirs()}
    else:
        path = os.path.realpath(os.path.expanduser(folder))
        if not any(stash.inside(path, d) for d in stash.allowed_dirs()):
            return {"error": f"'{folder}' is outside the upload allowlist", "allowed": stash.allowed_dirs()}
    if not os.path.isdir(path):
        return {"error": f"Not a folder: '{folder}'"}
    files = []
    for dirpath, _dirs, names in os.walk(path):
        for n in names:
            full = os.path.join(dirpath, n)
            try:
                st = os.stat(full)
            except OSError:
                continue
            files.append((st.st_mtime, full, st.st_size))
        if dirpath == path and folder.lower() != "stash":
            break  # top level only for user folders
    files.sort(reverse=True)
    return {"folder": path, "files": [
        {"path": f, "name": os.path.basename(f), "size": size,
         "modified": datetime.fromtimestamp(mt).isoformat(timespec="seconds")}
        for mt, f, size in files[:max(1, min(limit, 200))]
    ]}


@mcp.tool()
def manage_files(
    action: str,
    handle: str = "",
    path: str = "",
    url: str = "",
    text: str = "",
    data_base64: str = "",
    filename: str = "",
    folder: str = "",
    limit: int = 20,
):
    """The local file stash: files kept for this session so they can be attached
    to Backlog later. Every stashed file has a handle ('f1') that add_comment /
    create_issue / update_issues / manage_wiki_page accept in `attachments`.
    Files from Backlog are stashed with get_attachments(save=True); use this
    tool for everything else. The stash is deleted when the server stops.

    Images pasted into the chat cannot be captured — their bytes never reach
    tools. Ask the user to save the image (e.g. to Downloads) and use
    action='list_dir', folder='downloads' to find it.

    Args:
        action: 'list'     — stashed files, plus the stash folder path.
                'add'      — stash one file from exactly one of: `path` (a local
                             file inside the upload allowlist), `url` (public
                             http/https download), `text` (content you wrote, needs
                             `filename`, e.g. 'notes.md'), or `data_base64` (small
                             binary, needs `filename`).
                'view'     — show a stashed file: images inline, text as text.
                'remove'   — delete stashed file(s); `handle` may be comma-separated.
                'clear'    — delete every stashed file.
                'list_dir' — newest files in an allowed folder, to find what the
                             user saved. `folder`: 'downloads', 'desktop', 'stash',
                             or a path inside the allowlist.
        handle: Stash handle for view / remove.
        path, url, text, data_base64: Source for action='add' (pass exactly one).
        filename: Name to store under. Required with text / data_base64; optional
                  override for path / url. Backlog shows this name, and inline
                  image references match on it.
        folder: Folder for list_dir.
        limit: Max files for list_dir (default 20).

    Returns:
        add — {'handle', 'name', 'size', 'mime', 'path', 'origin'}.
        list — {'stash_folder', 'files': [...same shape...], 'upload_allowlist'}.
        view — image content, {'name', 'text'}, or file metadata.
        remove / clear — {'removed': [...]} / {'removed': count}.
        list_dir — {'folder', 'files': [{'path', 'name', 'size', 'modified'}]}.
        Any failure — {'error': message}.
    """
    try:
        if action == "list":
            return {"stash_folder": stash.root(),
                    "files": [e.public() for e in stash.entries()],
                    "upload_allowlist": stash.allowed_dirs()}

        if action == "add":
            given = [k for k, v in (("path", path), ("url", url), ("text", text),
                                    ("data_base64", data_base64)) if v]
            if len(given) != 1:
                return {"error": "Pass exactly one of path, url, text, data_base64"}
            if path:
                return stash.put_file(path, filename).public()
            if url:
                return _fetch_url(url.strip(), filename).public()
            if not filename:
                return {"error": "filename is required with text / data_base64"}
            if text:
                return stash.put_bytes(filename, text.encode("utf-8"), "",
                                       {"written_by": "model"}).public()
            try:
                data = base64.b64decode(data_base64, validate=True)
            except (binascii.Error, ValueError):
                return {"error": "data_base64 is not valid base64"}
            return stash.put_bytes(filename, data, "", {"written_by": "model"}).public()

        if action == "view":
            e = stash.get(handle)
            if stash.is_text(e.mime):
                with open(e.path, "rb") as fh:
                    body = fh.read(_TEXT_VIEW_LIMIT + 1)
                out = {"name": e.name, "text": body[:_TEXT_VIEW_LIMIT].decode("utf-8", errors="replace")}
                if len(body) > _TEXT_VIEW_LIMIT:
                    out["truncated"] = True
                return out
            if e.mime.startswith("image/") and e.size <= 5 * 1024 * 1024:
                with open(e.path, "rb") as fh:
                    return _decode_attachment(fh.read(), e.mime)
            return e.public()

        if action == "remove":
            handles = [h.strip() for h in handle.split(",") if h.strip()]
            if not handles:
                return {"error": "handle is required for action='remove'"}
            return {"removed": [stash.remove(h).handle for h in handles]}

        if action == "clear":
            return {"removed": stash.clear()}

        if action == "list_dir":
            return _list_dir(folder.strip(), limit)

    except ValueError as e:
        return {"error": str(e)}
    return {"error": f"Unknown action '{action}'. Use list, add, view, remove, clear or list_dir."}
