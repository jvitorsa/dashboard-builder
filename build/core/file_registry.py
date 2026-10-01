"""Scans context/ for data files (csv/parquet) and .sql files.

No DuckDB views are registered here — this module only tracks *what exists on
disk and where*. Turning a bare filename into something DuckDB can read happens
in query_builder.substitute_file_refs, using the maps this module maintains.
"""

import threading
import time
from pathlib import Path

import config

_lock = threading.Lock()
_data_files: dict[str, dict] = {}
_sql_files: dict[str, dict] = {}
_data_version = 0


def _stat_info(path: Path) -> dict:
    stat = path.stat()
    return {"size_bytes": stat.st_size, "modified_at": stat.st_mtime}


def scan() -> None:
    """Rebuild the registry from the current contents of CONTEXT_DIR."""
    global _data_files, _sql_files, _data_version

    data_files: dict[str, dict] = {}
    sql_files: dict[str, dict] = {}

    if config.CONTEXT_DIR.exists():
        for entry in config.CONTEXT_DIR.iterdir():
            if not entry.is_file():
                continue
            ext = entry.suffix.lower()
            if ext in config.DATA_EXTENSIONS:
                info = _stat_info(entry)
                data_files[entry.name] = {
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "type": ext.lstrip("."),
                    **info,
                }
            elif ext in config.SQL_EXTENSIONS:
                info = _stat_info(entry)
                sql_files[entry.name] = {
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "sql_text": entry.read_text(encoding="utf-8"),
                    **info,
                }

    with _lock:
        _data_files = data_files
        _sql_files = sql_files
        _data_version = int(time.time() * 1000)


def bump_version() -> int:
    global _data_version
    with _lock:
        _data_version = int(time.time() * 1000)
        return _data_version


def get_data_version() -> int:
    with _lock:
        return _data_version


def list_data_files() -> list[dict]:
    with _lock:
        return list(_data_files.values())


def list_sql_files() -> list[dict]:
    with _lock:
        return [{k: v for k, v in f.items() if k != "sql_text"} for f in _sql_files.values()]


def get_data_file_path(filename: str) -> str | None:
    with _lock:
        entry = _data_files.get(filename)
        return entry["path"] if entry else None


def all_data_filenames() -> list[str]:
    with _lock:
        return list(_data_files.keys())


def get_sql_text(filename: str) -> str | None:
    with _lock:
        entry = _sql_files.get(filename)
        return entry["sql_text"] if entry else None


# Populate the registry once at import time so a fresh process is immediately usable.
scan()
