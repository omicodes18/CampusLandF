"""
tests/test_auth.py
Automated tests for user registration, authentication, sessions, and role-based access control.
"""


def test_successful_registration(client):
    """Test user registration with valid details returns 201 Created."""
    response = client.post(
        "/api/auth/register",
        json={
            "name": "Jane Doe",
            "email": "jane@college.edu",
            "password": "Password123",
            "role": "student",
            "phone": "9876543210",
        },
    )
    assert response.status_code == 201
    assert response.is_json

    data = response.get_json()
    assert data["message"] == "User registered successfully"
    assert data["user"]["id"] is not None
    assert data["user"]["name"] == "Jane Doe"
    assert data["user"]["email"] == "jane@college.edu"
    assert data["user"]["role"] == "student"
    # Verify password hash is NEVER leaked in response
    assert "password" not in data["user"]
    assert "password_hash" not in data["user"]


def test_registration_validation_errors(client):
    """Test registration rejects invalid or missing fields with 400 Bad Request."""
    # Missing/too short name
    res = client.post(
        "/api/auth/register",
        json={"name": "A", "email": "valid@college.edu", "password": "Password123"},
    )
    assert res.status_code == 400
    assert "name" in res.get_json()["error"]["message"].lower()

    # Invalid email format
    res = client.post(
        "/api/auth/register",
        json={"name": "John Doe", "email": "not-an-email", "password": "Password123"},
    )
    assert res.status_code == 400
    assert "email" in res.get_json()["error"]["message"].lower()

    # Password too short (< 8 chars)
    res = client.post(
        "/api/auth/register",
        json={"name": "John Doe", "email": "john@college.edu", "password": "short"},
    )
    assert res.status_code == 400
    assert "8 characters" in res.get_json()["error"]["message"].lower()

    # Invalid role
    res = client.post(
        "/api/auth/register",
        json={"name": "John Doe", "email": "john@college.edu", "password": "Password123", "role": "superman"},
    )
    assert res.status_code == 400
    assert "role" in res.get_json()["error"]["message"].lower()


def test_duplicate_registration(client):
    """Test that attempting to register an existing email returns 409 Conflict."""
    payload = {
        "name": "Original User",
        "email": "duplicate@college.edu",
        "password": "Password123",
    }

    # First registration: succeeds
    res1 = client.post("/api/auth/register", json=payload)
    assert res1.status_code == 201

    # Second registration with identical email: must fail with 409 Conflict
    res2 = client.post(
        "/api/auth/register",
        json={
            "name": "Different Name",
            "email": "duplicate@college.edu",
            "password": "AnotherPassword456",
        },
    )
    assert res2.status_code == 409
    assert res2.is_json
    data = res2.get_json()
    assert "already exists" in data["error"]["message"].lower()


def test_successful_login_and_logout(client):
    """Test login sets session and logout destroys session."""
    # Register first
    client.post(
        "/api/auth/register",
        json={"name": "Login User", "email": "login@college.edu", "password": "SecretPassword123"},
    )

    # Login
    response = client.post(
        "/api/auth/login",
        json={"email": "login@college.edu", "password": "SecretPassword123"},
    )
    assert response.status_code == 200
    data = response.get_json()
    assert data["message"] == "Login successful"
    assert data["user"]["email"] == "login@college.edu"

    # Profile route /api/auth/me should succeed using the active session cookie
    me_response = client.get("/api/auth/me")
    assert me_response.status_code == 200
    assert me_response.get_json()["user"]["email"] == "login@college.edu"

    # Logout
    logout_res = client.post("/api/auth/logout")
    assert logout_res.status_code == 200
    assert logout_res.get_json()["message"] == "Logged out successfully"

    # Profile route should now return 401 Unauthorized
    me_after_logout = client.get("/api/auth/me")
    assert me_after_logout.status_code == 401


def test_login_incorrect_password(client):
    """Test that login with wrong password returns 401 Unauthorized."""
    # Register
    client.post(
        "/api/auth/register",
        json={"name": "Test User", "email": "wrongpwd@college.edu", "password": "CorrectPassword123"},
    )

    # Attempt login with wrong password
    response = client.post(
        "/api/auth/login",
        json={"email": "wrongpwd@college.edu", "password": "WrongPassword999"},
    )
    assert response.status_code == 401
    assert response.is_json
    data = response.get_json()
    assert "invalid email or password" in data["error"]["message"].lower()


def test_login_nonexistent_user(client):
    """Test login with an unregistered email returns 401 Unauthorized."""
    response = client.post(
        "/api/auth/login",
        json={"email": "nobody@college.edu", "password": "AnyPassword123"},
    )
    assert response.status_code == 401
    data = response.get_json()
    assert "invalid email or password" in data["error"]["message"].lower()


def test_unauthorized_admin_access_unauthenticated(client):
    """Test accessing admin endpoint without being logged in returns 401 Unauthorized."""
    response = client.get("/api/admin/users")
    assert response.status_code == 401
    assert response.is_json
    data = response.get_json()
    assert data["error"]["code"] == 401
    assert "authentication required" in data["error"]["message"].lower()


def test_unauthorized_admin_access_as_student(client):
    """Test that authenticated non-admin (student) user gets 403 Forbidden on admin routes."""
    # Register and log in as regular student
    client.post(
        "/api/auth/register",
        json={"name": "Normal Student", "email": "student@college.edu", "password": "Password123", "role": "student"},
    )
    client.post(
        "/api/auth/login",
        json={"email": "student@college.edu", "password": "Password123"},
    )

    # Attempt to access admin routes
    users_res = client.get("/api/admin/users")
    assert users_res.status_code == 403
    assert users_res.is_json
    data = users_res.get_json()
    assert data["error"]["code"] == 403
    assert "admin privileges required" in data["error"]["message"].lower()

    stats_res = client.get("/api/admin/stats")
    assert stats_res.status_code == 403


def test_authorized_admin_access(client):
    """Test that authenticated admin user can successfully access admin routes."""
    # Register and log in as admin
    client.post(
        "/api/auth/register",
        json={"name": "College Admin", "email": "admin@college.edu", "password": "AdminPassword123", "role": "admin"},
    )
    client.post(
        "/api/auth/login",
        json={"email": "admin@college.edu", "password": "AdminPassword123"},
    )

    # Access admin users list
    users_res = client.get("/api/admin/users")
    assert users_res.status_code == 200
    assert users_res.is_json
    data = users_res.get_json()
    assert data["count"] >= 1
    assert any(u["email"] == "admin@college.edu" for u in data["users"])

    # Access admin stats
    stats_res = client.get("/api/admin/stats")
    assert stats_res.status_code == 200
    stats_data = stats_res.get_json()["stats"]
    assert "total_users" in stats_data
    assert "total_items" in stats_data
    assert "total_claims" in stats_data
    assert "total_notifications" in stats_data
