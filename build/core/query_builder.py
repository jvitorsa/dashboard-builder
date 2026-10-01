"""Turns user-authored SQL (referencing bare filenames) into something DuckDB
can execute, and applies filter predicates on top - without ever string-
splicing untrusted identifiers into SQL text.

Pipeline for any element: substitute_file_refs(raw_sql) -> wrap_with_filters(...) -> execute.
"""

import re

from build.core import file_registry
from build.core.errors import DimensionNotFoundError, FileNotRegisteredError


def _sql_string_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def escape_ident(identifier: str) -> str:
    return '"' + identifier.replace('"', '""') + '"'


def substitute_file_refs(sql_text: str) -> str:
    """Replace registered filenames with a quoted absolute-path string
    literal, so DuckDB's replacement scan reads the right file regardless of
    process cwd. Handles both bare references (e.g. customer_master.csv,
    matching the convention from the user's own sample query) and quoted
    ones (e.g. 'online food delivery dataset.csv') - quoting is the only way
    to reference a filename containing spaces at all, and a bare quoted
    filename with no path prefix would otherwise resolve relative to the
    server process's cwd rather than context/, silently failing to find it."""
    result = sql_text
    for filename in file_registry.all_data_filenames():
        path = file_registry.get_data_file_path(filename)
        if not path:
            continue
        literal = _sql_string_literal(path.replace("\\", "/"))
        escaped_name = re.escape(filename)
        # Whole quoted token (the entire quoted content is just the filename,
        # not the filename as a suffix of some other longer quoted string).
        quoted_pattern = re.compile(r"(['\"])" + escaped_name + r"\1")
        result = quoted_pattern.sub(lambda _m: literal, result)
        # Bare token, not touching one already resolved by the quoted pass.
        bare_pattern = re.compile(r"(?<!['\"])\b" + escaped_name + r"\b(?!['\"])")
        result = bare_pattern.sub(lambda _m: literal, result)
    return result


def find_referenced_data_files(sql_text: str) -> set[str]:
    """Which registered data filenames does this SQL text actually reference
    (bare or quoted, same matching rules as substitute_file_refs) - used to
    figure out what to bundle when exporting a dashboard, without mutating
    the SQL itself."""
    found: set[str] = set()
    for filename in file_registry.all_data_filenames():
        escaped_name = re.escape(filename)
        quoted_pattern = re.compile(r"(['\"])" + escaped_name + r"\1")
        bare_pattern = re.compile(r"(?<!['\"])\b" + escaped_name + r"\b(?!['\"])")
        if quoted_pattern.search(sql_text) or bare_pattern.search(sql_text):
            found.add(filename)
    return found


def resolve_query_text(query_ref: dict) -> str:
    """query_ref: {"mode": "file", "path": "sales.sql"} or {"mode": "inline", "sql": "..."}.
    Returns the raw user SQL text, before file-ref substitution."""
    mode = query_ref.get("mode")
    if mode == "file":
        path = query_ref["path"]
        sql_text = file_registry.get_sql_text(path)
        if sql_text is None:
            raise FileNotRegisteredError(f"SQL file '{path}' not found in context/")
        return sql_text
    if mode == "inline":
        return query_ref["sql"]
    raise ValueError(f"Unknown query mode: {mode!r}")


def build_executable_sql(query_ref: dict) -> str:
    """Resolve a query_ref to fully executable SQL (file refs substituted),
    with no filters applied yet."""
    return substitute_file_refs(resolve_query_text(query_ref))


def wrap_with_filters(base_sql: str, filters: list, schema_columns: set[str]) -> tuple[str, list]:
    """filters: dicts with dimension, subtype ('single'|'multiselect'), values (list).
    Only filters whose dimension is present in schema_columns are applied -
    a filter targeting an element whose query doesn't expose that column is
    silently skipped rather than erroring."""
    applicable = [f for f in filters if f["dimension"] in schema_columns]
    if not applicable:
        return base_sql, []

    where_parts: list[str] = []
    params: list = []
    for f in applicable:
        ident = escape_ident(f["dimension"])
        values = f["values"]
        if f["subtype"] == "single":
            where_parts.append(f"{ident} = ?")
            params.append(values[0])
        else:  # multiselect
            placeholders = ",".join(["?"] * len(values))
            where_parts.append(f"{ident} IN ({placeholders})")
            params.extend(values)

    sql = f"SELECT * FROM ({base_sql}) AS t WHERE {' AND '.join(where_parts)}"
    return sql, params


def wrap_with_filters_inline(base_sql: str, filters: list, schema_columns: set[str]) -> str:
    """Same filtering as wrap_with_filters, but with escaped literal values
    inlined instead of parameter placeholders. DuckDB's PIVOT rejects any `?`
    parameter in its source when pivot values are auto-detected from the data
    ("PIVOT statements with pivot elements extracted from the data cannot
    have parameters in their source"), so the pivot code path needs this
    instead of the parameterized version. Values are still safe: escaped as
    single-quoted string literals, and DuckDB implicitly casts them against
    numeric columns the same way it does for bound parameters."""
    applicable = [f for f in filters if f["dimension"] in schema_columns]
    if not applicable:
        return base_sql

    where_parts: list[str] = []
    for f in applicable:
        ident = escape_ident(f["dimension"])
        values = f["values"]
        if f["subtype"] == "single":
            where_parts.append(f"{ident} = {_sql_string_literal(str(values[0]))}")
        else:  # multiselect
            literals = ",".join(_sql_string_literal(str(v)) for v in values)
            where_parts.append(f"{ident} IN ({literals})")

    return f"SELECT * FROM ({base_sql}) AS t WHERE {' AND '.join(where_parts)}"


STATIC_FILTER_OPERATORS = {"=", "!=", ">", "<", ">=", "<="}


def wrap_with_static_filters(base_sql: str, filters: list, schema_columns: set[str]) -> tuple[str, list]:
    """Element-authored "WHERE column op value" filters (field_mapping.extra_filters
    - a chart/table/card config, not a runtime dropdown filter). filters: dicts
    with field, op (one of STATIC_FILTER_OPERATORS), value. Same skip-if-unknown-
    column and bound-parameter approach as wrap_with_filters."""
    applicable = [f for f in filters if f.get("field") in schema_columns and f.get("op") in STATIC_FILTER_OPERATORS]
    if not applicable:
        return base_sql, []

    where_parts: list[str] = []
    params: list = []
    for f in applicable:
        ident = escape_ident(f["field"])
        where_parts.append(f"{ident} {f['op']} ?")
        params.append(f["value"])

    sql = f"SELECT * FROM ({base_sql}) AS t WHERE {' AND '.join(where_parts)}"
    return sql, params


def wrap_with_static_filters_inline(base_sql: str, filters: list, schema_columns: set[str]) -> str:
    """Same as wrap_with_static_filters but with escaped literal values inlined
    instead of parameters - needed ahead of a PIVOT, which rejects `?` params
    in its source (see wrap_with_filters_inline)."""
    applicable = [f for f in filters if f.get("field") in schema_columns and f.get("op") in STATIC_FILTER_OPERATORS]
    if not applicable:
        return base_sql

    where_parts = [f"{escape_ident(f['field'])} {f['op']} {_sql_string_literal(str(f['value']))}" for f in applicable]
    return f"SELECT * FROM ({base_sql}) AS t WHERE {' AND '.join(where_parts)}"


def build_filter_options_query(dimension: str, source_sql: str, schema_columns: set[str], limit: int) -> str:
    if dimension not in schema_columns:
        raise DimensionNotFoundError(f"Column '{dimension}' not found in the filter's source query")
    ident = escape_ident(dimension)
    return f"SELECT DISTINCT {ident} FROM ({source_sql}) AS t ORDER BY {ident} LIMIT {int(limit)}"
