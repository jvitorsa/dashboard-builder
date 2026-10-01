from flask import Blueprint, jsonify, request

from build.core import dashboard_store

bp = Blueprint("dashboards", __name__)


@bp.get("/api/dashboards")
def list_dashboards():
    summaries = dashboard_store.list_dashboards()
    return jsonify({"dashboards": [s.model_dump(mode="json") for s in summaries]})


@bp.post("/api/dashboards")
def create_dashboard():
    body = request.get_json(force=True)
    dashboard = dashboard_store.create(body)
    return jsonify({"id": dashboard.id}), 201


@bp.get("/api/dashboards/<dashboard_id>")
def get_dashboard(dashboard_id: str):
    dashboard = dashboard_store.load(dashboard_id)
    return jsonify(dashboard.model_dump(mode="json"))


@bp.put("/api/dashboards/<dashboard_id>")
def update_dashboard(dashboard_id: str):
    body = request.get_json(force=True)
    dashboard = dashboard_store.save(dashboard_id, body)
    return jsonify(dashboard.model_dump(mode="json"))


@bp.delete("/api/dashboards/<dashboard_id>")
def delete_dashboard(dashboard_id: str):
    dashboard_store.delete(dashboard_id)
    return "", 204


@bp.post("/api/dashboards/<dashboard_id>/duplicate")
def duplicate_dashboard(dashboard_id: str):
    body = request.get_json(silent=True) or {}
    dashboard = dashboard_store.duplicate(dashboard_id, body.get("new_name"))
    return jsonify({"id": dashboard.id}), 201
