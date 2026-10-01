"""Entry point for the dashboard VIEWER - the finished, read-only output.

Run with: python app.py
Renders dashboards saved as JSON by the builder (build/builder.py). No
editing here - add/configure elements and save changes in the builder; this
app just reads the same context/ data and build/dashboards/*.json files and
displays them, with working filters and live-reload.
"""

from flask import Flask, send_from_directory

import config
from build.api.dashboards import bp as dashboards_bp
from build.api.data import bp as data_bp
from build.api.version import bp as version_bp
from build.core import watcher
from build.core.errors import register_error_handlers


def create_app() -> Flask:
    app = Flask(__name__, static_folder=str(config.STATIC_DIR), static_url_path="/static")

    register_error_handlers(app)

    app.register_blueprint(version_bp)
    app.register_blueprint(dashboards_bp)
    app.register_blueprint(data_bp)

    @app.get("/")
    def index():
        return send_from_directory(config.STATIC_DIR / "viewer", "index.html")

    watcher.start()

    return app


app = create_app()

if __name__ == "__main__":
    app.run(port=config.VIEWER_PORT, debug=True, use_reloader=False)
