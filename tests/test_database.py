"""
tests/test_database.py
Automated tests for SQLite database initialization, schemas, and CLI commands.
"""

import sqlite3
import pytest
from database import get_db


def test_tables_created(app):
    """Test that all required tables and indexes are created by init_db."""
    with app.app_context():
        db = get_db()
        cursor = db.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row["name"] for row in cursor.fetchall()]

        assert "users" in tables
        assert "items" in tables
        assert "claims" in tables
        assert "notifications" in tables


def test_init_db_command(runner):
    """Test that the 'flask init-db' CLI command executes without error."""
    result = runner.invoke(args=["init-db"])
    assert result.exit_code == 0
    assert "Successfully initialized" in result.output


def test_foreign_key_enforcement(app):
    """Test that SQLite foreign key constraints are strictly enforced."""
    with app.app_context():
        db = get_db()
        # Attempting to insert an item referencing a non-existent user_id should fail
        with pytest.raises(sqlite3.IntegrityError):
            db.execute(
                """
                INSERT INTO items (
                    title, description, category, type, location,
                    date_event, status, user_id
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "Lost Watch",
                    "Silver wristwatch",
                    "Others",
                    "lost",
                    "Library",
                    "2026-10-21",
                    "open",
                    99999,  # Non-existent user
                ),
            )
            db.commit()


def test_insert_and_retrieve_user(app):
    """Test inserting a user and retrieving the record with Row factory."""
    with app.app_context():
        db = get_db()
        db.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            ("Test Student", "student@college.edu", "hashed_val", "student"),
        )
        db.commit()

        row = db.execute("SELECT * FROM users WHERE email = ?", ("student@college.edu",)).fetchone()
        assert row is not None
        assert row["name"] == "Test Student"
        assert row["role"] == "student"


def test_notifications_table_and_cascade(app):
    """Test inserting notifications and cascade delete when user is removed."""
    with app.app_context():
        db = get_db()
        cursor = db.execute(
            """
            INSERT INTO users (name, email, password_hash, role)
            VALUES (?, ?, ?, ?)
            """,
            ("Notif User", "notif@college.edu", "hashed_val", "student"),
        )
        user_id = cursor.lastrowid

        # Insert notification
        db.execute(
            """
            INSERT INTO notifications (user_id, title, message)
            VALUES (?, ?, ?)
            """,
            (user_id, "Item Found", "Someone reported finding your ID card."),
        )
        db.commit()

        notif = db.execute("SELECT * FROM notifications WHERE user_id = ?", (user_id,)).fetchone()
        assert notif is not None
        assert notif["title"] == "Item Found"
        assert notif["is_read"] == 0

        # Delete user -> notification should cascade delete
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()

        remaining_notifs = db.execute("SELECT * FROM notifications WHERE user_id = ?", (user_id,)).fetchall()
        assert len(remaining_notifs) == 0
