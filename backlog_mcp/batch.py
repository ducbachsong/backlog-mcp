"""Batch mode: any tool can run many calls in one MCP round trip.

`@batch` adds an `items` argument to a tool. Each item is a dict of that tool's
own arguments; the tool runs once per item and every result comes back in one
response, in input order. Arguments passed at top level are defaults shared by
every item, so

    update_issues(status='Closed', items=[{'issue_keys': ['A-1'], 'comment': 'dup'},
                                          {'issue_keys': ['A-2'], 'comment': 'fixed'}])

closes both issues with a different comment each, in one tool call.

Each item is validated against the tool's real signature — the same pydantic
model FastMCP validates a direct call with — and one failing item never stops
the rest. Read tools run their items concurrently; write tools run them in
order, so e.g. comments land in the sequence they were given.
"""

import functools
import inspect
from concurrent.futures import ThreadPoolExecutor
from typing import Annotated, Any, Optional

from mcp import types as mcp_types
from mcp.server.fastmcp.utilities.func_metadata import func_metadata
from pydantic import Field, ValidationError

from .api import scrub_secrets


MAX_ITEMS = 50


_WORKERS = 5  # per batch; tools that fan out internally multiply this, so keep it low


_ITEMS_DOC = (
    "Batch mode: list of argument objects, one per call (keys = this tool's "
    f"parameters), max {MAX_ITEMS}. Top-level arguments are defaults shared by every "
    "item. Returns {'total', 'failed', 'results': [one result per item, in order]}; "
    "a failed item's result is {'error': ...} and does not stop the others."
)


def _describe(e: ValidationError) -> str:
    """Flatten a pydantic ValidationError into one readable line."""
    return "; ".join(f"{'.'.join(map(str, err['loc'])) or 'arguments'}: {err['msg']}"
                     for err in e.errors())


def _envelope(results: list):
    """Wrap per-item results; images are lifted out of the JSON into content blocks.

    Input:
        results: One tool result per item, in input order.
    Output:
        {'total', 'failed', 'results'} — or, when any item returned images
        (get_attachments / manage_files view), [that dict, *ImageContent] so
        the images stay viewable instead of becoming base64 inside JSON. Each
        lifted image leaves {'image': n} in its slot: the n-th image below.
    """
    images, out = [], []
    for r in results:
        blocks = ([b for b in r if isinstance(b, mcp_types.ImageContent)]
                  if isinstance(r, list) else [])
        if blocks:
            out.append({"image": len(images) + 1} if len(blocks) == 1
                       else {"images": list(range(len(images) + 1, len(images) + len(blocks) + 1))})
            images.extend(blocks)
        else:
            out.append(r)
    failed = sum(1 for r in out if isinstance(r, dict) and "error" in r)
    env = {"total": len(out), "failed": failed, "results": out}
    return [env, *images] if images else env


def batch(parallel: bool):
    """Decorator giving a tool an `items` argument for running many calls at once.

    Apply below `@mcp.tool()`. Parameters that were required become optional in
    the published schema (an item may supply them instead); a single call that
    omits one still gets {'error': '<name>: Field required'}.

    Input:
        parallel: True for read-only tools (items run concurrently), False for
                  tools that write (items run one after another, in order).
    Output:
        The decorator.
    """
    def deco(fn):
        sig = inspect.signature(fn)
        arg_model = func_metadata(fn, structured_output=False).arg_model
        names = list(sig.parameters)
        required = {n for n, p in sig.parameters.items() if p.default is inspect.Parameter.empty}

        def call(args: dict):
            args = {k: v for k, v in args.items() if not (k in required and v is None)}
            try:
                validated = arg_model.model_validate(args).model_dump_one_level()
            except ValidationError as e:
                return {"error": _describe(e)}
            return fn(**validated)

        @functools.wraps(fn)
        def wrapper(items: Optional[list] = None, **kwargs):
            if not items:
                return call(kwargs)
            if len(items) > MAX_ITEMS:
                return {"error": f"At most {MAX_ITEMS} items per call (got {len(items)})"}

            def run_one(item):
                if not isinstance(item, dict):
                    return {"error": "Each item must be an object of this tool's arguments"}
                unknown = sorted(set(item) - set(names))
                if unknown:
                    return {"error": f"Unknown argument(s) {unknown}. Valid: {names}"}
                try:
                    return call({**kwargs, **item})
                except Exception as e:  # one bad item must not abort the batch
                    return {"error": scrub_secrets(e)}

            if parallel and len(items) > 1:
                with ThreadPoolExecutor(max_workers=min(len(items), _WORKERS)) as ex:
                    results = list(ex.map(run_one, items))
            else:
                results = [run_one(i) for i in items]
            return _envelope(results)

        params = [p.replace(default=None, annotation=Optional[p.annotation])
                  if p.name in required else p
                  for p in sig.parameters.values()]
        params.append(inspect.Parameter(
            "items", inspect.Parameter.POSITIONAL_OR_KEYWORD, default=None,
            annotation=Annotated[Optional[list[dict[str, Any]]], Field(description=_ITEMS_DOC)],
        ))
        # A batch always answers with a dict (or a list when images are lifted
        # out), so only a `dict` return annotation stays valid for structured output.
        ret = sig.return_annotation if sig.return_annotation is dict else inspect.Signature.empty
        wrapper.__signature__ = sig.replace(parameters=params, return_annotation=ret)
        wrapper.__annotations__ = {p.name: p.annotation for p in params}
        if ret is dict:
            wrapper.__annotations__["return"] = dict
        return wrapper

    return deco
