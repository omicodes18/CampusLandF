"""
services/item_service.py
Business logic, input validation, image processing, and database operations for lost and found items.
"""

import os
import uuid
from datetime import date
from werkzeug.utils import secure_filename
from database import get_db
from models import (
    VALID_CATEGORIES,
    VALID_ITEM_STATUSES,
    VALID_ITEM_TYPES,
    item_to_dict,
)

# Image upload configuration
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
MAX_IMAGE_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class ItemNotFoundError(Exception):
    """Raised when an item with the requested ID does not exist."""
    pass


class UnauthorizedActionError(Exception):
    """Raised when a user attempts an action on an item they do not own."""
    pass


class ItemValidationError(ValueError):
    """Raised when item fields or uploaded images fail validation."""
    pass


def allowed_file(filename: str) -> bool:
    """Check if the uploaded file has an allowed image extension."""
    if not filename or "." not in filename:
        return False
    ext = filename.rsplit(".", 1)[1].lower()
    return ext in ALLOWED_EXTENSIONS


def validate_image_file(file_storage):
    """
    Validate that an uploaded file is a valid image within allowed size limits.
    Returns (True, "") or raises ItemValidationError.
    """
    if file_storage is None or not getattr(file_storage, "filename", None):
        return True, ""

    if not allowed_file(file_storage.filename):
        allowed_list = ", ".join(sorted(ALLOWED_EXTENSIONS))
        raise ItemValidationError(f"Invalid file type. Allowed image formats: {allowed_list}")

    # Check file size without loading entire file into RAM at once
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)

    if size > MAX_IMAGE_SIZE_BYTES:
        max_mb = MAX_IMAGE_SIZE_BYTES // (1024 * 1024)
        raise ItemValidationError(f"File size exceeds maximum limit of {max_mb} MB.")

    return True, ""


def save_image(file_storage, upload_folder: str) -> str:
    """
    Safely save an uploaded image to disk with a collision-resistant unique name.
    Returns the stored filename.
    """
    validate_image_file(file_storage)
    if not file_storage or not file_storage.filename:
        return None

    os.makedirs(upload_folder, exist_ok=True)
    clean_name = secure_filename(file_storage.filename)
    if not clean_name or "." not in clean_name:
        ext = file_storage.filename.rsplit(".", 1)[1].lower()
        clean_name = f"image.{ext}"
    unique_filename = f"{uuid.uuid4().hex[:10]}_{clean_name}"
    destination_path = os.path.join(upload_folder, unique_filename)
    file_storage.save(destination_path)

    return unique_filename


def validate_item_data(data: dict, is_update: bool = False) -> list[str]:
    """Validate item fields for creation or update."""
    errors = []

    # Title
    if "title" in data or not is_update:
        title = (data.get("title") or "").strip()
        if not title:
            errors.append("Title is required.")
        elif len(title) < 3:
            errors.append("Title must be at least 3 characters long.")

    # Description
    if "description" in data or not is_update:
        description = (data.get("description") or "").strip()
        if not description:
            errors.append("Description is required.")

    # Category
    if "category" in data or not is_update:
        category = data.get("category")
        if not category or category not in VALID_CATEGORIES:
            errors.append(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")

    # Type (lost / found)
    if "type" in data or not is_update:
        item_type = data.get("type")
        if not item_type or item_type not in VALID_ITEM_TYPES:
            errors.append(f"Invalid type. Must be either: {', '.join(VALID_ITEM_TYPES)}")

    # Location
    if "location" in data or not is_update:
        location = (data.get("location") or "").strip()
        if not location:
            errors.append("Location is required.")

    # Date of event
    if "date_event" in data or not is_update:
        date_event = (data.get("date_event") or "").strip()
        if not date_event:
            errors.append("Date of event (lost/found date) is required.")
        else:
            try:
                date.fromisoformat(date_event)
            except ValueError:
                errors.append("Date of event must be a valid date in YYYY-MM-DD format.")

    # Status (optional, default is 'open')
    if "status" in data and data.get("status"):
        status = data.get("status").strip().lower()
        if status not in VALID_ITEM_STATUSES:
            errors.append(f"Invalid status. Must be one of: {', '.join(VALID_ITEM_STATUSES)}")

    return errors


def report_item(data: dict, user_id: int, image_file=None, upload_folder: str = None) -> dict:
    """
    Insert a newly reported lost or found item into the database.
    Optionally saves an uploaded image file.
    """
    errors = validate_item_data(data, is_update=False)
    if errors:
        raise ItemValidationError("; ".join(errors))

    image_filename = None
    if image_file and upload_folder:
        image_filename = save_image(image_file, upload_folder)
    elif data.get("image_filename"):
        image_filename = data.get("image_filename")

    db = get_db()
    cursor = db.execute(
        """
        INSERT INTO items (
            title, description, category, type, location,
            date_event, status, image_filename, user_id,
            contact_email, contact_phone
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            data["title"].strip(),
            data["description"].strip(),
            data["category"],
            data["type"],
            data["location"].strip(),
            data["date_event"].strip(),
            data.get("status", "open"),
            image_filename,
            user_id,
            data.get("contact_email"),
            data.get("contact_phone"),
        ),
    )
    db.commit()

    item_row = db.execute("SELECT * FROM items WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return item_to_dict(item_row)


def get_items(
    item_type: str = None,
    category: str = None,
    location: str = None,
    status: str = None,
    search: str = None,
) -> list[dict]:
    """
    Fetch items with multi-parameter filtering and keyword search.
    Case-insensitive matching for type, category, status, and location.
    """
    db = get_db()
    query = "SELECT * FROM items WHERE 1=1"
    params = []

    if item_type:
        query += " AND LOWER(type) = ?"
        params.append(item_type.strip().lower())

    if category:
        query += " AND LOWER(category) = ?"
        params.append(category.strip().lower())

    if location:
        query += " AND location LIKE ?"
        params.append(f"%{location.strip()}%")

    if status:
        query += " AND LOWER(status) = ?"
        params.append(status.strip().lower())

    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR location LIKE ?)"
        term = f"%{search.strip()}%"
        params.extend([term, term, term])

    query += " ORDER BY created_at DESC"

    rows = db.execute(query, params).fetchall()
    return [item_to_dict(row) for row in rows]


def get_item_by_id(item_id: int) -> dict:
    """Fetch single item by its ID."""
    db = get_db()
    row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return item_to_dict(row)


def update_item(
    item_id: int,
    user_id: int,
    user_role: str,
    data: dict,
    image_file=None,
    upload_folder: str = None,
) -> dict:
    """
    Update an existing item report.
    Enforces authorization: Only the reporting user or an admin can edit.
    """
    db = get_db()
    existing_row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    if not existing_row:
        raise ItemNotFoundError("Item not found.")

    # Authorization Check: owner or admin
    if existing_row["user_id"] != user_id and user_role != "admin":
        raise UnauthorizedActionError("You are only authorized to edit your own reports.")

    # Validate updated fields
    errors = validate_item_data(data, is_update=True)
    if errors:
        raise ItemValidationError("; ".join(errors))

    # Process image if a new image was uploaded
    new_image_filename = existing_row["image_filename"]
    if image_file and upload_folder:
        new_image_filename = save_image(image_file, upload_folder)
    elif "image_filename" in data:
        new_image_filename = data["image_filename"]

    # Build dynamic update statement based on supplied fields
    title = data.get("title", existing_row["title"]).strip()
    description = data.get("description", existing_row["description"]).strip()
    category = data.get("category", existing_row["category"])
    item_type = data.get("type", existing_row["type"])
    location = data.get("location", existing_row["location"]).strip()
    date_event = data.get("date_event", existing_row["date_event"]).strip()
    status = data.get("status", existing_row["status"])
    contact_email = data.get("contact_email", existing_row["contact_email"])
    contact_phone = data.get("contact_phone", existing_row["contact_phone"])

    db.execute(
        """
        UPDATE items
        SET title = ?, description = ?, category = ?, type = ?,
            location = ?, date_event = ?, status = ?,
            image_filename = ?, contact_email = ?, contact_phone = ?
        WHERE id = ?
        """,
        (
            title,
            description,
            category,
            item_type,
            location,
            date_event,
            status,
            new_image_filename,
            contact_email,
            contact_phone,
            item_id,
        ),
    )
    db.commit()

    updated_row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return item_to_dict(updated_row)


def delete_item(item_id: int, user_id: int, user_role: str) -> bool:
    """
    Delete an item report.
    Enforces authorization: Only the reporting user or an admin can delete.
    """
    db = get_db()
    existing_row = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()

    if not existing_row:
        raise ItemNotFoundError("Item not found.")

    if existing_row["user_id"] != user_id and user_role != "admin":
        raise UnauthorizedActionError("You are only authorized to delete your own reports.")

    db.execute("DELETE FROM items WHERE id = ?", (item_id,))
    db.commit()
    return True
