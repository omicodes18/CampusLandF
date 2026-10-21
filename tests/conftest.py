"""
tests/conftest.py
Pytest fixtures providing an isolated test environment and SQLite database.
"""

import os
import tempfile
import pytest

from app import create_app
from database import init_db


@pytest.fixture
def app():
    """Create and configure an isolated application instance for testing."""
    # Create a temporary file to act as the test database
    db_fd, db_path = tempfile.mkstemp(suffix=".db")

    app = create_app({
        "TESTING": True,
        "DATABASE": db_path,
        "SECRET_KEY": "test-secret-key-for-automated-tests",
    })

    with app.app_context():
        init_db()

    yield app

    # Cleanup temporary test database file
    os.close(db_fd)
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def client(app):
    """A test client for making simulated HTTP requests to the app."""
    return app.test_client()


@pytest.fixture
def runner(app):
    """A test CLI runner for testing Click / Flask CLI commands."""
    return app.test_cli_runner()
