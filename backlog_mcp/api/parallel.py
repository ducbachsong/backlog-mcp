"""Fan-out helper for the tools that accept a list of issue keys."""

from concurrent.futures import ThreadPoolExecutor, as_completed

from .secrets import scrub_secrets


def run_parallel(keys: list, fn, max_workers: int = 10) -> dict:
    """Run fn over a list of keys concurrently and collect the results by key.

    Input:
        keys: Items to process (issue keys, ids...).
        fn: Callable taking one key and returning its result.
        max_workers: Thread cap (also bounded by len(keys)).
    Output:
        dict mapping key → fn(key), or key → {'error': str} if fn raised.
    """
    if not keys:
        return {}

    def _wrap(k):
        try:
            return k, fn(k)
        except Exception as e:  # surface per-item failures instead of aborting the batch
            return k, {"error": scrub_secrets(e)}

    results: dict = {}
    with ThreadPoolExecutor(max_workers=min(len(keys), max_workers)) as ex:
        futures = [ex.submit(_wrap, k) for k in keys]
        for f in as_completed(futures):
            k, v = f.result()
            results[k] = v
    return results
