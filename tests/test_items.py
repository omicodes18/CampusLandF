"""
tests/test_items.py
Automated tests for lost & found item reporting, image uploads, search, filters, and authorization.
"""

import io
import os


def register_and_login(client, name="Item Tester", email="itemuser@college.edu", role="student"):
    """Helper to register and log in a user with a clean session."""
    client.post("/api/auth/logout")
    client.post(
        "/api/auth/register",
        json={"name": name, "email": email, "password": "Password123", "role": role},
    )
    res = client.post(
        "/api/auth/login",
        json={"email": email, "password": "Password123"},
    )
    assert res.status_code == 200


def test_create_report_unauthenticated(client):
    """Test reporting an item without authentication returns 401 Unauthorized."""
    response = client.post(
        "/api/items",
        json={
            "title": "Lost Wallet",
            "description": "Black leather wallet",
            "category": "Bags & Wallets",
            "type": "lost",
            "location": "Cafeteria",
            "date_event": "2026-10-21",
        },
    )
    assert response.status_code == 401
    assert "authentication required" in response.get_json()["error"]["message"].lower()


def test_create_report_success_json(client):
    """Test reporting an item with valid JSON payload returns 201 Created."""
    register_and_login(client, name="Alice Student", email="alice.student@college.edu")

    response = client.post(
        "/api/items",
        json={
            "title": "Casio Scientific Calculator",
            "description": "FX-991EX model left on desk in Room 204",
            "category": "Electronics",
            "type": "lost",
            "location": "Room 204 Academic Block",
            "date_event": "2026-10-21",
            "contact_email": "alice.student@college.edu",
            "contact_phone": "9876543210",
        },
    )
    assert response.status_code == 201
    assert response.is_json

    data = response.get_json()
    assert data["message"] == "Item reported successfully"
    item = data["item"]
    assert item["id"] is not None
    assert item["title"] == "Casio Scientific Calculator"
    assert item["category"] == "Electronics"
    assert item["type"] == "lost"
    assert item["status"] == "open"
    assert item["image_filename"] is None


def test_create_report_with_image_upload(client, app):
    """Test reporting an item with a valid image upload saves file and records path."""
    register_and_login(client, name="Bob Uploader", email="bob.uploader@college.edu")

    dummy_image = (io.BytesIO(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDRfakeimage"), "test_id_card.png")

    response = client.post(
        "/api/items",
        data={
            "title": "College Student ID Card",
            "description": "Found near chemistry lab corridor",
            "category": "ID Cards & Documents",
            "type": "found",
            "location": "Chemistry Block, Ground Floor",
            "date_event": "2026-10-21",
            "image": dummy_image,
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 201
    item = response.get_json()["item"]

    assert item["image_filename"] is not None
    assert item["image_filename"].endswith("_test_id_card.png")

    # Verify physical file existence in uploads directory
    uploaded_filepath = os.path.join(app.config["UPLOAD_FOLDER"], item["image_filename"])
    assert os.path.isfile(uploaded_filepath)

    # Verify image retrieval endpoint
    img_res = client.get(f"/uploads/{item['image_filename']}")
    assert img_res.status_code == 200

    # Cleanup test file
    if os.path.exists(uploaded_filepath):
        os.remove(uploaded_filepath)


def test_image_upload_invalid_file_type(client):
    """Test uploading a file with an invalid extension (e.g. .exe/.sh) returns 400 Bad Request."""
    register_and_login(client, name="Malicious User", email="malicious@college.edu")

    bad_file = (io.BytesIO(b"malicious script contents"), "exploit.sh")

    response = client.post(
        "/api/items",
        data={
            "title": "Lost Notebook",
            "description": "Algorithms notes",
            "category": "Books & Stationery",
            "type": "lost",
            "location": "Library",
            "date_event": "2026-10-21",
            "image": bad_file,
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "invalid file type" in response.get_json()["error"]["message"].lower()


def test_image_upload_file_size_limit(client):
    """Test uploading an image exceeding 5MB returns 400 Bad Request."""
    register_and_login(client, name="Big File User", email="bigfile@college.edu")

    # Construct file slightly above 5MB limit
    oversized_data = b"0" * (6 * 1024 * 1024)
    oversized_file = (io.BytesIO(oversized_data), "large_photo.jpg")

    response = client.post(
        "/api/items",
        data={
            "title": "Lost Jacket",
            "description": "Black winter jacket",
            "category": "Clothing",
            "type": "lost",
            "location": "Sports Complex",
            "date_event": "2026-10-21",
            "image": oversized_file,
        },
        content_type="multipart/form-data",
    )
    assert response.status_code == 400
    assert "exceeds maximum limit" in response.get_json()["error"]["message"].lower()


def test_create_report_invalid_inputs(client):
    """Test input validations for required fields and domain constraints."""
    register_and_login(client, name="Val User", email="val@college.edu")

    # Missing title
    res1 = client.post("/api/items", json={
        "description": "Some description",
        "category": "Electronics",
        "type": "lost",
        "location": "Canteen",
        "date_event": "2026-10-21",
    })
    assert res1.status_code == 400
    assert "title" in res1.get_json()["error"]["message"].lower()

    # Invalid category
    res2 = client.post("/api/items", json={
        "title": "Car Keys",
        "description": "Found near gate",
        "category": "Automobiles",  # Invalid
        "type": "found",
        "location": "Main Gate",
        "date_event": "2026-10-21",
    })
    assert res2.status_code == 400
    assert "invalid category" in res2.get_json()["error"]["message"].lower()

    # Invalid type
    res3 = client.post("/api/items", json={
        "title": "Car Keys",
        "description": "Found near gate",
        "category": "Keys",
        "type": "stolen",  # Invalid, only lost/found allowed
        "location": "Main Gate",
        "date_event": "2026-10-21",
    })
    assert res3.status_code == 400
    assert "invalid type" in res3.get_json()["error"]["message"].lower()


def test_retrieve_items_and_single_item(client):
    """Test listing items and fetching a specific item by ID."""
    register_and_login(client, name="Reader User", email="reader@college.edu")

    # Create two items
    client.post("/api/items", json={
        "title": "Blue Umbrella",
        "description": "Left near cafeteria umbrella stand",
        "category": "Others",
        "type": "found",
        "location": "Cafeteria",
        "date_event": "2026-10-20",
    })
    item2_res = client.post("/api/items", json={
        "title": "Noise Cancelling Headphones",
        "description": "Sony WH-1000XM4 in black case",
        "category": "Electronics",
        "type": "lost",
        "location": "Reading Hall 1",
        "date_event": "2026-10-21",
    })
    created_id = item2_res.get_json()["item"]["id"]

    # Public listing
    list_res = client.get("/api/items")
    assert list_res.status_code == 200
    assert list_res.get_json()["count"] >= 2

    # Fetch existing item by ID
    single_res = client.get(f"/api/items/{created_id}")
    assert single_res.status_code == 200
    assert single_res.get_json()["item"]["title"] == "Noise Cancelling Headphones"

    # Non-existent item
    missing_res = client.get("/api/items/999999")
    assert missing_res.status_code == 404


def test_search_and_filters(client):
    """Test searching by keyword and filtering by category, location, type, and status."""
    register_and_login(client, name="Search Tester", email="searcher@college.edu")

    # Item A: lost, Electronics, Library
    client.post("/api/items", json={
        "title": "Scientific Calculator Casio",
        "description": "Silver edition with name sticker",
        "category": "Electronics",
        "type": "lost",
        "location": "Central Library 3rd Floor",
        "date_event": "2026-10-18",
    })
    # Item B: found, Books & Stationery, Canteen
    client.post("/api/items", json={
        "title": "Data Structures Textbook",
        "description": "Author Cormen with blue cover",
        "category": "Books & Stationery",
        "type": "found",
        "location": "Student Canteen",
        "date_event": "2026-10-19",
    })
    # Item C: found, Electronics, Auditorium
    client.post("/api/items", json={
        "title": "Apple USB-C Adapter",
        "description": "White 20W power adapter",
        "category": "Electronics",
        "type": "found",
        "location": "Main Auditorium Stage",
        "date_event": "2026-10-20",
    })

    # Keyword search: matches "Casio"
    res_search = client.get("/api/items?q=Casio")
    assert res_search.status_code == 200
    items = res_search.get_json()["items"]
    assert len(items) == 1
    assert "Casio" in items[0]["title"]

    # Keyword search matching location: "Auditorium"
    res_loc_search = client.get("/api/items?q=Auditorium")
    assert len(res_loc_search.get_json()["items"]) == 1

    # Filter by type: lost
    res_type = client.get("/api/items?type=lost")
    for itm in res_type.get_json()["items"]:
        assert itm["type"] == "lost"

    # Filter by category: Electronics
    res_cat = client.get("/api/items?category=Electronics")
    for itm in res_cat.get_json()["items"]:
        assert itm["category"] == "Electronics"

    # Filter by location
    res_loc = client.get("/api/items?location=Canteen")
    assert len(res_loc.get_json()["items"]) == 1
    assert res_loc.get_json()["items"][0]["category"] == "Books & Stationery"


def test_unauthorized_edit_unauthenticated(client):
    """Test modifying an item without logging in returns 401 Unauthorized."""
    register_and_login(client, name="Owner User", email="owner1@college.edu")
    res = client.post("/api/items", json={
        "title": "Lab Coat",
        "description": "White lab coat with initials MS",
        "category": "Clothing",
        "type": "lost",
        "location": "Bio Lab 2",
        "date_event": "2026-10-21",
    })
    item_id = res.get_json()["item"]["id"]

    # Logout
    client.post("/api/auth/logout")

    # Attempt edit
    edit_res = client.put(f"/api/items/{item_id}", json={"location": "Bio Lab 3"})
    assert edit_res.status_code == 401


def test_unauthorized_edit_by_different_user(client):
    """Test modifying an item reported by another user returns 403 Forbidden."""
    # User 1 reports an item
    register_and_login(client, name="Original Owner", email="orig.owner@college.edu")
    res = client.post("/api/items", json={
        "title": "Sports Water Bottle",
        "description": "Red Milton 1L bottle",
        "category": "Others",
        "type": "lost",
        "location": "Gymnasium",
        "date_event": "2026-10-21",
    })
    item_id = res.get_json()["item"]["id"]

    # User 2 logs in
    register_and_login(client, name="Intruder User", email="intruder@college.edu")

    # User 2 attempts to edit User 1's report
    unauthorized_res = client.put(
        f"/api/items/{item_id}",
        json={"title": "Hacked Title", "status": "claimed"},
    )
    assert unauthorized_res.status_code == 403
    assert "only authorized to edit your own reports" in unauthorized_res.get_json()["error"]["message"].lower()

    # Verify original item was NOT modified
    verify_res = client.get(f"/api/items/{item_id}")
    assert verify_res.get_json()["item"]["title"] == "Sports Water Bottle"


def test_authorized_edit_by_owner(client):
    """Test that the owner of an item can successfully edit the report."""
    register_and_login(client, name="Rightful Owner", email="rightful.owner@college.edu")
    res = client.post("/api/items", json={
        "title": "Set of Room Keys",
        "description": "Three silver keys on a blue keychain",
        "category": "Keys",
        "type": "lost",
        "location": "Hostel Block B",
        "date_event": "2026-10-20",
    })
    item_id = res.get_json()["item"]["id"]

    # Owner updates status to 'claimed' and notes additional location details
    update_res = client.put(
        f"/api/items/{item_id}",
        json={
            "location": "Hostel Block B, Room 312",
            "status": "claimed",
        },
    )
    assert update_res.status_code == 200
    updated_item = update_res.get_json()["item"]
    assert updated_item["location"] == "Hostel Block B, Room 312"
    assert updated_item["status"] == "claimed"


def test_authorized_edit_by_admin(client):
    """Test that an administrator can edit any item report."""
    # Student creates report
    register_and_login(client, name="Student Reporter", email="reporter.student@college.edu", role="student")
    res = client.post("/api/items", json={
        "title": "Graphing Notebook",
        "description": "Spiral bound",
        "category": "Books & Stationery",
        "type": "found",
        "location": "Lab 4",
        "date_event": "2026-10-21",
    })
    item_id = res.get_json()["item"]["id"]

    # Admin logs in
    register_and_login(client, name="Chief Admin", email="admin.mod@college.edu", role="admin")

    # Admin updates item status to resolved
    admin_res = client.patch(
        f"/api/items/{item_id}",
        json={"status": "resolved"},
    )
    assert admin_res.status_code == 200
    assert admin_res.get_json()["item"]["status"] == "resolved"


def test_delete_item_authorization(client):
    """Test that only item owner or admin can delete an item report."""
    # Owner creates item
    register_and_login(client, name="Delete Owner", email="del.owner@college.edu")
    res = client.post("/api/items", json={
        "title": "USB Pen Drive 32GB",
        "description": "SanDisk metal casing",
        "category": "Electronics",
        "type": "found",
        "location": "Computer Lab 1",
        "date_event": "2026-10-21",
    })
    item_id = res.get_json()["item"]["id"]

    # Different user attempts delete -> 403
    register_and_login(client, name="Other User", email="other.del@college.edu")
    fail_del = client.delete(f"/api/items/{item_id}")
    assert fail_del.status_code == 403

    # Owner deletes item -> 200
    register_and_login(client, name="Delete Owner", email="del.owner@college.edu")
    success_del = client.delete(f"/api/items/{item_id}")
    assert success_del.status_code == 200

    # Ensure item no longer exists -> 404
    get_res = client.get(f"/api/items/{item_id}")
    assert get_res.status_code == 404
