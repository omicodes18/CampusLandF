"""
Routes package registering Flask blueprints.
"""
from routes.admin_routes import admin_bp
from routes.auth_routes import admin_required, auth_bp, login_required
from routes.claim_routes import claim_bp
from routes.health import health_bp
from routes.item_routes import items_bp

__all__ = [
    "admin_bp",
    "admin_required",
    "auth_bp",
    "claim_bp",
    "health_bp",
    "items_bp",
    "login_required",
]
