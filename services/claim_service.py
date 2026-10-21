"""
services/claim_service.py
Business logic, input validation, status transition enforcement, and notifications for ownership claims.
"""

from database import get_db
from models import VALID_ITEM_STATUSES, claim_to_dict, item_to_dict


class ItemNotFoundError(Exception):
    """Raised when an item with the requested ID does not exist."""
    pass


class ClaimNotFoundError(Exception):
    """Raised when the requested claim does not exist."""
    pass


class ClaimValidationError(ValueError):
    """Raised when claim parameters or eligibility checks fail."""
    pass


class InvalidStatusTransitionError(ValueError):
    """Raised when an illegal status change is attempted on a claim or item."""
    pass


def submit_claim(item_id: int, claimant_id: int, proof_details: str) -> dict:
    """
    Submit an ownership claim for a found item with proof description.
    Enforces validation and business rules:
    - Item must exist and be of type 'found'.
    - Item must not be already 'returned' or 'resolved'.
    - User cannot claim an item they reported.
    - User cannot submit multiple active pending claims for the same item.
    """
    if not proof_details or not isinstance(proof_details, str):
        raise ClaimValidationError("Proof description is required.")

    clean_proof = proof_details.strip()
    if len(clean_proof) < 10:
        raise ClaimValidationError("Proof description must be at least 10 characters long.")

    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ItemNotFoundError("Item not found.")

    if item["type"] != "found":
        raise ClaimValidationError("Ownership claims can only be submitted for found items.")

    if item["user_id"] == claimant_id:
        raise ClaimValidationError("You cannot submit an ownership claim for an item you reported.")

    if item["status"] in ("claimed", "resolved", "returned"):
        raise ClaimValidationError(f"This item is already marked as {item['status']} and cannot be claimed.")

    # Check for existing pending claim by this user for this item
    existing_claim = db.execute(
        "SELECT id FROM claims WHERE item_id = ? AND claimant_id = ? AND status = 'pending'",
        (item_id, claimant_id),
    ).fetchone()
    if existing_claim:
        raise ClaimValidationError("You already have an active pending claim for this item.")

    # Insert claim
    cursor = db.execute(
        """
        INSERT INTO claims (item_id, claimant_id, proof_details, status)
        VALUES (?, ?, ?, 'pending')
        """,
        (item_id, claimant_id, clean_proof),
    )
    claim_id = cursor.lastrowid

    # Create notification for the finder/reporter
    db.execute(
        """
        INSERT INTO notifications (user_id, title, message)
        VALUES (?, ?, ?)
        """,
        (
            item["user_id"],
            "New Ownership Claim Received",
            f"A user has submitted an ownership claim with proof for your found item: '{item['title']}'.",
        ),
    )
    db.commit()

    created_claim = db.execute(
        """
        SELECT c.*, i.title as item_title, i.type as item_type, i.status as item_status,
               u.name as claimant_name, u.email as claimant_email
        FROM claims c
        JOIN items i ON c.item_id = i.id
        JOIN users u ON c.claimant_id = u.id
        WHERE c.id = ?
        """,
        (claim_id,),
    ).fetchone()

    return claim_to_dict(created_claim)


def get_claim_by_id(claim_id: int) -> dict:
    """Retrieve single claim by ID with item and claimant details."""
    db = get_db()
    row = db.execute(
        """
        SELECT c.*, i.title as item_title, i.type as item_type, i.status as item_status,
               u.name as claimant_name, u.email as claimant_email
        FROM claims c
        JOIN items i ON c.item_id = i.id
        JOIN users u ON c.claimant_id = u.id
        WHERE c.id = ?
        """,
        (claim_id,),
    ).fetchone()
    return claim_to_dict(row)


def get_claims(status: str = None, claimant_id: int = None, item_id: int = None) -> list[dict]:
    """List claims with optional filters (status, claimant_id, item_id)."""
    db = get_db()
    query = """
        SELECT c.*, i.title as item_title, i.type as item_type, i.status as item_status,
               u.name as claimant_name, u.email as claimant_email
        FROM claims c
        JOIN items i ON c.item_id = i.id
        JOIN users u ON c.claimant_id = u.id
        WHERE 1=1
    """
    params = []

    if status:
        query += " AND c.status = ?"
        params.append(status.lower())

    if claimant_id:
        query += " AND c.claimant_id = ?"
        params.append(claimant_id)

    if item_id:
        query += " AND c.item_id = ?"
        params.append(item_id)

    query += " ORDER BY c.created_at DESC"

    rows = db.execute(query, params).fetchall()
    return [claim_to_dict(row) for row in rows]


def review_claim(claim_id: int, new_status: str, admin_notes: str = None) -> dict:
    """
    Review a pending claim (Admin only).
    Enforces valid status transitions:
    - Only 'approved' or 'rejected' are valid targets.
    - Only claims currently in 'pending' status can be reviewed.
    - If approved:
      * Claim status -> 'approved'
      * Item status -> 'claimed'
      * Other pending claims on the same item are automatically rejected
      * Claimant is notified
    - If rejected:
      * Claim status -> 'rejected'
      * Item remains in its current status
      * Claimant is notified
    """
    new_status = (new_status or "").strip().lower()
    if new_status not in ("approved", "rejected"):
        raise ClaimValidationError("New status must be either 'approved' or 'rejected'.")

    db = get_db()
    claim = db.execute("SELECT * FROM claims WHERE id = ?", (claim_id,)).fetchone()
    if not claim:
        raise ClaimNotFoundError("Claim not found.")

    # Status transition check
    if claim["status"] != "pending":
        raise InvalidStatusTransitionError(
            f"Cannot review claim: claim is already '{claim['status']}'."
        )

    item = db.execute("SELECT * FROM items WHERE id = ?", (claim["item_id"],)).fetchone()
    if not item:
        raise ClaimValidationError("Associated item no longer exists.")

    admin_notes_clean = admin_notes.strip() if admin_notes else None

    if new_status == "approved":
        if item["status"] in ("returned", "resolved"):
            raise InvalidStatusTransitionError(
                f"Cannot approve claim: the item has already been marked as '{item['status']}'."
            )

        # 1. Update this claim to approved
        db.execute(
            "UPDATE claims SET status = 'approved', admin_notes = ? WHERE id = ?",
            (admin_notes_clean, claim_id),
        )

        # 2. Update item status to 'claimed'
        db.execute("UPDATE items SET status = 'claimed' WHERE id = ?", (item["id"],))

        # 3. Automatically reject any other pending claims for this item
        db.execute(
            """
            UPDATE claims
            SET status = 'rejected', admin_notes = 'Another claim was approved for this item.'
            WHERE item_id = ? AND id != ? AND status = 'pending'
            """,
            (item["id"], claim_id),
        )

        # 4. Notify claimant of approval
        db.execute(
            """
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
            """,
            (
                claim["claimant_id"],
                "Ownership Claim Approved!",
                f"Your claim for '{item['title']}' has been approved. Please visit the Lost & Found office with ID proof to collect your item.",
            ),
        )

    elif new_status == "rejected":
        # 1. Update this claim to rejected
        db.execute(
            "UPDATE claims SET status = 'rejected', admin_notes = ? WHERE id = ?",
            (admin_notes_clean, claim_id),
        )

        # 2. Notify claimant of rejection
        reason_msg = f" Reason: {admin_notes_clean}" if admin_notes_clean else ""
        db.execute(
            """
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
            """,
            (
                claim["claimant_id"],
                "Ownership Claim Rejected",
                f"Your claim for '{item['title']}' was not approved.{reason_msg}",
            ),
        )

    db.commit()
    return get_claim_by_id(claim_id)


def update_item_status(item_id: int, new_status: str, admin_notes: str = None) -> dict:
    """
    Update item status directly (Admin only), e.g., to 'returned' or 'resolved'.
    Enforces valid transitions and prevents reopening closed items.
    """
    new_status = (new_status or "").strip().lower()
    if new_status not in VALID_ITEM_STATUSES:
        valid_str = ", ".join(VALID_ITEM_STATUSES)
        raise ClaimValidationError(f"Invalid item status. Must be one of: {valid_str}")

    db = get_db()
    item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        raise ItemNotFoundError("Item not found.")

    current_status = item["status"]

    # Transition integrity checks
    if current_status in ("returned", "resolved") and new_status == "open":
        raise InvalidStatusTransitionError(
            f"Invalid transition: An item marked as '{current_status}' cannot be reopened to 'open'."
        )

    if current_status == new_status:
        return item_to_dict(item)

    # Update item status
    db.execute("UPDATE items SET status = ? WHERE id = ?", (new_status, item_id))

    # If marked as returned or resolved, notify the reporter
    if new_status in ("returned", "resolved"):
        db.execute(
            """
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
            """,
            (
                item["user_id"],
                f"Item Marked as {new_status.capitalize()}",
                f"Your reported item '{item['title']}' has been officially marked as {new_status}.",
            ),
        )

    db.commit()
    updated_item = db.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    return item_to_dict(updated_item)
