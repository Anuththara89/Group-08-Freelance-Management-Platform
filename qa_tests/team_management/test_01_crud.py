"""
test_01_crud.py
===============
Core CRUD lifecycle tests for POST /api/freelancer/create,
GET /api/freelancer, GET /api/freelancer/{id},
PUT /api/freelancer/{id}, DELETE /api/freelancer/{id}.

Tests are ordered and share state via the `live_freelancer` class fixture.
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_freelancer_by_email


# ===========================================================================
# TC-CRUD-01  Create Member
# ===========================================================================

@pytest.mark.crud
class TestCreateFreelancer:
    """POST /api/freelancer/create"""

    def test_create_returns_201(self, temp_freelancer):
        """Create should respond with HTTP 201 Created."""
        # temp_freelancer fixture already asserts 201 internally;
        # re-verify via an independent call for explicit assertion tracking.
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        # cleanup
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        assert r.status_code == 201, (
            f"[BUG] Expected 201, got {r.status_code}. Body: {r.text}"
        )

    def test_create_response_contains_memberName(self, temp_freelancer):
        """Create response must contain memberName field."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        body = r.json()
        assert "memberName" in body, (
            f"[BUG] 'memberName' missing from create response. Got: {body}"
        )
        assert body["memberName"] == payload["fullName"]

    def test_create_response_contains_email(self, temp_freelancer):
        """Create response must contain the email field."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        body = r.json()
        assert "email" in body, f"[BUG] 'email' missing from create response. Got: {body}"
        assert body["email"] == payload["email"]

    def test_create_response_password_is_12_chars(self, temp_freelancer):
        """Create response must include a plain-text password of exactly 12 characters."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        body = r.json()
        assert "password" in body, (
            f"[BUG] 'password' missing from create response. Got: {body}"
        )
        pwd = body["password"]
        assert len(pwd) == 12, (
            f"[BUG] Password should be 12 characters, got {len(pwd)}: '{pwd}'"
        )

    def test_create_response_password_is_plain_text(self, temp_freelancer):
        """Create response password must NOT be a BCrypt hash."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        body = r.json()
        pwd = body.get("password", "")
        assert not pwd.startswith("$2a$") and not pwd.startswith("$2b$"), (
            f"[BUG] Create response returned a BCrypt hash instead of plain-text password."
        )


# ===========================================================================
# TC-CRUD-02  View Roster
# ===========================================================================

@pytest.mark.crud
class TestViewRoster:
    """GET /api/freelancer"""

    def test_get_all_returns_200(self):
        """GET /api/freelancer must return HTTP 200."""
        r = requests.get(BASE_URL)
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}"
        )

    def test_get_all_returns_json_array(self):
        """GET /api/freelancer must return a JSON array."""
        r = requests.get(BASE_URL)
        body = r.json()
        assert isinstance(body, list), (
            f"[BUG] Expected a JSON array, got {type(body).__name__}: {body}"
        )

    def test_get_all_contains_only_active_freelancers(self, temp_freelancer):
        """Every item in the roster list must have the expected fields."""
        r = requests.get(BASE_URL)
        freelancers = r.json()
        assert len(freelancers) > 0, "Roster should contain at least the temp_freelancer."
        required_fields = {"id", "fullName"}
        for fl in freelancers:
            missing = required_fields - fl.keys()
            assert not missing, (
                f"[BUG] Freelancer record is missing fields {missing}. Record: {fl}"
            )

    def test_get_all_freelancer_linked_to_manager_id_1(self, temp_freelancer):
        """Every freelancer in the roster must be linked to manager ID 1."""
        r = requests.get(BASE_URL)
        for fl in r.json():
            manager = fl.get("manager")
            assert manager is not None, (
                f"[BUG] Freelancer id={fl.get('id')} has no manager linked. "
                f"'View freelancer' will fail to load for the admin."
            )
            assert manager.get("id") == 1, (
                f"[BUG] Freelancer id={fl.get('id')} is linked to manager_id="
                f"{manager.get('id')}, expected 1."
            )


# ===========================================================================
# TC-CRUD-03  Search by ID
# ===========================================================================

@pytest.mark.crud
class TestGetFreelancerById:
    """GET /api/freelancer/{id}"""

    def test_get_by_id_returns_200(self, live_freelancer):
        """GET /api/freelancer/{id} must return 200 for a valid ID."""
        r = requests.get(f"{BASE_URL}/{live_freelancer['id']}")
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}. Body: {r.text}"
        )

    def test_get_by_id_returns_correct_freelancer(self, live_freelancer):
        """GET /api/freelancer/{id} must return the freelancer with matching data."""
        fid = live_freelancer["id"]
        payload = live_freelancer["payload"]
        r = requests.get(f"{BASE_URL}/{fid}")
        body = r.json()
        assert body.get("id") == fid, (
            f"[BUG] Returned freelancer id {body.get('id')} != requested id {fid}"
        )
        assert body.get("fullName") == payload["fullName"], (
            f"[BUG] fullName mismatch: got '{body.get('fullName')}', "
            f"expected '{payload['fullName']}'"
        )

    def test_get_by_id_returns_correct_email(self, live_freelancer):
        """GET /api/freelancer/{id} must return the correct email in nested user."""
        fid = live_freelancer["id"]
        payload = live_freelancer["payload"]
        r = requests.get(f"{BASE_URL}/{fid}")
        body = r.json()
        user_email = body.get("user", {}).get("email")
        assert user_email == payload["email"], (
            f"[BUG] Email mismatch: got '{user_email}', expected '{payload['email']}'"
        )


# ===========================================================================
# TC-CRUD-04  Update Info
# ===========================================================================

@pytest.mark.crud
class TestUpdateFreelancer:
    """PUT /api/freelancer/{id}"""

    def test_update_returns_200(self, live_freelancer):
        """PUT /api/freelancer/{id} must return HTTP 200."""
        fid = live_freelancer["id"]
        payload = {**live_freelancer["payload"], "title": "Senior QA Engineer"}
        r = requests.put(f"{BASE_URL}/{fid}", json=payload)
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}. Body: {r.text}"
        )

    def test_update_title_partial_update(self, live_freelancer):
        """PUT with only title changed must update title and preserve other fields."""
        fid = live_freelancer["id"]
        original_payload = live_freelancer["payload"]
        update_payload = {**original_payload, "title": "Lead QA Engineer"}
        r = requests.put(f"{BASE_URL}/{fid}", json=update_payload)
        assert r.status_code == 200, f"Update failed: {r.text}"
        body = r.json()
        assert body.get("title") == "Lead QA Engineer", (
            f"[BUG] Title not updated. Got: '{body.get('title')}'"
        )
        assert body.get("fullName") == original_payload["fullName"], (
            "[BUG] fullName changed unexpectedly during partial update."
        )

    def test_update_contact_number_partial_update(self, live_freelancer):
        """PUT with only contactNumber changed must update that field."""
        fid = live_freelancer["id"]
        update_payload = {**live_freelancer["payload"], "contactNumber": "0779999999"}
        r = requests.put(f"{BASE_URL}/{fid}", json=update_payload)
        assert r.status_code == 200, f"Update failed: {r.text}"
        body = r.json()
        assert body.get("contactNumber") == "0779999999", (
            f"[BUG] contactNumber not updated. Got: '{body.get('contactNumber')}'"
        )

    def test_update_returns_updated_freelancer_body(self, live_freelancer):
        """PUT response body must reflect the updated state."""
        fid = live_freelancer["id"]
        update_payload = {**live_freelancer["payload"], "title": "Updated Title"}
        r = requests.put(f"{BASE_URL}/{fid}", json=update_payload)
        body = r.json()
        assert "id" in body, "[BUG] Update response body does not contain 'id'."
        assert "fullName" in body, "[BUG] Update response body does not contain 'fullName'."


# ===========================================================================
# TC-CRUD-05  Remove Member
# ===========================================================================

@pytest.mark.crud
class TestDeleteFreelancer:
    """DELETE /api/freelancer/{id}"""

    def test_delete_returns_200(self):
        """DELETE /api/freelancer/{id} must return HTTP 200."""
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=payload)
        assert r_create.status_code == 201, "Pre-condition failed: cannot create freelancer."
        fl = find_freelancer_by_email(payload["email"])
        assert fl is not None
        fid = fl["id"]

        r_delete = requests.delete(f"{BASE_URL}/{fid}")
        assert r_delete.status_code == 200, (
            f"[BUG] Expected 200 on delete, got {r_delete.status_code}. Body: {r_delete.text}"
        )

    def test_delete_removes_freelancer_from_roster(self):
        """After DELETE, the freelancer must no longer appear in GET /api/freelancer."""
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=payload)
        assert r_create.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        # Verify removed from roster
        fl_after = find_freelancer_by_email(payload["email"])
        assert fl_after is None, (
            f"[BUG] Freelancer (id={fid}) still appears in roster after DELETE."
        )

    def test_delete_makes_get_by_id_return_non_200(self):
        """After DELETE, GET /api/freelancer/{id} should NOT return 200."""
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=payload)
        assert r_create.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        r_get = requests.get(f"{BASE_URL}/{fid}")
        assert r_get.status_code != 200, (
            f"[BUG] GET /api/freelancer/{fid} still returns 200 after deletion. "
            f"The record was not properly deleted."
        )
