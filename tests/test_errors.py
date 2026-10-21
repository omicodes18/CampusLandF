"""
tests/test_errors.py
Automated tests for custom error handlers ensuring structured JSON responses.
"""


def test_404_not_found(client):
    """Test accessing an unknown endpoint returns JSON formatted 404."""
    response = client.get("/api/non-existent-route")
    assert response.status_code == 404
    assert response.is_json

    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == 404
    assert data["error"]["name"] == "Not Found"


def test_405_method_not_allowed(client):
    """Test using an unsupported HTTP method returns JSON formatted 405."""
    response = client.post("/api/health")
    assert response.status_code == 405
    assert response.is_json

    data = response.get_json()
    assert "error" in data
    assert data["error"]["code"] == 405
    assert data["error"]["name"] == "Method Not Allowed"
