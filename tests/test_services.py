"""
tests/test_services.py
Automated tests for authentication service and item service business logic.
"""

from services.auth_service import (
    authenticate_user,
    create_user,
    hash_password,
    validate_email,
    validate_password_strength,
    verify_password,
)
from services.item_service import get_item_by_id, get_items, report_item


def test_password_hashing_and_verification():
    """Verify passwords are hashed securely and verified correctly."""
    plain = "SuperSecret123"
    hashed = hash_password(plain)

    # Password must never be stored as plain text
    assert hashed != plain
    assert len(hashed) > 20

    # Verification checks
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword", hashed) is False
    assert verify_password("", hashed) is False


def test_password_strength_validation():
    """Verify validation enforces minimum length."""
    valid, msg = validate_password_strength("short")
    assert valid is False
    assert "8 characters" in msg

    valid, msg = validate_password_strength("validpassword123")
    assert valid is True
    assert msg == ""


def test_email_validation():
    """Verify email format validation."""
    assert validate_email("student@college.edu")[0] is True
    assert validate_email("invalid-email")[0] is False
    assert validate_email("")[0] is False


def test_user_creation_and_authentication(app):
    """Test user creation and authentication flow."""
    with app.app_context():
        # Create user
        user = create_user(
            name="Alice Kumar",
            email="alice@college.edu",
            password="SecurePassword2026",
            role="student",
        )

        assert user["id"] is not None
        assert user["name"] == "Alice Kumar"
        assert user["email"] == "alice@college.edu"
        # Ensure password_hash is omitted from user_to_dict output
        assert "password_hash" not in user

        # Authenticate with valid credentials
        auth_success = authenticate_user("alice@college.edu", "SecurePassword2026")
        assert auth_success is not None
        assert auth_success["email"] == "alice@college.edu"

        # Authenticate with invalid password
        auth_fail = authenticate_user("alice@college.edu", "WrongPassword")
        assert auth_fail is None


def test_report_and_get_items(app):
    """Test item reporting and listing."""
    with app.app_context():
        user = create_user(
            name="Bob Sharma",
            email="bob@college.edu",
            password="BobPassword123",
        )

        item_data = {
            "title": "Blue Dell Laptop Charger",
            "description": "Found near desk 4, 65W USB-C charger",
            "category": "Electronics",
            "type": "found",
            "location": "Central Library, 2nd Floor",
            "date_event": "2026-10-21",
            "contact_email": "bob@college.edu",
        }

        created = report_item(item_data, user["id"])
        assert created["id"] is not None
        assert created["title"] == "Blue Dell Laptop Charger"
        assert created["status"] == "open"

        # Fetch list
        items = get_items(item_type="found")
        assert len(items) == 1
        assert items[0]["title"] == "Blue Dell Laptop Charger"

        # Fetch by ID
        fetched = get_item_by_id(created["id"])
        assert fetched is not None
        assert fetched["location"] == "Central Library, 2nd Floor"
