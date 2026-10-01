from flask import Blueprint, jsonify, request

import config
from build.core import cache, dashboard_store, duckdb_conn, file_registry, query_builder, schema_introspect
from build.core.errors import AppError, NotFoundError
from build.core.query_builder import escape_ident

bp = Blueprint("data", __name__)

ALLOWED_AGGS = {"SUM", "AVG", "COUNT", "MIN", "MAX"}


def _validate_agg(agg: str) -> str:
    agg_upper = agg.upper()
    if agg_upper not in ALLOWED_AGGS:
        raise AppError(f"Unsupported aggregation '{agg}'", status_code=400)
    return agg_upper


def _find_element(dashboard, element_id: str):
    for tab in dashboard.tabs:
        for element in tab.elements:
            if element.id == element_id:
                group = next((g for g in tab.groups if g.id == element.group_id), None) if element.group_id else None
                return tab, group, element
    raise NotFoundError(f"Element '{element_id}' not found")


def _find_filter_element(dashboard, filter_element_id: str):
    for tab in dashboard.tabs:
        for element in tab.elements:
            if element.id == filter_element_id and element.type == "drop_filter":
                return element
    raise NotFoundError(f"Filter element '{filter_element_id}' not found")


def _resolve_query_ref(element, group) -> dict:
    query = getattr(element, "query", None)
    if query is not None:
        return query.model_dump()
    if group is not None and group.shared_query is not None:
        return group.shared_query.model_dump()
    raise AppError(f"Element '{element.id}' has no query and no group shared_query to inherit")


def _is_targeted(filter_element, element_id: str, group_id: str | None) -> bool:
    targets = filter_element.filter.targets
    return element_id in targets.elements or (group_id is not None and group_id in targets.groups)


def _gather_active_filters(dashboard, element, requested_filters: list[dict]) -> list[dict]:
    active_filters = []
    for entry in requested_filters:
        filter_element = _find_filter_element(dashboard, entry["filter_element_id"])
        if not _is_targeted(filter_element, element.id, element.group_id):
            continue  # filter doesn't target this element/group - silently skipped
        active_filters.append(
            {
                "dimension": filter_element.filter.dimension,
                "subtype": filter_element.subtype,
                "values": entry["values"],
            }
        )
    return active_filters


@bp.post("/api/data/element")
def get_element_data():
    body = request.get_json(force=True)

    dashboard = dashboard_store.load(body["dashboard_id"])
    _tab, group, element = _find_element(dashboard, body["element_id"])
    query_ref = _resolve_query_ref(element, group)

    base_sql = query_builder.build_executable_sql(query_ref)
    schema_columns = schema_introspect.get_column_names(base_sql)

    # Element-authored static filters (field_mapping.extra_filters - a config
    # field, like dimension/metrics) apply before the runtime dropdown
    # filters below; charts/tables/cards can have field_mapping, drop_filter
    # elements can't (they have no query of their own to prefilter).
    extra_filters = getattr(element, "field_mapping", None).get("extra_filters", []) if element.type != "drop_filter" else []
    is_pivot = element.type == "table" and element.subtype == "pivot"
    if is_pivot:
        base_sql = query_builder.wrap_with_static_filters_inline(base_sql, extra_filters, schema_columns)
    else:
        base_sql, static_params = query_builder.wrap_with_static_filters(base_sql, extra_filters, schema_columns)

    active_filters = _gather_active_filters(dashboard, element, body.get("active_filters", []))
    if is_pivot:
        # DuckDB's PIVOT rejects parameters in its source when pivot values
        # are auto-detected from the data - inline literals instead.
        filtered_sql, params = query_builder.wrap_with_filters_inline(base_sql, active_filters, schema_columns), []
    else:
        filtered_sql, params = query_builder.wrap_with_filters(base_sql, active_filters, schema_columns)
        params = static_params + params

    sql, meta = _final_sql_for_element(element, filtered_sql, body, schema_columns)

    data_version = file_registry.get_data_version()
    columns, rows = cache.get_or_execute(sql, params, data_version, lambda: duckdb_conn.execute(sql, params))

    if meta.pop("_trim_extra_row", False):
        has_more = len(rows) > meta["page_size"]
        rows = rows[: meta["page_size"]]
        meta["has_more"] = has_more

    return jsonify({"columns": columns, "rows": rows, **meta})


def _require(value, message: str):
    if not value:
        raise AppError(message)
    return value


SORT_DIRECTIONS = {"asc", "desc"}


def _resolve_sort(body: dict, element, available_columns) -> tuple[str, str] | None:
    """Interactive sort (body["sort"], from a header click) takes priority
    over the element's configured default_sort; body["sort"]: null means the
    user explicitly cleared an interactive sort, which must NOT fall back to
    the default - so presence of the key in the request, not its truthiness,
    decides whether to look at default_sort at all. Silently ignored (like
    an unknown filter dimension) if the column isn't sortable or the
    direction is bogus, rather than erroring."""
    sort = body["sort"] if "sort" in body else element.field_mapping.get("default_sort")
    if not sort or not sort.get("column"):
        return None
    column = sort["column"]
    direction = str(sort.get("direction", "asc")).lower()
    if column not in available_columns or direction not in SORT_DIRECTIONS:
        return None
    return column, direction


def _final_sql_for_element(element, filtered_sql: str, body: dict, schema_columns: set[str]) -> tuple[str, dict]:
    if element.type == "card":
        metrics = element.field_mapping.get("metrics", [])
        _require(metrics, f"Element '{element.id}' has no metrics configured yet")
        select_parts = [
            f"{_validate_agg(m['agg'])}({escape_ident(m['field'])}) AS {escape_ident(m['alias'])}" for m in metrics
        ]
        sql = f"SELECT {', '.join(select_parts)} FROM ({filtered_sql}) AS t2"
        return sql, {}

    if element.type == "chart" and element.subtype == "map" and element.field_mapping.get("map_mode") == "point_heatmap":
        lat_field = _require(element.field_mapping.get("lat_field"), f"Map '{element.id}' has no latitude column selected yet")
        lng_field = _require(element.field_mapping.get("lng_field"), f"Map '{element.id}' has no longitude column selected yet")
        metrics = element.field_mapping.get("metrics", [])
        _require(metrics, f"Map '{element.id}' has no value metric configured yet")
        m = metrics[0]
        # Raw GPS lat/lng are essentially never exactly duplicated, so
        # GROUP BY on the bare columns is a near no-op - it returns one row
        # per source point rather than a meaningful density pattern, and
        # ORDER BY value DESC LIMIT N then returns an arbitrary slice (plus
        # whatever rare exact-coordinate collision happens to have the
        # highest count). Rounding to `precision` decimal places first bins
        # nearby points together so the count actually reflects density.
        precision = element.field_mapping.get("bin_precision", config.MAP_HEATMAP_BIN_PRECISION_DEFAULT)
        precision = max(0, min(int(precision), config.MAP_HEATMAP_BIN_PRECISION_MAX))
        lat_expr = f"ROUND({escape_ident(lat_field)}, {precision})"
        lng_expr = f"ROUND({escape_ident(lng_field)}, {precision})"
        value_expr = f"{_validate_agg(m['agg'])}({escape_ident(m['field'])}) AS {escape_ident(m['alias'])}"
        sql = (
            f"SELECT {lat_expr} AS {escape_ident('lat')}, {lng_expr} AS {escape_ident('lng')}, {value_expr} "
            f"FROM ({filtered_sql}) AS t2 GROUP BY {lat_expr}, {lng_expr} "
            f"ORDER BY {escape_ident(m['alias'])} DESC LIMIT {config.MAP_HEATMAP_POINT_LIMIT}"
        )
        return sql, {}

    if element.type == "chart":
        # Region-mode maps reuse this same dimension/metrics GROUP BY path -
        # the region column is stored as field_mapping.dimension (like any
        # other chart's x-axis dimension) and the single value metric as
        # field_mapping.metrics[0], so no map-specific branch is needed here.
        dimension = _require(element.field_mapping.get("dimension"), f"Chart '{element.id}' has no dimension selected yet")
        metrics = element.field_mapping.get("metrics", [])
        _require(metrics, f"Chart '{element.id}' has no metrics configured yet")
        select_parts = [escape_ident(dimension)] + [
            f"{_validate_agg(m['agg'])}({escape_ident(m['field'])}) AS {escape_ident(m['alias'])}" for m in metrics
        ]
        sql = (
            f"SELECT {', '.join(select_parts)} FROM ({filtered_sql}) AS t2 "
            f"GROUP BY {escape_ident(dimension)} ORDER BY {escape_ident(dimension)}"
        )
        return sql, {}

    if element.type == "table" and element.subtype == "pivot":
        rows_cols = _require(element.field_mapping.get("rows"), f"Pivot table '{element.id}' has no row column(s) selected yet")
        columns_col = _require(
            (element.field_mapping.get("columns") or [None])[0], f"Pivot table '{element.id}' has no pivot column selected yet"
        )
        values = _require(element.field_mapping.get("values"), f"Pivot table '{element.id}' has no value metric(s) configured yet")
        value_expr = ", ".join(f"{_validate_agg(v['agg'])}({escape_ident(v['field'])})" for v in values)
        rows_expr = ", ".join(escape_ident(c) for c in rows_cols)
        sql = f"PIVOT ({filtered_sql}) ON {escape_ident(columns_col)} USING {value_expr} GROUP BY {rows_expr}"
        # Only the row-group columns are known ahead of the pivot running (the
        # value columns are data-driven - auto-named from distinct pivot
        # column values), so sorting is limited to those.
        sort = _resolve_sort(body, element, set(rows_cols))
        if sort:
            column, direction = sort
            sql = f"SELECT * FROM ({sql}) AS sorted ORDER BY {escape_ident(column)} {direction.upper()}"
        return sql, {}

    if element.type == "table" and element.subtype == "grouped":
        dimensions = _require(
            element.field_mapping.get("dimensions"), f"Grouped table '{element.id}' has no dimension column(s) selected yet"
        )
        metrics = _require(element.field_mapping.get("metrics"), f"Grouped table '{element.id}' has no metrics configured yet")

        dims_expr = ", ".join(escape_ident(d) for d in dimensions)
        select_parts = [escape_ident(d) for d in dimensions] + [
            f"{_validate_agg(m['agg'])}({escape_ident(m['field'])}) AS {escape_ident(m['alias'])}" for m in metrics
        ]

        page = max(int(body.get("page", 1)), 1)
        page_size = min(int(body.get("page_size", config.DEFAULT_TABLE_PAGE_SIZE)), config.MAX_TABLE_PAGE_SIZE)
        offset = (page - 1) * page_size

        # Only dimensions + metric aliases exist in the aggregated output -
        # unlike the "regular" branch below (which may sort by any underlying
        # schema column), schema_columns are NOT valid sort targets here.
        available_columns = set(dimensions) | {m["alias"] for m in metrics}
        sort = _resolve_sort(body, element, available_columns)
        order_clause = f" ORDER BY {escape_ident(sort[0])} {sort[1].upper()}" if sort else f" ORDER BY {dims_expr}"

        if body.get("show_all"):
            sql = f"SELECT {', '.join(select_parts)} FROM ({filtered_sql}) AS t2 GROUP BY {dims_expr}{order_clause}"
            return sql, {}

        sql = (
            f"SELECT {', '.join(select_parts)} FROM ({filtered_sql}) AS t2 "
            f"GROUP BY {dims_expr}{order_clause} LIMIT {page_size + 1} OFFSET {offset}"
        )
        return sql, {"page": page, "page_size": page_size, "_trim_extra_row": True}

    if element.type == "table":
        page = max(int(body.get("page", 1)), 1)
        page_size = min(int(body.get("page_size", config.DEFAULT_TABLE_PAGE_SIZE)), config.MAX_TABLE_PAGE_SIZE)
        offset = (page - 1) * page_size
        columns = element.field_mapping.get("columns")
        select_clause = ", ".join(escape_ident(c) for c in columns) if columns else "*"
        # ORDER BY may reference any column in the underlying query, even one
        # not in a restricted select_clause - schema_columns (the full query
        # output), not just the displayed subset, is what's actually sortable.
        sort = _resolve_sort(body, element, schema_columns)
        order_clause = f" ORDER BY {escape_ident(sort[0])} {sort[1].upper()}" if sort else ""

        if body.get("show_all"):
            sql = f"SELECT {select_clause} FROM ({filtered_sql}) AS t2{order_clause}"
            return sql, {}

        sql = f"SELECT {select_clause} FROM ({filtered_sql}) AS t2{order_clause} LIMIT {page_size + 1} OFFSET {offset}"
        return sql, {"page": page, "page_size": page_size, "_trim_extra_row": True}

    raise AppError(f"Element type '{element.type}' does not support /api/data/element")


@bp.post("/api/data/filter-options")
def get_filter_options():
    body = request.get_json(force=True)
    dashboard = dashboard_store.load(body["dashboard_id"])
    filter_element = _find_filter_element(dashboard, body["filter_element_id"])

    source_sql = query_builder.build_executable_sql(filter_element.filter.source.model_dump())
    schema_columns = schema_introspect.get_column_names(source_sql)
    options_sql = query_builder.build_filter_options_query(
        filter_element.filter.dimension, source_sql, schema_columns, config.FILTER_OPTIONS_LIMIT
    )

    data_version = file_registry.get_data_version()
    columns, rows = cache.get_or_execute(options_sql, [], data_version, lambda: duckdb_conn.execute(options_sql, []))
    return jsonify({"values": [row[0] for row in rows]})
