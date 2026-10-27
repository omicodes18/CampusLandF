"""
routes/web_routes.py
User interface web routes serving the Stitch Blush Collegiate HTML templates.
Wires together frontend views with the underlying SQLite database & REST APIs.
"""

from flask import Blueprint, current_app, jsonify, render_template, request

web_bp = Blueprint("web", __name__)


@web_bp.route("/", methods=["GET"])
def index():
    """
    Root route with content negotiation:
    - If accessed by a browser (Accept: text/html): renders the Stitch UI homepage.
    - If accessed by an API client or test runner: returns API JSON metadata.
    """
    accept = request.headers.get("Accept", "")
    format_arg = request.args.get("format")

    if format_arg == "json" or "text/html" not in accept:
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
                "search_by_image": "POST /api/items/search/image",
                "similarity_info": "GET /api/items/similarity/info",
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

    return render_template("index.html", active_page="home")


@web_bp.route("/home", methods=["GET"])
def home():
    """Explicit homepage route."""
    return render_template("index.html", active_page="home")


@web_bp.route("/browse", methods=["GET"])
@web_bp.route("/board", methods=["GET"])
def board():
    """Catalog board page for browsing, searching, and filtering lost/found items."""
    return render_template("board.html", active_page="browse")


@web_bp.route("/report", methods=["GET"])
def report():
    """Report submission form page for lost or found items."""
    report_type = request.args.get("type", "lost")
    active_page = "report_found" if report_type == "found" else "report_lost"
    return render_template("report.html", active_page=active_page)


@web_bp.route("/claims", methods=["GET"])
@web_bp.route("/my-claims", methods=["GET"])
def claims():
    """User ownership claims management page."""
    return render_template("claims.html", active_page="claims")


@web_bp.route("/admin", methods=["GET"])
def admin_panel():
    """Administrative control panel page."""
    return render_template("admin.html", active_page="admin")
