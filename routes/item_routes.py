"""
routes/item_routes.py
API endpoints for lost & found item reporting, filtering, searching, updates, and uploads.
Enforces that users can only edit or delete their own reported items.
"""

from flask import Blueprint, current_app, jsonify, request, send_from_directory, session
from database import get_db
from routes.auth_routes import login_required
from services.clip_service import (
    CLIPModelNotAvailableError,
    CLIPService,
    InvalidImageError,
)
from services.item_service import (
    ItemNotFoundError,
    ItemValidationError,
    UnauthorizedActionError,
    delete_item,
    get_item_by_id,
    get_items,
    report_item,
    search_items_by_image,
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


@items_bp.route("/api/items/search/image", methods=["POST"])
@items_bp.route("/api/items/search-by-image", methods=["POST"])
def search_by_image():
    """
    Search for items with visually similar images using OpenAI CLIP embeddings.
    Accepts multipart/form-data with:
    - image: The photograph file to search with (required).
    - type: Optional filter (all, lost, found).
    - category: Optional category filter.
    - location: Optional location keyword.
    - status: Optional item status (open, claimed, resolved).
    - top_k: Maximum results to return (default 20, max 50).
    - threshold: Minimum cosine similarity threshold (default 0.0).
    """
    if "image" not in request.files or not request.files["image"].filename:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": "An image file is required in multipart field 'image'.",
            }
        }), 400

    query_file = request.files["image"]
    upload_folder = current_app.config.get("UPLOAD_FOLDER")

    # Extract optional filter parameters from form or query string
    item_type = request.form.get("type") or request.args.get("type")
    category = request.form.get("category") or request.args.get("category")
    location = request.form.get("location") or request.args.get("location")
    status = request.form.get("status") or request.args.get("status")

    try:
        top_k = min(50, max(1, int(request.form.get("top_k") or request.args.get("top_k") or 20)))
    except (ValueError, TypeError):
        top_k = 20

    try:
        threshold = float(request.form.get("threshold") or request.args.get("threshold") or 0.0)
    except (ValueError, TypeError):
        threshold = 0.0

    try:
        similar_items = search_items_by_image(
            query_image_input=query_file,
            upload_folder=upload_folder,
            item_type=item_type,
            category=category,
            location=location,
            status=status,
            top_k=top_k,
            threshold=threshold,
        )
    except (InvalidImageError, ItemValidationError) as exc:
        return jsonify({
            "error": {
                "code": 400,
                "name": "Bad Request",
                "message": str(exc),
            }
        }), 400
    except CLIPModelNotAvailableError as exc:
        return jsonify({
            "error": {
                "code": 503,
                "name": "Service Unavailable",
                "message": f"CLIP visual similarity service is currently unavailable: {exc}",
            }
        }), 503
    except Exception as exc:
        current_app.logger.error("Unexpected error during visual similarity search: %s", exc, exc_info=True)
        return jsonify({
            "error": {
                "code": 500,
                "name": "Internal Server Error",
                "message": "An error occurred while computing visual similarity.",
            }
        }), 500

    clip_info = CLIPService.get_instance().get_info()

    return jsonify({
        "count": len(similar_items),
        "model_info": {
            "model_name": clip_info["model_name"],
            "model_version": clip_info["model_version"],
            "device": clip_info["device"],
            "device_description": clip_info["device_description"],
        },
        "items": similar_items,
    }), 200


@items_bp.route("/api/items/similarity/info", methods=["GET"])
def similarity_service_info():
    """
    Retrieve status and diagnostic information about the CLIP similarity engine.
    """
    clip_info = CLIPService.get_instance().get_info()
    db = get_db()
    total_embedded = db.execute("SELECT COUNT(*) FROM item_embeddings").fetchone()[0]
    total_items_with_images = db.execute(
        "SELECT COUNT(*) FROM items WHERE image_filename IS NOT NULL AND TRIM(image_filename) != ''"
    ).fetchone()[0]

    return jsonify({
        "status": "ready" if clip_info["is_loaded"] else "idle",
        "clip": clip_info,
        "database_stats": {
            "total_embeddings": total_embedded,
            "total_items_with_images": total_items_with_images,
            "coverage_percentage": round((total_embedded / total_items_with_images * 100), 1)
            if total_items_with_images > 0 else 100.0,
        },
    }), 200
