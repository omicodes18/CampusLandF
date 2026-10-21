"""
tests/test_claims.py
Automated tests for ownership claims, admin review (approval/rejection),
invalid status transition prevention, and item status lifecycle updates.
"""


def register_and_login(client, name, email, role="student"):
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


def create_found_item(client, title="Found Smart Watch"):
    """Helper to report a found item."""
    res = client.post(
        "/api/items",
        json={
            "title": title,
            "description": "Black silicone strap, found near cafeteria table 6",
            "category": "Electronics",
            "type": "found",
            "location": "Cafeteria Table 6",
            "date_event": "2026-10-21",
        },
    )
    assert res.status_code == 201
    return res.get_json()["item"]["id"]


def test_claim_submission_success(client):
    """Test submitting an ownership claim for a found item returns 201 Created."""
    # Finder reports item
    register_and_login(client, name="Finder Sam", email="finder@college.edu")
    item_id = create_found_item(client, title="Found FitBit Watch")

    # Claimant logs in and submits claim with proof
    register_and_login(client, name="Owner Dave", email="owner.dave@college.edu")
    response = client.post(
        f"/api/items/{item_id}/claims",
        json={
            "proof_details": "It has a scratch on the bezel and the wallpaper is a golden retriever.",
        },
    )
    assert response.status_code == 201
    assert response.is_json

    data = response.get_json()
    assert data["message"] == "Claim submitted successfully"
    claim = data["claim"]
    assert claim["id"] is not None
    assert claim["item_id"] == item_id
    assert claim["status"] == "pending"
    assert "scratch on the bezel" in claim["proof_details"]
    assert claim["claimant_email"] == "owner.dave@college.edu"


def test_claim_submission_unauthenticated(client):
    """Test submitting a claim without authentication returns 401 Unauthorized."""
    response = client.post(
        "/api/items/1/claims",
        json={"proof_details": "This watch belongs to me."},
    )
    assert response.status_code == 401


def test_claim_submission_validations(client):
    """Test claim submission enforces proof length, valid found items, and non-self claiming."""
    # User 1 reports a found item and a lost item
    register_and_login(client, name="User One", email="user1@college.edu")
    found_id = create_found_item(client, title="Found Scientific Calculator")
    lost_res = client.post(
        "/api/items",
        json={
            "title": "Lost Wallet",
            "description": "Lost in library",
            "category": "Bags & Wallets",
            "type": "lost",
            "location": "Library",
            "date_event": "2026-10-21",
        },
    )
    lost_id = lost_res.get_json()["item"]["id"]

    # 1. User 1 cannot claim their own found item
    self_claim = client.post(
        f"/api/items/{found_id}/claims",
        json={"proof_details": "Valid proof details description"},
    )
    assert self_claim.status_code == 400
    assert "cannot submit an ownership claim for an item you reported" in self_claim.get_json()["error"]["message"].lower()

    # User 2 logs in
    register_and_login(client, name="User Two", email="user2@college.edu")

    # 2. Cannot claim a 'lost' item (claims are for found items)
    lost_claim = client.post(
        f"/api/items/{lost_id}/claims",
        json={"proof_details": "Valid proof details description"},
    )
    assert lost_claim.status_code == 400
    assert "only be submitted for found items" in lost_claim.get_json()["error"]["message"].lower()

    # 3. Too short proof description (< 10 chars)
    short_proof = client.post(
        f"/api/items/{found_id}/claims",
        json={"proof_details": "Mine"},
    )
    assert short_proof.status_code == 400
    assert "at least 10 characters" in short_proof.get_json()["error"]["message"].lower()

    # 4. Duplicate pending claim by the same user
    valid_res1 = client.post(
        f"/api/items/{found_id}/claims",
        json={"proof_details": "This calculator has my initials 'U2' engraved."},
    )
    assert valid_res1.status_code == 201

    valid_res2 = client.post(
        f"/api/items/{found_id}/claims",
        json={"proof_details": "Submitting another claim for the same calculator."},
    )
    assert valid_res2.status_code == 400
    assert "already have an active pending claim" in valid_res2.get_json()["error"]["message"].lower()


def test_user_view_own_claims(client):
    """Test user can view their submitted claims via /api/claims/my."""
    register_and_login(client, name="Finder Ann", email="finder.ann@college.edu")
    item_id = create_found_item(client, title="Found USB Drive")

    register_and_login(client, name="Claimant Bob", email="claimant.bob@college.edu")
    client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "It has 32GB capacity and contains CS notes."},
    )

    my_claims_res = client.get("/api/claims/my")
    assert my_claims_res.status_code == 200
    data = my_claims_res.get_json()
    assert data["count"] >= 1
    assert any(c["item_title"] == "Found USB Drive" for c in data["claims"])


def test_admin_approve_claim_and_cascade(client):
    """Test admin approves claim: claim becomes approved, item becomes claimed, other claims rejected."""
    # Finder reports found item
    register_and_login(client, name="Finder Chris", email="finder.chris@college.edu")
    item_id = create_found_item(client, title="Found Prescription Glasses")

    # Claimant 1 submits claim
    register_and_login(client, name="Claimant 1", email="claimant1@college.edu")
    c1_res = client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "Black RayBan frame with -2.5 power lenses."},
    )
    claim1_id = c1_res.get_json()["claim"]["id"]

    # Claimant 2 submits claim for the same item
    register_and_login(client, name="Claimant 2", email="claimant2@college.edu")
    c2_res = client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "Glasses with a small scratch on left arm."},
    )
    claim2_id = c2_res.get_json()["claim"]["id"]

    # Admin logs in and approves Claimant 1's claim
    register_and_login(client, name="Chief Admin", email="admin.claims@college.edu", role="admin")

    # Approve claim 1
    approve_res = client.post(
        f"/api/admin/claims/{claim1_id}/approve",
        json={"admin_notes": "Prescription match verified by clinic."},
    )
    assert approve_res.status_code == 200
    approved_claim = approve_res.get_json()["claim"]
    assert approved_claim["status"] == "approved"
    assert approved_claim["admin_notes"] == "Prescription match verified by clinic."

    # Verify item status was automatically updated to 'claimed'
    item_res = client.get(f"/api/items/{item_id}")
    assert item_res.get_json()["item"]["status"] == "claimed"

    # Verify Claimant 2's pending claim was automatically rejected
    claims_list = client.get(f"/api/admin/claims?item_id={item_id}").get_json()["claims"]
    c2_claim = next(c for c in claims_list if c["id"] == claim2_id)
    assert c2_claim["status"] == "rejected"
    assert "Another claim was approved" in c2_claim["admin_notes"]


def test_admin_reject_claim(client):
    """Test admin rejects claim: claim becomes rejected, item stays open."""
    register_and_login(client, name="Finder Dan", email="dan.finder@college.edu")
    item_id = create_found_item(client, title="Found Umbrella")

    register_and_login(client, name="Claimant Dan", email="dan.claimant@college.edu")
    c_res = client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "Blue umbrella with wooden handle."},
    )
    claim_id = c_res.get_json()["claim"]["id"]

    # Admin rejects claim
    register_and_login(client, name="Admin Reviewer", email="admin.reviewer@college.edu", role="admin")
    reject_res = client.post(
        f"/api/admin/claims/{claim_id}/reject",
        json={"admin_notes": "Incorrect handle color, reported umbrella has plastic handle."},
    )
    assert reject_res.status_code == 200
    assert reject_res.get_json()["claim"]["status"] == "rejected"

    # Item remains 'open' for others to claim
    item_res = client.get(f"/api/items/{item_id}")
    assert item_res.get_json()["item"]["status"] == "open"


def test_invalid_claim_status_transitions(client):
    """Test preventing invalid status transitions on claims."""
    register_and_login(client, name="Finder Eve", email="eve.finder@college.edu")
    item_id = create_found_item(client, title="Found Laptop Bag")

    register_and_login(client, name="Claimant Eve", email="eve.claimant@college.edu")
    c_res = client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "Lenovo branded black bag with a mouse inside."},
    )
    claim_id = c_res.get_json()["claim"]["id"]

    register_and_login(client, name="Admin Eve", email="admin.eve@college.edu", role="admin")

    # Reject the claim
    client.post(f"/api/admin/claims/{claim_id}/reject")

    # Attempting to approve an already rejected claim must fail
    re_approve = client.post(f"/api/admin/claims/{claim_id}/approve")
    assert re_approve.status_code == 400
    assert "already" in re_approve.get_json()["error"]["message"].lower()

    # Attempting to reject again must fail
    re_reject = client.post(f"/api/admin/claims/{claim_id}/reject")
    assert re_reject.status_code == 400


def test_admin_update_item_status_returned_resolved(client):
    """Test admin updating item status to 'returned' or 'resolved' and preventing invalid transitions."""
    register_and_login(client, name="Finder Fred", email="fred.finder@college.edu")
    item_id = create_found_item(client, title="Found College Jacket")

    register_and_login(client, name="Super Admin", email="super.admin@college.edu", role="admin")

    # Update item status to 'returned'
    ret_res = client.patch(
        f"/api/admin/items/{item_id}/status",
        json={"status": "returned"},
    )
    assert ret_res.status_code == 200
    assert ret_res.get_json()["item"]["status"] == "returned"

    # Update item status to 'resolved'
    res_res = client.patch(
        f"/api/admin/items/{item_id}/status",
        json={"status": "resolved"},
    )
    assert res_res.status_code == 200
    assert res_res.get_json()["item"]["status"] == "resolved"

    # Attempting to reopen a resolved item back to 'open' is blocked as an invalid transition
    invalid_reopen = client.patch(
        f"/api/admin/items/{item_id}/status",
        json={"status": "open"},
    )
    assert invalid_reopen.status_code == 400
    assert "cannot be reopened" in invalid_reopen.get_json()["error"]["message"].lower()


def test_unauthorized_admin_actions(client):
    """Test non-admin student is forbidden from approving/rejecting claims and updating item status."""
    register_and_login(client, name="Finder George", email="george.finder@college.edu")
    item_id = create_found_item(client, title="Found Scientific Calculator")

    register_and_login(client, name="Regular Student", email="student.reg@college.edu", role="student")
    c_res = client.post(
        f"/api/items/{item_id}/claims",
        json={"proof_details": "My name is written in marker on back cover."},
    )
    claim_id = c_res.get_json()["claim"]["id"]

    # Student tries to approve their own claim -> 403 Forbidden
    unauth_approve = client.post(f"/api/admin/claims/{claim_id}/approve")
    assert unauth_approve.status_code == 403

    # Student tries to reject -> 403 Forbidden
    unauth_reject = client.post(f"/api/admin/claims/{claim_id}/reject")
    assert unauth_reject.status_code == 403

    # Student tries to update item status -> 403 Forbidden
    unauth_status = client.patch(
        f"/api/admin/items/{item_id}/status",
        json={"status": "resolved"},
    )
    assert unauth_status.status_code == 403

    # Student tries to list all admin claims -> 403 Forbidden
    unauth_list = client.get("/api/admin/claims")
    assert unauth_list.status_code == 403
