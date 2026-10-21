"""
routes/item_routes.py
API endpoints for lost & found item reporting, filtering, searching, updates, and uploads.
Enforces that users can only edit or delete their own reported items.
"""

from flask import Blueprint, current_app, jsonify, request, send_from_directory, session
from routes.auth_routes import login_required
from services.item_service import (
    ItemNotFoundError,
    ItemValidationError,
    UnauthorizedActionError,
    delete_item,
    get_item_by_id,
    get_items,
    report_item,
    update_item,
)

items_bp = Blueprint("items", __name__)


def extract_item_payload(req):
    """
    Helper to extract fields from either multipart/form-data or application/json.
    Returns (data_dict, image_file).
    """
    if req.is_json:
        return req.get_json() or {}, None

    # Handle multipart/form-data or URL-encoded form
    data = req.form.to_dict() if req.form else {}
    image_file = req.files.get("image") if req.files else None
    return data, image_file


@items_bp.route("/api/items", methods=["GET"])
def list_items():
    """
    List items with optional search and filters:
    - type: lost | found
    - category: e.g. Electronics, Books & Stationery
    - location: e.g. Library, Canteen
    - status: open | claimed | resolved
    - q or search: search keyword matching title, description, or location
    """
    item_type = request.args.get("type")
    category = request.args.get("category")
    location = request.args.get("location")
    status = request.args.get("status")
    search = request.args.get("q") or request.args.get("search")

    items = get_items(
        item_type=item_type,
        category=category,
        location=location,
        status=status,
        search=search,
    )
    return jsonify({"count": len(items), "items": items}), 200


@items_bp.route("/api/items/<int:item_id>", methods=["GET"])
def get_item(item_id: int):
    """Retrieve details of a single lost/found item by ID."""
    item = get_item_by_id(item_id)
    if not item:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": "Item not found.",
            }
        }), 404
    return jsonify({"item": item}), 200


@items_bp.route("/api/items", methods=["POST"])
@login_required
def create_item():
    """
    Report a lost or found item.
    Supports JSON or multipart/form-data (for file uploads).
    Protected: User authentication required.
    """
    data, image_file = extract_item_payload(request)
    user_id = session["user_id"]
    upload_folder = current_app.config["UPLOAD_FOLDER"]

    try:
        created_item = report_item(
            data=data,
            user_id=user_id,
            image_file=image_file,
            upload_folder=upload_folder,
        )
    except ItemValidationError as exc:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(exc),
            }
        }), 400

    return jsonify({
        "message": "Item reported successfully",
        "item": created_item,
    }), 201


@items_bp.route("/api/items/<int:item_id>", methods=["PUT", "PATCH"])
@login_required
def modify_item(item_id: int):
    """
    Update an existing item report.
    Protected: Users can only edit their own reports; Admins can edit any report.
    """
    data, image_file = extract_item_payload(request)
    user_id = session["user_id"]
    user_role = session.get("role", "student")
    upload_folder = current_app.config["UPLOAD_FOLDER"]

    try:
        updated_item = update_item(
            item_id=item_id,
            user_id=user_id,
            user_role=user_role,
            data=data,
            image_file=image_file,
            upload_folder=upload_folder,
        )
    except ItemNotFoundError as exc:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": str(exc),
            }
        }), 404
    except UnauthorizedActionError as exc:
        return jsonify({
            "error": {
                "code": 403,
                "name": "Forbidden",
                "message": str(exc),
            }
        }), 403
    except ItemValidationError as exc:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(exc),
            }
        }), 400

    return jsonify({
        "message": "Item updated successfully",
        "item": updated_item,
    }), 200


@items_bp.route("/api/items/<int:item_id>", methods=["DELETE"])
@login_required
def remove_item(item_id: int):
    """
    Delete an existing item report.
    Protected: Users can only delete their own reports; Admins can delete any report.
    """
    user_id = session["user_id"]
    user_role = session.get("role", "student")

    try:
        delete_item(item_id=item_id, user_id=user_id, user_role=user_role)
    except ItemNotFoundError as exc:
        return jsonify({
            "error": {
                "code": 404,
                "name": "Not Found",
                "message": str(exc),
            }
        }), 404
    except UnauthorizedActionError as exc:
        return jsonify({
            "error": {
                "code": 403,
                "name": "Forbidden",
                "message": str(exc),
            }
        }), 403

    return jsonify({"message": "Item deleted successfully"}), 200


@items_bp.route("/uploads/<filename>", methods=["GET"])
@items_bp.route("/api/uploads/<filename>", methods=["GET"])
def get_uploaded_file(filename: str):
    """Serve uploaded images securely from the uploads directory."""
    return send_from_directory(current_app.config["UPLOAD_FOLDER"], filename)
