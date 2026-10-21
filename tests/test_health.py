"""
tests/test_health.py
Automated tests for health check and root status endpoints.
"""


def test_api_health_endpoint(client):
    """Test that /api/health returns 200 OK and connected database status."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["service"] == "College Lost & Found Management API"
    assert "version" in data
    assert "timestamp" in data
    assert data["database"]["status"] == "connected"
    assert data["database"]["type"] == "SQLite"


def test_health_alias_endpoint(client):
    """Test that /health route aliases correctly to health check."""
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "healthy"
    assert data["database"]["status"] == "connected"


def test_root_index_endpoint(client):
    """Test that GET / returns API metadata and links to health check."""
    response = client.get("/")
    assert response.status_code == 200
    assert response.is_json

    data = response.get_json()
    assert data["status"] == "online"
    assert data["health_check"] == "/api/health"
