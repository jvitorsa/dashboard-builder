"""Single process-wide DuckDB connection.

DuckDB connections are not thread-safe to share directly across concurrent
requests, but cursor() handles derived from one connection are - they share
the catalog (nothing needs re-registering per request) while each getting an
independent execution context. Flask's dev server runs single-process, so one
global connection is exactly right here (see PLAN.md "Known Risks").
"""

import duckdb

_conn = duckdb.connect(database=":memory:")


def get_cursor():
    return _conn.cursor()


def execute(sql: str, params: list | None = None):
    """Run sql (already fully built - filenames substituted, filters wrapped)
    and return (columns, rows) as plain Python values."""
    cur = get_cursor()
    try:
        result = cur.execute(sql, params or [])
        columns = [d[0] for d in result.description]
        rows = result.fetchall()
        return columns, rows
    finally:
        cur.close()


def describe(sql: str) -> list[tuple[str, str]]:
    """Return [(column_name, column_type), ...] for a query without fetching rows."""
    columns, rows = execute(f"DESCRIBE {sql}")
    name_idx = columns.index("column_name")
    type_idx = columns.index("column_type")
    return [(row[name_idx], row[type_idx]) for row in rows]
