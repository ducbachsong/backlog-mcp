"""Redaction of Backlog API keys from anything that can reach the caller.

Backlog API v2 authenticates with a `?apiKey=` query parameter, so the key is
part of every request URL — and `requests` embeds the full URL in the message of
HTTPError, ConnectionError and Timeout. Those messages are handed to the MCP
client verbatim, which would put the key in the model's context, the chat
transcript and any logs. This module exists to stop that.
"""

import re

from .. import config


_APIKEY_QS = re.compile(r"(apiKey=)[^&\s'\"<>]+", re.IGNORECASE)


def scrub_secrets(text) -> str:
    """Redact Backlog API keys from any text that may reach the caller.

    Two passes: the `apiKey=...` query parameter (catches keys embedded in URLs,
    including ones from sources this process no longer has configured), then the
    literal value of every configured key (catches keys that appear outside a
    query string, e.g. in a header dump).

    Input:  text: Any value; stringified before scrubbing.
    Output: The text with each key replaced by '***'.
    """
    out = _APIKEY_QS.sub(r"\1***", str(text))
    for cfg in config.SOURCES.values():
        key = (cfg.get("api_key") or "").strip()
        if key:
            out = out.replace(key, "***")
    return out


def scrubbed_error(e: Exception) -> Exception:
    """Rebuild a requests exception with its message redacted.

    The type is preserved so callers can still branch on it, and `.response` /
    `.request` are carried over so status codes stay reachable.

    Input:  e: The original exception raised by requests.
    Output: A same-typed exception whose message contains no API key.
    """
    try:
        return type(e)(
            scrub_secrets(e),
            response=getattr(e, "response", None),
            request=getattr(e, "request", None),
        )
    except Exception:  # non-standard signature — fall back to a plain error
        return RuntimeError(scrub_secrets(e))
