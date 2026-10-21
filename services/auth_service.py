"""
services/auth_service.py
Authentication service handling secure password hashing, user registration, and verification.
Follows security best practices: passwords are never stored in plain text.
"""

import re
import sqlite3
from werkzeug.security import check_password_hash, generate_password_hash
from database import get_db
from models import VALID_USER_ROLES, user_to_dict


class DuplicateUserError(Exception):
    """Raised when an attempt is made to register an email that already exists."""
    pass


class AuthValidationError(ValueError):
    """Raised when user input fails validation constraints."""
    pass


def hash_password(plain_password: str) -> str:
    """Hash a plain text password using Werkzeug's secure hashing algorithm."""
    if not plain_password or not isinstance(plain_password, str):
        raise AuthValidationError("Password must be a non-empty string.")
    return generate_password_hash(plain_password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a plain text password against a stored hash."""
    if not plain_password or not hashed_password:
        return False
    return check_password_hash(hashed_password, plain_password)


def validate_password_strength(password: str) -> tuple[bool, str]:
    """Validate password meets minimum security standards."""
    if not password or len(password) < 8:
        return False, "Password must be at least 8 characters long."
    return True, ""


def validate_email(email: str) -> tuple[bool, str]:
    """Basic email format validation."""
    if not email:
        return False, "Email address is required."
    pattern = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
    if not re.match(pattern, email.strip()):
        return False, "Invalid email address format."
    return True, ""


def create_user(name: str, email: str, password: str, role: str = "student", phone: str = None) -> dict:
    """
    Create a new user with a hashed password and store in the database.
    Raises DuplicateUserError if the email is already in use.
    Raises AuthValidationError if validation fails.
    Returns the created user dictionary without password_hash.
    """
    if not name or not isinstance(name, str) or len(name.strip()) < 2:
        raise AuthValidationError("Name is required and must be at least 2 characters long.")

    name = name.strip()
    email = (email or "").strip().lower()

    is_valid_email, email_err = validate_email(email)
    if not is_valid_email:
        raise AuthValidationError(email_err)

    is_valid_pwd, pwd_err = validate_password_strength(password)
    if not is_valid_pwd:
        raise AuthValidationError(pwd_err)

    if role not in VALID_USER_ROLES:
        raise AuthValidationError(f"Invalid role. Must be one of: {', '.join(VALID_USER_ROLES)}")

    if phone:
        phone = str(phone).strip()

    # Pre-check email uniqueness
    if get_user_by_email(email) is not None:
        raise DuplicateUserError("A user with this email already exists.")

    password_hashed = hash_password(password)

    db = get_db()
    try:
        cursor = db.execute(
            """
            INSERT INTO users (name, email, password_hash, role, phone)
            VALUES (?, ?, ?, ?, ?)
            """,
            (name, email, password_hashed, role, phone),
        )
        db.commit()
    except sqlite3.IntegrityError as exc:
        raise DuplicateUserError("A user with this email already exists.") from exc

    user_row = db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return user_to_dict(user_row)


def get_user_by_email(email: str):
    """Retrieve raw user row by email (internal use for authentication)."""
    db = get_db()
    return db.execute("SELECT * FROM users WHERE email = ?", (email.strip().lower(),)).fetchone()


def get_user_by_id(user_id: int) -> dict:
    """Retrieve sanitized user details by ID."""
    db = get_db()
    row = db.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    return user_to_dict(row)


def get_all_users() -> list[dict]:
    """Retrieve all users without password hashes (admin only)."""
    db = get_db()
    rows = db.execute("SELECT * FROM users ORDER BY created_at DESC").fetchall()
    return [user_to_dict(row) for row in rows]


def authenticate_user(email: str, password: str):
    """
    Authenticate a user by email and password.
    Returns sanitized user dictionary if successful, None otherwise.
    """
    if not email or not password:
        return None

    user_row = get_user_by_email(email)
    if not user_row:
        return None

    if verify_password(password, user_row["password_hash"]):
        return user_to_dict(user_row)

    return None
