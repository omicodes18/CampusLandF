"""
routes/claim_routes.py
User endpoints for submitting ownership claims and viewing submitted claims.
"""

from flask import Blueprint, jsonify, request, session
from database import get_db
from routes.auth_routes import login_required
from services.claim_service import (
    ClaimValidationError,
    ItemNotFoundError,
    get_claims,
    submit_claim,
)

claim_bp = Blueprint("claims", __name__)


@claim_bp.route("/api/items/<int:item_id>/claims", methods=["POST"])
@login_required
def create_claim(item_id: int):
    """
    Submit an ownership claim for a found item.
    Expects JSON: { proof_details: string }
    Protected: Logged-in user.
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

    proof_details = data.get("proof_details")
    claimant_id = session["user_id"]

    try:
        claim = submit_claim(
            item_id=item_id,
            claimant_id=claimant_id,
            proof_details=proof_details,
        )
    except ItemNotFoundError as exc:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": str(exc),
            }
        }), 404
    except ClaimValidationError as exc:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(exc),
            }
        }), 400

    return jsonify({
        "message": "Claim submitted successfully",
        "claim": claim,
    }), 201


@claim_bp.route("/api/claims/my", methods=["GET"])
@login_required
def my_claims():
    """Retrieve all claims submitted by the currently logged-in user."""
    claimant_id = session["user_id"]
    claims = get_claims(claimant_id=claimant_id)
    return jsonify({"count": len(claims), "claims": claims}), 200


@claim_bp.route("/api/items/<int:item_id>/claims", methods=["GET"])
@login_required
def item_claims(item_id: int):
    """
    Retrieve claims for a specific item.
    Allowed only for: The item's reporter or an Admin.
    """
    user_id = session["user_id"]
    role = session.get("role", "student")

    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": "Item not found.",
            }
        }), 404

    if item["user_id"] != user_id and role != "admin":
        return jsonify({
            "error": {
                "code": 403,
                "name": "Forbidden",
                "message": "You can only view claims for items you reported.",
            }
        }), 403

    claims = get_claims(item_id=item_id)
    return jsonify({"count": len(claims), "claims": claims}), 200
