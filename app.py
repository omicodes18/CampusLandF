"""
app.py
College Lost & Found Management System - Flask Application Entrypoint & Factory.

Features:
- Application factory pattern (create_app)
- Configuration management (.env and environment variables)
- SQLite database initialization and registration
- Error handling with structured JSON responses
- Health check and modular blueprint routing
"""

import os
import logging
from flask import Flask, jsonify

# Attempt to load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.isfile(env_path):
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, val = line.split("=", 1)
                    os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))

import database
from routes import admin_bp, auth_bp, claim_bp, health_bp, items_bp


def create_app(test_config=None):
    """
    Application factory pattern to configure and instantiate the Flask app.
    Enables isolated instances for production, development, and automated testing.
    """
    app = Flask(__name__, instance_relative_config=True)

    # Base configuration
    secret_key = os.environ.get("SECRET_KEY")
    if not secret_key:
        secret_key = "dev-insecure-key-change-in-production"
        if os.environ.get("FLASK_ENV") == "production":
            logging.warning("CRITICAL: Running in production without a secure SECRET_KEY set!")

    default_db_path = os.path.join(app.instance_path, "lost_and_found.db")
    upload_dir = os.path.join(app.root_path, "uploads")

    app.config.from_mapping(
        SECRET_KEY=secret_key,
        DATABASE=os.environ.get("DATABASE", default_db_path),
        UPLOAD_FOLDER=os.environ.get("UPLOAD_FOLDER", upload_dir),
        MAX_CONTENT_LENGTH=int(os.environ.get("MAX_CONTENT_LENGTH", 16 * 1024 * 1024)),
        # Secure session cookie configurations
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("FLASK_ENV") == "production",
    )

    # Override configuration for unit testing if provided
    if test_config is not None:
        app.config.from_mapping(test_config)

    # Ensure instance and upload directories exist
    os.makedirs(app.instance_path, exist_ok=True)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    # Register database teardown and CLI commands
    database.init_app(app)

    # Auto-initialize database tables on first launch if not yet created
    with app.app_context():
        try:
            database.init_db()
        except Exception as exc:
            app.logger.warning("Auto DB initialization notice: %s", exc)

    # Register Route Blueprints
    app.register_blueprint(health_bp)
    app.register_blueprint(auth_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(claim_bp)
    app.register_blueprint(items_bp)

    # Root informational route
    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "project": "College Lost & Found Management System API",
            "version": "1.0.0",
            "status": "online",
            "health_check": "/api/health",
            "endpoints": {
                "health": "/api/health",
                "auth_register": "POST /api/auth/register",
                "auth_login": "POST /api/auth/login",
                "auth_logout": "POST /api/auth/logout",
                "auth_me": "GET /api/auth/me",
                "notifications": "GET /api/auth/notifications",
                "notification_read": "PATCH /api/auth/notifications/<id>/read",
                "items": "GET /api/items",
                "report_item": "POST /api/items",
                "item_detail": "GET /api/items/<id>",
                "claims": "POST /api/items/<id>/claims",
                "my_claims": "GET /api/claims/my",
                "admin_users": "GET /api/admin/users",
                "admin_stats": "GET /api/admin/stats",
                "admin_claims": "GET /api/admin/claims",
                "admin_reports": "GET /api/admin/reports",
                "admin_approve_claim": "POST /api/admin/claims/<id>/approve",
                "admin_reject_claim": "POST /api/admin/claims/<id>/reject",
                "admin_item_status": "PATCH /api/admin/items/<id>/status",
            },
        }), 200

    # Structured JSON error handlers
    @app.errorhandler(400)
    def bad_request(error):
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": getattr(error, "description", "The request could not be understood or was missing required parameters."),
            }
        }), 400

    @app.errorhandler(404)
    def not_found(error):
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": getattr(error, "description", "The requested resource was not found on this server."),
            }
        }), 404

    @app.errorhandler(405)
    def method_not_allowed(error):
        return jsonify({
            "error": {
                "code": 405,
                "name": "Method Not Allowed",
                "message": getattr(error, "description", "The HTTP method is not allowed for this endpoint."),
            }
        }), 405

    @app.errorhandler(500)
    def internal_server_error(error):
        return jsonify({
            "error": {
                "code": 500,
                "name": "Internal Server Error",
                "message": "An unexpected error occurred on the server.",
            }
        }), 500

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.environ.get("PORT", 5001))
    print(f"Starting College Lost & Found backend on http://127.0.0.1:{port}")
    app.run(host="127.0.0.1", port=port, debug=True)
