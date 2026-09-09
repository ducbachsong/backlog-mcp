"""The HTTP client: one retrying, key-scrubbing request path for all Backlog traffic.

Every call in this package funnels through `_request`, which is what makes the
API-key redaction in `.secrets` airtight — see `_request` for the details.
"""

import time
from typing import Any

import requests

from .secrets import scrub_secrets, scrubbed_error
from .sources import source_config


def _request(method: str, url: str, **kwargs) -> requests.Response:
    """Send one HTTP request with retry on rate limit and transient network errors.

    Retries up to 3 times: exponential backoff on HTTP 429, 1s backoff on
    timeout / connection reset.

    Every failure leaves here with its message scrubbed of the API key — this is
    the single choke point all Backlog traffic passes through, so scrubbing here
    covers both the errors callers catch and the ones that propagate uncaught to
    the MCP client. `raise ... from None` drops the original exception so the key
    cannot resurface through the __context__ chain in a traceback.

    Input:
        method: HTTP verb ('GET', 'POST', 'PATCH', 'DELETE').
        url: Absolute request URL.
        **kwargs: Passed straight to requests.request (params, data, files...).
    Output:
        requests.Response with a 2xx status.
    Raises:
        requests.HTTPError for non-2xx responses, RuntimeError if retries run out.
    """
    for attempt in range(3):
        try:
            r = requests.request(method, url, timeout=30, **kwargs)
            if r.status_code == 429:
                time.sleep(2 ** attempt)
                continue
            r.raise_for_status()
            return r
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError) as e:
            if attempt == 2:
                raise scrubbed_error(e) from None
            time.sleep(1)
        except requests.exceptions.RequestException as e:
            raise scrubbed_error(e) from None
    raise RuntimeError(f"Max retries exceeded for {scrub_secrets(url)}")


def get(source: str, endpoint: str, params: dict = None, list_params: dict = None) -> Any:
    """GET a Backlog endpoint and return the decoded JSON.

    Input:
        source: Source name. Empty = default source.
        endpoint: Path below /api/v2, e.g. '/issues'.
        params: Single-value query params, e.g. {'count': 20}.
        list_params: Repeated query params, e.g. {'statusId[]': [1, 2]}.
    Output:
        Parsed JSON — dict or list depending on the endpoint.
    """
    cfg = source_config(source)
    p = list((params or {}).items()) + [("apiKey", cfg["api_key"])]
    for k, vals in (list_params or {}).items():
        for v in (vals if isinstance(vals, list) else [vals]):
            p.append((k, v))
    return _request("GET", f"{cfg['base_url']}{endpoint}", params=p).json()


def post(source: str, endpoint: str, data: dict = None, files=None, extra_params: list = None) -> Any:
    """POST a form-encoded body to a Backlog endpoint.

    Input:
        source: Source name. Empty = default source.
        endpoint: Path below /api/v2, e.g. '/issues'.
        data: Form fields. A list value is sent as repeated keys ('categoryId[]').
        files: Optional multipart file payload.
        extra_params: Extra query-string tuples appended before apiKey.
    Output:
        Parsed JSON of the created resource.
    """
    cfg = source_config(source)
    p = (extra_params or []) + [("apiKey", cfg["api_key"])]
    return _request("POST", f"{cfg['base_url']}{endpoint}", params=p, data=data, files=files).json()


def patch(source: str, endpoint: str, data: dict = None, extra_params: list = None) -> Any:
    """PATCH a form-encoded body to a Backlog endpoint (partial update).

    Input:
        source: Source name. Empty = default source.
        endpoint: Path below /api/v2, e.g. '/issues/KEY-1'.
        data: Only the fields to change. A list value is sent as repeated keys.
        extra_params: Extra query-string tuples appended before apiKey.
    Output:
        Parsed JSON of the updated resource.
    """
    cfg = source_config(source)
    p = (extra_params or []) + [("apiKey", cfg["api_key"])]
    return _request("PATCH", f"{cfg['base_url']}{endpoint}", params=p, data=data).json()


def delete(source: str, endpoint: str, params: dict = None) -> Any:
    """DELETE a Backlog resource.

    Input:
        source: Source name. Empty = default source.
        endpoint: Path below /api/v2, e.g. '/issues/KEY-1'.
        params: Extra query params (e.g. substituteIssueTypeId).
    Output:
        Parsed JSON of the deleted resource.
    """
    cfg = source_config(source)
    p = list((params or {}).items()) + [("apiKey", cfg["api_key"])]
    return _request("DELETE", f"{cfg['base_url']}{endpoint}", params=p).json()


def get_raw(source: str, endpoint: str) -> tuple[bytes, str]:
    """GET binary content without JSON parsing — used for attachment downloads.

    Input:
        source: Source name. Empty = default source.
        endpoint: Attachment path, e.g. '/issues/KEY-1/attachments/99'.
    Output:
        (raw bytes, Content-Type header value).
    """
    cfg = source_config(source)
    r = _request("GET", f"{cfg['base_url']}{endpoint}", params=[("apiKey", cfg["api_key"])])
    return r.content, r.headers.get("Content-Type", "application/octet-stream")
