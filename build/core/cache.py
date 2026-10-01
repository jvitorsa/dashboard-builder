import hashlib
import json

from cachetools import LRUCache

import config

_result_cache: LRUCache = LRUCache(maxsize=config.RESULT_CACHE_SIZE)


def _key(sql: str, params: list, data_version: int) -> str:
    params_repr = json.dumps(params, sort_keys=True, default=str)
    raw = f"{data_version}|{sql}|{params_repr}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def get_or_execute(sql: str, params: list, data_version: int, executor):
    """executor: callable() -> (columns, rows). Cached per (sql, params, data_version) -
    changing data_version naturally ages out stale entries since the key changes."""
    key = _key(sql, params, data_version)
    cached = _result_cache.get(key)
    if cached is not None:
        return cached
    result = executor()
    _result_cache[key] = result
    return result
