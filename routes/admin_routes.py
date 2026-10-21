"""
routes/admin_routes.py
Admin endpoints protected by role-based access control.
Provides user management, report review, claim approval/rejection, and item status transitions.
"""

from flask import Blueprint, jsonify, request
from database import get_db
from routes.auth_routes import admin_required
from services.auth_service import get_all_users
from services.claim_service import (
    ClaimNotFoundError,
    ClaimValidationError,
    InvalidStatusTransitionError,
    ItemNotFoundError,
    get_claims,
    review_claim,
    update_item_status,
)
from services.item_service import get_items

admin_bp = Blueprint("admin", __name__, url_prefix="/api/admin")


@admin_bp.route("/users", methods=["GET"])
@admin_required
def list_all_users():
    """List all registered users (passwords omitted)."""
    users = get_all_users()
    return jsonify({
        "count": len(users),
        "users": users,
    }), 200


@admin_bp.route("/stats", methods=["GET"])
@admin_required
def get_system_stats():
    """Return overview statistics for the platform."""
    db = get_db()
    users_count = db.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    items_count = db.execute("SELECT COUNT(*) FROM items").fetchone()[0]
    claims_count = db.execute("SELECT COUNT(*) FROM claims").fetchone()[0]
    notifs_count = db.execute("SELECT COUNT(*) FROM notifications").fetchone()[0]

    return jsonify({
        "stats": {
            "total_users": users_count,
            "total_items": items_count,
            "total_claims": claims_count,
            "total_notifications": notifs_count,
        }
    }), 200


@admin_bp.route("/reports", methods=["GET"])
@admin_required
def review_reports():
    """
    Review all submitted lost and found reports.
    Supports query parameters: type, category, status.
    """
    item_type = request.args.get("type")
    category = request.args.get("category")
    status = request.args.get("status")

    items = get_items(item_type=item_type, category=category, status=status)
    return jsonify({
        "count": len(items),
        "items": items,
    }), 200


@admin_bp.route("/claims", methods=["GET"])
@admin_required
def list_all_claims():
    """
    List all ownership claims across items.
    Supports query parameters: status, item_id.
    """
    status = request.args.get("status")
    item_id = request.args.get("item_id", type=int)

    claims = get_claims(status=status, item_id=item_id)
    return jsonify({
        "count": len(claims),
        "claims": claims,
    }), 200


@admin_bp.route("/claims/<int:claim_id>/approve", methods=["POST"])
@admin_required
def approve_claim(claim_id: int):
    """
    Approve an ownership claim.
    Transitions claim to 'approved' and item to 'claimed'.
    Rejects other pending claims on the same item.
    """
    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")

    try:
        updated_claim = review_claim(
            claim_id=claim_id,
            new_status="approved",
            admin_notes=admin_notes,
        )
    except ClaimNotFoundError as exc:
        return jsonify({"error": {"code": 404, "name": "Not Found", "message": str(exc)}}), 404
    except (InvalidStatusTransitionError, ClaimValidationError) as exc:
        return jsonify({"error": {"code": 400, "name": "Bad Request", "message": str(exc)}}), 400

    return jsonify({
        "message": "Claim approved successfully",
        "claim": updated_claim,
    }), 200


@admin_bp.route("/claims/<int:claim_id>/reject", methods=["POST"])
@admin_required
def reject_claim(claim_id: int):
    """
    Reject an ownership claim with optional feedback notes.
    Transitions claim to 'rejected'.
    """
    data = request.get_json(silent=True) or {}
    admin_notes = data.get("admin_notes")

    try:
        updated_claim = review_claim(
            claim_id=claim_id,
            new_status="rejected",
            admin_notes=admin_notes,
        )
    except ClaimNotFoundError as exc:
        return jsonify({"error": {"code": 404, "name": "Not Found", "message": str(exc)}}), 404
    except (InvalidStatusTransitionError, ClaimValidationError) as exc:
        return jsonify({"error": {"code": 400, "name": "Bad Request", "message": str(exc)}}), 400

    return jsonify({
        "message": "Claim rejected successfully",
        "claim": updated_claim,
    }), 200


@admin_bp.route("/claims/<int:claim_id>", methods=["PUT", "PATCH"])
@admin_required
def update_claim_review(claim_id: int):
    """
    Unified endpoint to approve or reject a claim.
    Expects JSON: { status: 'approved' | 'rejected', admin_notes: string (optional) }
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

    status = data.get("status")
    admin_notes = data.get("admin_notes")

    try:
        updated_claim = review_claim(
            claim_id=claim_id,
            new_status=status,
            admin_notes=admin_notes,
        )
    except ClaimNotFoundError as exc:
        return jsonify({"error": {"code": 404, "name": "Not Found", "message": str(exc)}}), 404
    except (InvalidStatusTransitionError, ClaimValidationError) as exc:
        return jsonify({"error": {"code": 400, "name": "Bad Request", "message": str(exc)}}), 400

    return jsonify({
        "message": f"Claim {status} successfully",
        "claim": updated_claim,
    }), 200


@admin_bp.route("/items/<int:item_id>/status", methods=["PUT", "PATCH"])
@admin_required
def update_report_status(item_id: int):
    """
    Update item status directly (e.g. to 'returned' or 'resolved').
    Expects JSON: { status: 'returned' | 'resolved' | 'open' | 'claimed', admin_notes: string (optional) }
    Enforces valid status transitions.
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

    status = data.get("status")
    admin_notes = data.get("admin_notes")

    try:
        updated_item = update_item_status(
            item_id=item_id,
            new_status=status,
            admin_notes=admin_notes,
        )
    except ItemNotFoundError as exc:
        return jsonify({"error": {"code": 404, "name": "Not Found", "message": str(exc)}}), 404
    except (InvalidStatusTransitionError, ClaimValidationError) as exc:
        return jsonify({"error": {"code": 400, "name": "Bad Request", "message": str(exc)}}), 400

    return jsonify({
        "message": "Item status updated successfully",
        "item": updated_item,
    }), 200
