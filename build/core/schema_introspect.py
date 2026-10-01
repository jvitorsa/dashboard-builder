import hashlib

from cachetools import LRUCache

import config
from build.core import duckdb_conn, file_registry

_schema_cache: LRUCache = LRUCache(maxsize=config.SCHEMA_CACHE_SIZE)


def _cache_key(sql: str) -> tuple[str, int]:
    return hashlib.sha256(sql.encode("utf-8")).hexdigest(), file_registry.get_data_version()


def get_columns(executable_sql: str) -> list[tuple[str, str]]:
    """[(column_name, column_type), ...] for a fully-resolved (file refs
    substituted) query, without executing it - never fetches rows."""
    key = _cache_key(executable_sql)
    cached = _schema_cache.get(key)
    if cached is not None:
        return cached
    columns = duckdb_conn.describe(f"SELECT * FROM ({executable_sql}) AS t")
    _schema_cache[key] = columns
    return columns


def get_column_names(executable_sql: str) -> set[str]:
    return {name for name, _ in get_columns(executable_sql)}
