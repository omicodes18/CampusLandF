"""
routes/auth_routes.py
Authentication endpoints and role-based access control decorators.
Implements registration, login, logout, profile retrieval, and session management.
"""

from functools import wraps
from flask import Blueprint, jsonify, request, session
from services.auth_service import (
    AuthValidationError,
    DuplicateUserError,
    authenticate_user,
    create_user,
    get_user_by_id,
)

auth_bp = Blueprint("auth", __name__, url_prefix="/api/auth")


def login_required(f):
    """Decorator to require that a user is actively authenticated via session."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "error": {
                    "code": 401,
                    "name": "Unauthorized",
                    "message": "Authentication required. Please log in.",
                }
            }), 401

        user = get_user_by_id(session["user_id"])
        if not user:
            session.clear()
            return jsonify({
                "error": {
                    "code": 401,
                    "name": "Unauthorized",
                    "message": "User session is no longer valid. Please log in again.",
                }
            }), 401

        return f(*args, **kwargs)
    return decorated_function


def admin_required(f):
    """Decorator to require administrator privileges."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if "user_id" not in session:
            return jsonify({
                "error": {
                    "code": 401,
                    "name": "Unauthorized",
                    "message": "Authentication required. Please log in.",
                }
            }), 401

        user = get_user_by_id(session["user_id"])
        if not user:
            session.clear()
            return jsonify({
                "error": {
                    "code": 401,
                    "name": "Unauthorized",
                    "message": "User session is no longer valid. Please log in again.",
                }
            }), 401

        if user.get("role") != "admin":
            return jsonify({
                "error": {
                    "code": 403,
                    "name": "Forbidden",
                    "message": "Access forbidden: admin privileges required.",
                }
            }), 403

        return f(*args, **kwargs)
    return decorated_function


@auth_bp.route("/register", methods=["POST"])
def register():
    """
    Register a new user account.
    Expects JSON body: { name, email, password, role (optional), phone (optional) }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": "Request payload must be valid JSON.",
            }
        }), 400

    name = data.get("name")
    email = data.get("email")
    password = data.get("password")
    role = data.get("role", "student")
    phone = data.get("phone")

    try:
        user = create_user(
            name=name,
            email=email,
            password=password,
            role=role,
            phone=phone,
        )
    except DuplicateUserError as exc:
        return jsonify({
            "error": {
                "code": 409,
                "name": "Conflict",
                "message": str(exc),
            }
        }), 409
    except AuthValidationError as exc:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(exc),
            }
        }), 400

    return jsonify({
        "message": "User registered successfully",
        "user": user,
    }), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    """
    Authenticate user and create a secure server-side session.
    Expects JSON body: { email, password }
    """
    data = request.get_json(silent=True)
    if not data or not isinstance(data, dict):
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": "Request payload must be valid JSON.",
            }
        }), 400

    email = data.get("email")
    password = data.get("password")

    if not email or not password:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": "Email and password are required.",
            }
        }), 400

    user = authenticate_user(email, password)
    if not user:
        return jsonify({
            "error": {
                "code": 401,
                "name": "Unauthorized",
                "message": "Invalid email or password.",
            }
        }), 401

    # Clear previous session to prevent session fixation attacks
    session.clear()
    session["user_id"] = user["id"]
    session["role"] = user["role"]
    session["name"] = user["name"]
    session["email"] = user["email"]

    return jsonify({
        "message": "Login successful",
        "user": user,
    }), 200


@auth_bp.route("/logout", methods=["POST"])
def logout():
    """Clear session data and log out the current user."""
    session.clear()
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route("/me", methods=["GET"])
@login_required
def get_current_user():
    """Retrieve details of the currently authenticated user."""
    user = get_user_by_id(session["user_id"])
    if not user:
        session.clear()
        return jsonify({
            "error": {
                "code": 401,
                "name": "Unauthorized",
                "message": "User session is no longer valid.",
            }
        }), 401

    return jsonify({"user": user}), 200


@auth_bp.route("/notifications", methods=["GET"])
@login_required
def list_notifications():
    """Retrieve all notifications for the authenticated user."""
    from database import get_db
    from models import notification_to_dict

    db = get_db()
    rows = db.execute(
        "SELECT * FROM notifications WHERE user_id = ? ORDER BY created_at DESC",
        (session["user_id"],),
    ).fetchall()

    notifs = [notification_to_dict(r) for r in rows]
    return jsonify({"count": len(notifs), "notifications": notifs}), 200


@auth_bp.route("/notifications/<int:notif_id>/read", methods=["PATCH", "POST"])
@login_required
def mark_notification_read(notif_id: int):
    """Mark a notification as read."""
    from database import get_db

    db = get_db()
    notif = db.execute(
        "SELECT * FROM notifications WHERE id = ? AND user_id = ?",
        (notif_id, session["user_id"]),
    ).fetchone()

    if not notif:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": "Notification not found.",
            }
        }), 404

    db.execute("UPDATE notifications SET is_read = 1 WHERE id = ?", (notif_id,))
    db.commit()

    return jsonify({"message": "Notification marked as read"}), 200
