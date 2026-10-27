"""
models.py
Domain models, SQL schemas, and serialization helpers for the College Lost & Found system.
Designed to be clean, readable, and easy to explain during academic evaluation.
"""

# Valid constants for data integrity
VALID_CATEGORIES = [
    "Electronics",
    "ID Cards & Documents",
    "Books & Stationery",
    "Keys",
    "Bags & Wallets",
    "Clothing",
    "Others",
]

VALID_ITEM_TYPES = ["lost", "found"]
VALID_ITEM_STATUSES = ["open", "claimed", "resolved", "returned"]
VALID_CLAIM_STATUSES = ["pending", "approved", "rejected"]
VALID_USER_ROLES = ["student", "faculty", "staff", "admin"]


# Database Table Schemas (SQLite DDL)
SCHEMA_SQL = """
-- Users table: stores student/staff accounts
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL DEFAULT 'student' CHECK(role IN ('student', 'faculty', 'staff', 'admin')),
    phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Items table: stores reports of lost and found belongings
CREATE TABLE IF NOT EXISTS items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT NOT NULL,
    category TEXT NOT NULL,
    type TEXT NOT NULL CHECK(type IN ('lost', 'found')),
    location TEXT NOT NULL,
    date_event DATE NOT NULL,
    status TEXT NOT NULL DEFAULT 'open' CHECK(status IN ('open', 'claimed', 'resolved', 'returned')),
    image_filename TEXT,
    user_id INTEGER NOT NULL,
    contact_email TEXT,
    contact_phone TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Claims table: allows rightful owners to claim found items by providing proof
CREATE TABLE IF NOT EXISTS claims (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL,
    claimant_id INTEGER NOT NULL,
    proof_details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending' CHECK(status IN ('pending', 'approved', 'rejected')),
    admin_notes TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE,
    FOREIGN KEY (claimant_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Notifications table: alerts users about claims, status changes, and updates
CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    is_read INTEGER NOT NULL DEFAULT 0 CHECK(is_read IN (0, 1)),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

-- Item Embeddings table: stores OpenAI CLIP multimodal vector embeddings for item images
CREATE TABLE IF NOT EXISTS item_embeddings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    item_id INTEGER NOT NULL UNIQUE,
    model_version TEXT NOT NULL,
    embedding BLOB NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (item_id) REFERENCES items (id) ON DELETE CASCADE
);

-- Indexes for fast searching and filtering
CREATE INDEX IF NOT EXISTS idx_items_type ON items(type);
CREATE INDEX IF NOT EXISTS idx_items_status ON items(status);
CREATE INDEX IF NOT EXISTS idx_items_category ON items(category);
CREATE INDEX IF NOT EXISTS idx_claims_item ON claims(item_id);
CREATE INDEX IF NOT EXISTS idx_notifications_user ON notifications(user_id);
CREATE INDEX IF NOT EXISTS idx_item_embeddings_item ON item_embeddings(item_id);
"""


def user_to_dict(user_row):
    """
    Convert a SQLite Row for a user into a dictionary.
    SECURITY NOTE: password_hash is intentionally excluded from the output.
    """
    if user_row is None:
        return None
    return {
        "id": user_row["id"],
        "name": user_row["name"],
        "email": user_row["email"],
        "role": user_row["role"],
        "phone": user_row["phone"],
        "created_at": user_row["created_at"],
    }


def item_to_dict(item_row):
    """Convert a SQLite Row for a lost/found item into a dictionary."""
    if item_row is None:
        return None
    return {
        "id": item_row["id"],
        "title": item_row["title"],
        "description": item_row["description"],
        "category": item_row["category"],
        "type": item_row["type"],
        "location": item_row["location"],
        "date_event": item_row["date_event"],
        "status": item_row["status"],
        "image_filename": item_row["image_filename"],
        "user_id": item_row["user_id"],
        "contact_email": item_row["contact_email"],
        "contact_phone": item_row["contact_phone"],
        "created_at": item_row["created_at"],
    }


def claim_to_dict(claim_row):
    """Convert a SQLite Row for a claim into a dictionary."""
    if claim_row is None:
        return None
    keys = claim_row.keys() if hasattr(claim_row, "keys") else []
    result = {
        "id": claim_row["id"],
        "item_id": claim_row["item_id"],
        "claimant_id": claim_row["claimant_id"],
        "proof_details": claim_row["proof_details"],
        "status": claim_row["status"],
        "admin_notes": claim_row["admin_notes"] if "admin_notes" in keys else None,
        "created_at": claim_row["created_at"],
    }
    # Enriched fields if joined with items/users
    if "item_title" in keys:
        result["item_title"] = claim_row["item_title"]
    if "item_type" in keys:
        result["item_type"] = claim_row["item_type"]
    if "item_status" in keys:
        result["item_status"] = claim_row["item_status"]
    if "claimant_name" in keys:
        result["claimant_name"] = claim_row["claimant_name"]
    if "claimant_email" in keys:
        result["claimant_email"] = claim_row["claimant_email"]
    return result


def notification_to_dict(notif_row):
    """Convert a SQLite Row for a notification into a dictionary."""
    if notif_row is None:
        return None
    return {
        "id": notif_row["id"],
        "user_id": notif_row["user_id"],
        "title": notif_row["title"],
        "message": notif_row["message"],
        "is_read": bool(notif_row["is_read"]),
        "created_at": notif_row["created_at"],
    }
