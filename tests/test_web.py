"""
tests/test_web.py
Automated tests for frontend web pages and template rendering.
"""


def test_homepage_html_rendering(client):
    """Test that GET / with Accept text/html renders the Stitch UI homepage."""
    response = client.get("/", headers={"Accept": "text/html,application/xhtml+xml"})
    assert response.status_code == 200
    assert not response.is_json
    html = response.get_data(as_text=True)
    assert "Campus Lost &amp; Found" in html or "Campus Lost & Found" in html
    assert "Official Campus Directory" in html


def test_home_route_rendering(client):
    """Test GET /home renders the homepage template."""
    response = client.get("/home")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Let’s bring it home" in html or "bring it home" in html


def test_board_route_rendering(client):
    """Test GET /browse and GET /board render the items catalog board."""
    for path in ["/browse", "/board"]:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "The campus lost &amp; found board" in html or "lost & found board" in html
        assert "Filters" in html
        assert "All Categories" in html


def test_report_route_rendering(client):
    """Test GET /report renders the lost/found item submission form."""
    response = client.get("/report")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Report Lost Item" in html
    assert "Item Name" in html

    # Found item report view
    response_found = client.get("/report?type=found")
    assert response_found.status_code == 200
    html_found = response_found.get_data(as_text=True)
    assert "Found something on campus?" in html_found


def test_claims_route_rendering(client):
    """Test GET /claims and GET /my-claims render the claims page."""
    for path in ["/claims", "/my-claims"]:
        response = client.get(path)
        assert response.status_code == 200
        html = response.get_data(as_text=True)
        assert "My Ownership Claims" in html


def test_admin_route_rendering(client):
    """Test GET /admin renders the admin management dashboard."""
    response = client.get("/admin")
    assert response.status_code == 200
    html = response.get_data(as_text=True)
    assert "Campus Registry Management" in html
    assert "Ownership Claims Review" in html
