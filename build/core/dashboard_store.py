import json
import uuid
from datetime import datetime, timezone

import config
from build.core.errors import NotFoundError
from build.core.models import Dashboard, DashboardSummary


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _path_for(dashboard_id: str):
    return config.DASHBOARDS_DIR / f"{dashboard_id}.json"


def list_dashboards() -> list[DashboardSummary]:
    summaries = []
    for path in sorted(config.DASHBOARDS_DIR.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        summaries.append(DashboardSummary(id=raw.get("id", path.stem), name=raw.get("name", path.stem), updated_at=raw.get("updated_at")))
    return summaries


def load(dashboard_id: str) -> Dashboard:
    path = _path_for(dashboard_id)
    if not path.exists():
        raise NotFoundError(f"Dashboard '{dashboard_id}' not found")
    raw = json.loads(path.read_text(encoding="utf-8"))
    return Dashboard.model_validate(raw)


def create(data: dict) -> Dashboard:
    data = dict(data)
    data["id"] = data.get("id") or f"dash_{uuid.uuid4().hex[:12]}"
    now = _now()
    data["created_at"] = now
    data["updated_at"] = now
    dashboard = Dashboard.model_validate(data)
    _write(dashboard)
    return dashboard


def save(dashboard_id: str, data: dict) -> Dashboard:
    path = _path_for(dashboard_id)
    if not path.exists():
        raise NotFoundError(f"Dashboard '{dashboard_id}' not found")
    data = dict(data)
    data["id"] = dashboard_id
    existing = json.loads(path.read_text(encoding="utf-8"))
    data["created_at"] = existing.get("created_at", _now())
    data["updated_at"] = _now()
    dashboard = Dashboard.model_validate(data)
    _write(dashboard)
    return dashboard


def delete(dashboard_id: str) -> None:
    path = _path_for(dashboard_id)
    if not path.exists():
        raise NotFoundError(f"Dashboard '{dashboard_id}' not found")
    path.unlink()


def duplicate(dashboard_id: str, new_name: str | None = None) -> Dashboard:
    original = load(dashboard_id)
    data = original.model_dump(mode="json")
    data.pop("id", None)
    data["name"] = new_name or f"{original.name} (copy)"
    return create(data)


def _write(dashboard: Dashboard) -> None:
    path = _path_for(dashboard.id)
    path.write_text(json.dumps(dashboard.model_dump(mode="json"), indent=2), encoding="utf-8")
