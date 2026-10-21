"""
tests/test_audit.py
Security, edge-case, and failure-scenario tests covering the comprehensive audit requirements:
- Invalid date formats
- Non-existent resource handling (404)
- Case-insensitive search and filters
- Stale/deleted user session revocation
- Missing uploaded files (404)
- Notifications lifecycle (listing and marking as read)
- Database CLI reset capability
"""

from database import get_db


def test_invalid_date_format_in_item_report(client):
    """Test reporting an item with a malformed date string returns 400 Bad Request."""
    client.post(
        "/api/auth/register",
        json={"name": "Date Tester", "email": "datetest@college.edu", "password": "Password123"},
    )
    client.post("/api/auth/login", json={"email": "datetest@college.edu", "password": "Password123"})

    response = client.post(
        "/api/items",
        json={
            "title": "Lost Wallet",
            "description": "Black leather wallet",
            "category": "Bags & Wallets",
            "type": "lost",
            "location": "Cafeteria",
            "date_event": "not-a-valid-date",
        },
    )
    assert response.status_code == 400
    assert "YYYY-MM-DD" in response.get_json()["error"]["message"]


def test_case_insensitive_filtering(client):
    """Test filtering by type, category, and status works case-insensitively."""
    client.post(
        "/api/auth/register",
        json={"name": "Case User", "email": "caseuser@college.edu", "password": "Password123"},
    )
    client.post("/api/auth/login", json={"email": "caseuser@college.edu", "password": "Password123"})

    client.post(
        "/api/items",
        json={
            "title": "Graphing Calculator",
            "description": "Silver Texas Instruments",
            "category": "Electronics",
            "type": "lost",
            "location": "Math Lab",
            "date_event": "2026-10-21",
        },
    )

    # Test uppercase type
    res_type = client.get("/api/items?type=LOST")
    assert res_type.status_code == 200
    assert len(res_type.get_json()["items"]) >= 1

    # Test lowercase category
    res_cat = client.get("/api/items?category=electronics")
    assert res_cat.status_code == 200
    assert len(res_cat.get_json()["items"]) >= 1

    # Test uppercase status
    res_status = client.get("/api/items?status=OPEN")
    assert res_status.status_code == 200
    assert len(res_status.get_json()["items"]) >= 1


def test_nonexistent_item_claim_returns_404(client):
    """Test claiming an item ID that does not exist returns 404 Not Found."""
    client.post(
        "/api/auth/register",
        json={"name": "Claim 404 User", "email": "claim404@college.edu", "password": "Password123"},
    )
    client.post("/api/auth/login", json={"email": "claim404@college.edu", "password": "Password123"})

    response = client.post(
        "/api/items/999999/claims",
        json={"proof_details": "Valid proof details for non-existent item"},
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == 404


def test_nonexistent_item_status_update_returns_404(client):
    """Test updating the status of a non-existent item returns 404 Not Found."""
    client.post(
        "/api/auth/register",
        json={"name": "Admin 404", "email": "admin404@college.edu", "password": "Password123", "role": "admin"},
    )
    client.post("/api/auth/login", json={"email": "admin404@college.edu", "password": "Password123"})

    response = client.patch(
        "/api/admin/items/999999/status",
        json={"status": "resolved"},
    )
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == 404


def test_nonexistent_claim_review_returns_404(client):
    """Test reviewing a non-existent claim returns 404 Not Found."""
    client.post(
        "/api/auth/register",
        json={"name": "Admin 404 B", "email": "admin404b@college.edu", "password": "Password123", "role": "admin"},
    )
    client.post("/api/auth/login", json={"email": "admin404b@college.edu", "password": "Password123"})

    response = client.post("/api/admin/claims/999999/approve")
    assert response.status_code == 404
    assert response.get_json()["error"]["code"] == 404


def test_download_missing_uploaded_image_returns_404_json(client):
    """Test requesting a non-existent uploaded image returns structured JSON 404."""
    response = client.get("/uploads/completely_fake_image_file.png")
    assert response.status_code == 404
    assert response.is_json
    assert response.get_json()["error"]["code"] == 404


def test_stale_deleted_user_session_revoked(client, app):
    """Test that if a user record is deleted from the DB, any active session is revoked with 401."""
    # Register and login
    client.post(
        "/api/auth/register",
        json={"name": "Temporary User", "email": "temp@college.edu", "password": "Password123"},
    )
    login_res = client.post("/api/auth/login", json={"email": "temp@college.edu", "password": "Password123"})
    user_id = login_res.get_json()["user"]["id"]

    # Delete user directly from DB
    with app.app_context():
        db = get_db()
        db.execute("DELETE FROM users WHERE id = ?", (user_id,))
        db.commit()

    # Attempting to access protected endpoint should fail with 401 and clear session
    response = client.get("/api/auth/me")
    assert response.status_code == 401
    assert "no longer valid" in response.get_json()["error"]["message"].lower()

    # Next call should be completely unauthorized
    response2 = client.get("/api/auth/me")
    assert response2.status_code == 401


def test_notifications_endpoint_and_read_state(client):
    """Test fetching user notifications and marking one as read."""
    # Finder creates found item
    client.post(
        "/api/auth/register",
        json={"name": "Finder Notif", "email": "finder.notif@college.edu", "password": "Password123"},
    )
    client.post("/api/auth/login", json={"email": "finder.notif@college.edu", "password": "Password123"})
    item_res = client.post(
        "/api/items",
        json={
            "title": "Found Silver Key",
            "description": "Small locker key found near gym",
            "category": "Keys",
            "type": "found",
            "location": "Gym Corridor",
            "date_event": "2026-10-21",
        },
    )
    item_id = item_res.get_json()["item"]["id"]

    # Claimant submits claim -> triggers notification for Finder
    client.post(
        "/api/auth/register",
        json={"name": "Claimant Notif", "email": "claimant.notif@college.edu", "password": "Password123"},
    )
    client.post("/api/auth/login", json={"email": "claimant.notif@college.edu", "password": "Password123"})
    client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "This is my gym locker key #42."},
    )

    # Finder logs back in and checks notifications
    client.post("/api/auth/login", json={"email": "finder.notif@college.edu", "password": "Password123"})
    notifs_res = client.get("/api/auth/notifications")
    assert notifs_res.status_code == 200
    data = notifs_res.get_json()
    assert data["count"] >= 1
    notif = data["notifications"][0]
    assert notif["is_read"] is False
    notif_id = notif["id"]

    # Mark notification as read
    read_res = client.patch(f"/api/auth/notifications/{notif_id}/read")
    assert read_res.status_code == 200

    # Verify notification is now marked read
    notifs_updated = client.get("/api/auth/notifications").get_json()["notifications"]
    target_notif = next(n for n in notifs_updated if n["id"] == notif_id)
    assert target_notif["is_read"] is True


def test_cli_init_db_reset(runner):
    """Test running 'flask init-db --reset' executes successfully and recreates schema."""
    result = runner.invoke(args=["init-db", "--reset"])
    assert result.exit_code == 0
    assert "Successfully initialized" in result.output
