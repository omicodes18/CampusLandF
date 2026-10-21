"""
database.py
Database connection management and initialization for SQLite.
Uses Flask's application context (g) to ensure safe, per-request connections.
"""

import os
import sqlite3
import click
from flask import current_app, g
from flask.cli import with_appcontext

from models import SCHEMA_SQL


def get_db():
    """
    Connect to the application's configured SQLite database.
    The connection is unique for each request and is stored in 'g'.
    """
    if "db" not in g:
        db_path = current_app.config["DATABASE"]

        # Ensure directory for the database file exists (e.g., instance/)
        db_dir = os.path.dirname(db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)

        g.db = sqlite3.connect(db_path)
        # Enable column access by name (dict-like row objects)
        g.db.row_factory = sqlite3.Row

        # Enforce foreign key constraints in SQLite
        g.db.execute("PRAGMA foreign_keys = ON;")

    return g.db


def close_db(e=None):
    """Close the database connection at the end of the request."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db(reset: bool = False):
    """Execute the schema SQL to create all required database tables."""
    db = get_db()
    if reset:
        db.executescript("""
            DROP TABLE IF EXISTS notifications;
            DROP TABLE IF EXISTS claims;
            DROP TABLE IF EXISTS items;
            DROP TABLE IF EXISTS users;
        """)
    db.executescript(SCHEMA_SQL)

    # Backward-compatible column migration for claims table
    try:
        cols = [r["name"] for r in db.execute("PRAGMA table_info(claims);").fetchall()]
        if cols and "admin_notes" not in cols:
            db.execute("ALTER TABLE claims ADD COLUMN admin_notes TEXT;")
    except Exception:
        pass

    db.commit()


@click.command("init-db")
@click.option("--reset", is_flag=True, default=False, help="Drop existing tables and recreate from scratch.")
@with_appcontext
def init_db_command(reset):
    """CLI command to initialize/reset the SQLite database."""
    init_db(reset=reset)
    click.echo("Successfully initialized the SQLite database.")


def check_db_connection():
    """
    Test database connectivity for health checks.
    Returns a tuple of (is_healthy: bool, message: str).
    """
    try:
        db = get_db()
        cursor = db.execute("SELECT 1;")
        result = cursor.fetchone()
        if result and result[0] == 1:
            return True, "connected"
        return False, "unexpected query result"
    except Exception as exc:
        return False, str(exc)


def init_app(app):
    """Register database teardown and CLI commands with the Flask application."""
    app.teardown_appcontext(close_db)
    app.cli.add_command(init_db_command)
