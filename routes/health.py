"""
routes/health.py
Health check endpoint verifying API service status and database connectivity.
"""

from datetime import datetime, timezone
from flask import Blueprint, jsonify
from database import check_db_connection

health_bp = Blueprint("health", __name__)


@health_bp.route("/health", methods=["GET"])
@health_bp.route("/api/health", methods=["GET"])
def health_check():
    """
    Health check endpoint.
    Verifies that the Flask web server is active and the SQLite database is reachable.
    """
    db_ok, db_message = check_db_connection()

    payload = {
        "status": "healthy" if db_ok else "unhealthy",
        "service": "College Lost & Found Management API",
        "version": "1.0.0",
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "database": {
            "status": "connected" if db_ok else "disconnected",
            "type": "SQLite",
            "message": db_message,
        },
    }

    status_code = 200 if db_ok else 503
    return jsonify(payload), status_code
