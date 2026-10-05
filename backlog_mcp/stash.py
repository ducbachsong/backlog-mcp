"""The file stash: a per-run temp folder that holds files between tool calls.

Files downloaded from Backlog, fetched from a URL, or written by the model are
kept here under short handles ('f1', 'f2', ...). Tools hand each other handles,
not bytes, so an attachment copied from one ticket to another never passes
through the model's context — the upload path reads it straight from disk.

Lifetime: the folder belongs to this server process and is deleted when the
process exits. Folders left behind by a run that was killed are swept at
startup once nothing in them has changed for STALE_HOURS.

Local paths: `resolve_local_path` is the only way a caller-supplied path reaches
the disk, and it refuses anything outside config.UPLOAD_DIRS + the stash folder.
The model can be steered by ticket text, so it must not be able to read and
upload arbitrary files from the user's machine.
"""

import atexit
import itertools
import mimetypes
import os
import re
import shutil
import threading
import time
from dataclasses import dataclass, field

from . import config


STALE_HOURS = 24
HANDLE_RE = re.compile(r"^f\d+$")

_ROOT = os.path.join(config.TEMP_ROOT, str(os.getpid()))
_lock = threading.Lock()
_entries: dict[str, "Entry"] = {}
_counter = itertools.count(1)


@dataclass
class Entry:
    """One stashed file (or, with handle='', a local file being uploaded as-is)."""
    handle: str
    name: str
    path: str
    mime: str
    size: int
    origin: dict = field(default_factory=dict)

    def public(self) -> dict:
        """The view returned to the model."""
        out = {"handle": self.handle, "name": self.name, "size": self.size,
               "mime": self.mime, "path": self.path}
        if self.origin:
            out["origin"] = self.origin
        return out


def root() -> str:
    """Return this run's stash folder, creating it on first use."""
    os.makedirs(_ROOT, exist_ok=True)
    return _ROOT


def max_file_bytes() -> int:
    return int(config.MAX_FILE_MB * 1024 * 1024)


def safe_name(name: str) -> str:
    """Reduce a caller- or server-supplied filename to one safe to create on disk.

    Keeps the name recognisable — Backlog references inline images by filename,
    so a copied comment only renders if the name survives — but strips any
    directory part and characters Windows refuses.
    """
    base = re.split(r"[\\/]", str(name or ""))[-1]
    base = re.sub(r'[<>:"|?*\x00-\x1f]', "_", base).strip(" .")
    return base[:150] or "file"


# The Windows registry, which mimetypes consults, misses or mislabels these.
_TEXT_TYPES = {".md": "text/markdown", ".markdown": "text/markdown", ".txt": "text/plain",
               ".log": "text/plain", ".csv": "text/csv", ".tsv": "text/tab-separated-values",
               ".json": "application/json", ".yaml": "text/yaml", ".yml": "text/yaml",
               ".xml": "application/xml", ".html": "text/html", ".sql": "text/plain"}


def guess_mime(name: str, fallback: str = "application/octet-stream") -> str:
    ext = os.path.splitext(name)[1].lower()
    return _TEXT_TYPES.get(ext) or mimetypes.guess_type(name)[0] or fallback


def is_text(mime: str) -> bool:
    return mime.startswith("text/") or mime in ("application/json", "application/xml")


def _total_bytes() -> int:
    return sum(e.size for e in _entries.values())


def write_stream(name: str, chunks, mime: str = "", origin: dict = None) -> Entry:
    """Write an iterable of byte chunks into the stash as a new entry.

    The size cap is enforced while writing, so an oversized download is
    abandoned part-way instead of filling the disk first.

    Input:
        name: Original filename; sanitised but otherwise kept.
        chunks: Iterable of bytes.
        mime: MIME type; guessed from the name when blank.
        origin: Where the file came from, e.g. {'source', 'issueKey', 'attachmentId'}.
    Output:
        The new Entry.
    Raises:
        ValueError when the file exceeds BACKLOG_MCP_MAX_FILE_MB or the stash
        would exceed BACKLOG_MCP_STASH_MAX_MB.
    """
    name = safe_name(name)
    with _lock:
        handle = f"f{next(_counter)}"
    slot = os.path.join(root(), handle)
    os.makedirs(slot, exist_ok=True)
    path = os.path.join(slot, name)

    cap, size = max_file_bytes(), 0
    try:
        with open(path, "wb") as fh:
            for chunk in chunks:
                if not chunk:
                    continue
                size += len(chunk)
                if size > cap:
                    raise ValueError(f"'{name}' is larger than the {config.MAX_FILE_MB:g} MB "
                                     "limit (BACKLOG_MCP_MAX_FILE_MB)")
                fh.write(chunk)
        with _lock:
            if _total_bytes() + size > config.STASH_MAX_MB * 1024 * 1024:
                raise ValueError(f"Stash is full ({config.STASH_MAX_MB:g} MB, "
                                 "BACKLOG_MCP_STASH_MAX_MB) — remove files with manage_files first")
            mime = (mime or "").split(";")[0].strip()
            if not mime or mime == "application/octet-stream":
                mime = guess_mime(name)
            entry = Entry(handle, name, path, mime, size, origin or {})
            _entries[handle] = entry
        return entry
    except BaseException:
        shutil.rmtree(slot, ignore_errors=True)
        raise


def put_bytes(name: str, data: bytes, mime: str = "", origin: dict = None) -> Entry:
    """Stash an in-memory blob. See write_stream."""
    return write_stream(name, [data], mime, origin)


def put_file(path: str, name: str = "", origin: dict = None) -> Entry:
    """Copy an allowlisted local file into the stash. See resolve_local_path."""
    real = resolve_local_path(path)

    def chunks():
        with open(real, "rb") as fh:
            while chunk := fh.read(1 << 16):
                yield chunk

    return write_stream(name or os.path.basename(real), chunks(), "",
                        origin or {"path": real})


def get(handle: str) -> Entry:
    """Look up a handle.

    Raises:
        ValueError with a message that tells the model how to recover — handles
        do not survive a server restart, so 'not found' usually means re-fetch.
    """
    with _lock:
        entry = _entries.get(str(handle).strip())
    if not entry or not os.path.isfile(entry.path):
        raise ValueError(f"No stashed file '{handle}'. Handles last only while the server "
                       "runs — list them with manage_files(action='list') or fetch the "
                       "file again.")
    return entry


def entries() -> list[Entry]:
    with _lock:
        return list(_entries.values())


def remove(handle: str) -> Entry:
    entry = get(handle)
    with _lock:
        _entries.pop(entry.handle, None)
    shutil.rmtree(os.path.dirname(entry.path), ignore_errors=True)
    return entry


def clear() -> int:
    with _lock:
        n = len(_entries)
        _entries.clear()
    shutil.rmtree(_ROOT, ignore_errors=True)
    return n


# ── Local paths ──────────────────────────────────────────────────────────────

def allowed_dirs() -> list[str]:
    """Folders local paths may come from: config.UPLOAD_DIRS plus this run's stash."""
    return list(config.UPLOAD_DIRS) + [_ROOT]


def inside(path: str, folder: str) -> bool:
    p = os.path.normcase(os.path.realpath(path))
    f = os.path.normcase(os.path.realpath(folder))
    try:
        return os.path.commonpath([p, f]) == f
    except ValueError:  # different drives on Windows
        return False


def resolve_local_path(path: str) -> str:
    """Check a caller-supplied path against the upload allowlist.

    The path is fully resolved first (symlinks, '..') so it cannot escape an
    allowed folder by indirection.

    Input:
        path: Absolute path, or one starting with '~'.
    Output:
        The resolved real path of an existing file.
    Raises:
        ValueError when the file does not exist or sits outside every allowed folder.
    """
    real = os.path.realpath(os.path.expanduser(str(path).strip().strip('"')))
    if not any(inside(real, d) for d in allowed_dirs()):
        raise ValueError(f"'{path}' is outside the folders files may be uploaded from: "
                         f"{'; '.join(allowed_dirs())}. Move it into one of them, or extend "
                         "BACKLOG_MCP_UPLOAD_DIRS.")
    if not os.path.isfile(real):
        raise ValueError(f"No such file: '{path}'")
    return real


def local_entry(path: str) -> Entry:
    """Describe an allowlisted local file as an Entry without copying it."""
    real = resolve_local_path(path)
    name = os.path.basename(real)
    return Entry("", name, real, guess_mime(name), os.path.getsize(real), {"path": real})


# ── Lifetime ─────────────────────────────────────────────────────────────────

def _last_change(folder: str) -> float:
    latest = os.path.getmtime(folder)
    for dirpath, _dirs, files in os.walk(folder):
        for f in files:
            try:
                latest = max(latest, os.path.getmtime(os.path.join(dirpath, f)))
            except OSError:
                pass
    return latest


def sweep_stale() -> None:
    """Delete stash folders of earlier runs that were killed before cleaning up.

    Folders are keyed by pid, and other server instances (Claude Desktop and
    Claude Code side by side) may be alive, so only folders idle for
    STALE_HOURS are removed.
    """
    if not os.path.isdir(config.TEMP_ROOT):
        return
    cutoff = time.time() - STALE_HOURS * 3600
    for name in os.listdir(config.TEMP_ROOT):
        folder = os.path.join(config.TEMP_ROOT, name)
        if folder == _ROOT or not os.path.isdir(folder):
            continue
        try:
            if _last_change(folder) < cutoff:
                shutil.rmtree(folder, ignore_errors=True)
        except OSError:
            pass


atexit.register(lambda: shutil.rmtree(_ROOT, ignore_errors=True))
