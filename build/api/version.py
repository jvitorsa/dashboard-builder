from flask import Blueprint, jsonify

from build.core import file_registry

bp = Blueprint("version", __name__)


@bp.get("/api/version")
def get_version():
    return jsonify({"data_version": file_registry.get_data_version()})
