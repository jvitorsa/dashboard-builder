from pydantic import ValidationError
from werkzeug.exceptions import HTTPException


class AppError(Exception):
    """Base class for errors that should be surfaced to the client as JSON."""

    status_code = 400

    def __init__(self, message: str, *, status_code: int | None = None, details=None):
        super().__init__(message)
        self.message = message
        if status_code is not None:
            self.status_code = status_code
        self.details = details


class NotFoundError(AppError):
    status_code = 404


class FileNotRegisteredError(AppError):
    status_code = 404


class DimensionNotFoundError(AppError):
    status_code = 400


class NameConflictError(AppError):
    status_code = 409


def register_error_handlers(app):
    @app.errorhandler(AppError)
    def handle_app_error(err: AppError):
        payload = {"error": err.message}
        if err.details is not None:
            payload["details"] = err.details
        return payload, err.status_code

    @app.errorhandler(ValidationError)
    def handle_validation_error(err: ValidationError):
        return {"error": "validation_failed", "details": err.errors()}, 400

    @app.errorhandler(Exception)
    def handle_unexpected_error(err: Exception):
        # Surface unforeseen failures (a bad DuckDB query, etc.) as JSON with
        # the real message, instead of Flask's generic HTML 500 page - this is
        # a local single-user tool, so showing the actual error is more useful
        # than hiding it. HTTPExceptions (404s, etc.) pass through unchanged.
        if isinstance(err, HTTPException):
            return err
        return {"error": "internal_error", "details": str(err)}, 500
