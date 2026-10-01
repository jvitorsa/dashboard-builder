import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent

CONTEXT_DIR = Path(os.environ.get("DASHBOARD_BUILDER_CONTEXT_DIR", BASE_DIR / "context")).resolve()
BUILD_DIR = Path(os.environ.get("DASHBOARD_BUILDER_BUILD_DIR", BASE_DIR / "build")).resolve()
DASHBOARDS_DIR = BUILD_DIR / "dashboards"
STATIC_DIR = BUILD_DIR / "static"

DATA_EXTENSIONS = {".csv", ".parquet"}
SQL_EXTENSIONS = {".sql"}

# Watcher debounce: settle window before a filesystem change bumps data_version,
# so a parquet/csv file mid-write doesn't get read half-finished.
WATCH_DEBOUNCE_SECONDS = 0.4

# Result/schema LRU cache sizes. Entries key on data_version, so they naturally
# stop being reachable (and get evicted) the moment the underlying files change.
SCHEMA_CACHE_SIZE = 256
RESULT_CACHE_SIZE = 128

MAX_TABLE_PAGE_SIZE = 1000
DEFAULT_TABLE_PAGE_SIZE = 500
FILTER_OPTIONS_LIMIT = 1000
# Cap on (lat,lng) groups returned for a point-heatmap map element - keeps
# browser-side heatmap rendering fast even against a 10M-row source.
MAP_HEATMAP_POINT_LIMIT = 5000
# Clamp for field_mapping.bin_precision (decimal places lat/lng are rounded
# to before GROUP BY) - real GPS data is almost never exactly duplicated, so
# without binning the group-by is a near no-op and the density pattern is
# lost; 4 decimals (~11m bins) is already finer than useful.
MAP_HEATMAP_BIN_PRECISION_MAX = 4
MAP_HEATMAP_BIN_PRECISION_DEFAULT = 1

# Two separate Flask apps: the builder (build/builder.py, the editing tool)
# and the viewer (app.py, the finished read-only dashboard) run on different
# ports so both can be up at once without colliding.
VIEWER_PORT = int(os.environ.get("DASHBOARD_BUILDER_VIEWER_PORT", 5000))
BUILDER_PORT = int(os.environ.get("DASHBOARD_BUILDER_BUILDER_PORT", 5050))

DASHBOARDS_DIR.mkdir(parents=True, exist_ok=True)
