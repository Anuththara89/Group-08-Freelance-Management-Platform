"""
test_01_crud.py
===============
Core CRUD lifecycle tests for the Freelancer API.

These tests verify the five basic operations:
  1. CREATE  - POST /api/freelancer/create
  2. READ    - GET  /api/freelancer  (all freelancers)
  3. READ    - GET  /api/freelancer/{id}  (single freelancer)
  4. UPDATE  - PUT  /api/freelancer/{id}
  5. DELETE  - DELETE /api/freelancer/{id}
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
        """
        WHAT:  Send a valid POST request with email + fullName to create a freelancer.
        WHY:   The API must respond with HTTP 201 (Created) when input is valid.
        CHECK: response.status_code == 201
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        # cleanup the freelancer we just created so it doesn't pollute the DB
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        assert r.status_code == 201, (
            f"[BUG] Expected 201, got {r.status_code}. Body: {r.text}"
        )

    def test_create_response_contains_memberName(self, temp_freelancer):
        """
        WHAT:  After creating a freelancer, check the JSON response body.
        WHY:   The response must include "memberName" matching the fullName we sent,
               so the frontend can display a confirmation.
        CHECK: "memberName" key exists AND equals the fullName from our request.
        """
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
        """
        WHAT:  After creating a freelancer, check the JSON response body.
        WHY:   The response must echo back the "email" we sent,
               confirming the correct account was created.
        CHECK: "email" key exists AND matches our input.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")
        body = r.json()
        assert "email" in body, f"[BUG] 'email' missing from create response. Got: {body}"
        assert body["email"] == payload["email"]

    def test_create_response_password_is_12_chars(self, temp_freelancer):
        """
        WHAT:  After creating a freelancer, check the password in the response.
        WHY:   The system auto-generates a 12-character onboarding password.
               This password is shown ONCE so the admin can share it with the freelancer.
        CHECK: "password" key exists AND is exactly 12 characters long.
        """
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
        """
        WHAT:  Verify the password in the create response is plain text, not a hash.
        WHY:   The admin needs a readable password to give to the freelancer.
               If the API accidentally returns the BCrypt hash (starts with "$2a$"),
               it's useless for onboarding.
        CHECK: password does NOT start with "$2a$" or "$2b$".
        """
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
# TC-CRUD-02  View Roster (list all freelancers)
# ===========================================================================

@pytest.mark.crud
class TestViewRoster:
    """GET /api/freelancer — returns the full list of freelancers."""

    def test_get_all_returns_200(self):
        """
        WHAT:  Send a GET request to the freelancer list endpoint.
        WHY:   This is the main roster page — it must always return 200.
        CHECK: response.status_code == 200
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}"
        )

    def test_get_all_returns_json_array(self):
        """
        WHAT:  Verify the response body is a JSON array (list).
        WHY:   The frontend expects an array of freelancer objects to render the table.
               If the API returns a single object or a string, the UI will break.
        CHECK: response.json() is a Python list.
        """
        r = requests.get(BASE_URL)
        body = r.json()
        assert isinstance(body, list), (
            f"[BUG] Expected a JSON array, got {type(body).__name__}: {body}"
        )

    def test_get_all_contains_only_active_freelancers(self, temp_freelancer):
        """
        WHAT:  Verify every object in the list has the required fields.
        WHY:   Each freelancer record must have at least "id" and "fullName"
               for the roster to be usable. Missing fields = broken UI.
        CHECK: Every object in the array contains "id" and "fullName".
        """
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
        """
        WHAT:  Verify every freelancer in the roster is linked to manager ID 1.
        WHY:   The app hardcodes manager ID 1 during creation. If the manager
               field is null or wrong, the "View Freelancer" page will fail to
               load for the admin.
        CHECK: Every freelancer has manager.id == 1.
        """
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
# TC-CRUD-03  Search by ID (get single freelancer)
# ===========================================================================

@pytest.mark.crud
class TestGetFreelancerById:
    """GET /api/freelancer/{id} — returns a single freelancer by their ID."""

    def test_get_by_id_returns_200(self, live_freelancer):
        """
        WHAT:  Use the ID of a known freelancer to fetch their record.
        WHY:   Fetching a valid ID must return 200.
        CHECK: response.status_code == 200
        """
        r = requests.get(f"{BASE_URL}/{live_freelancer['id']}")
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}. Body: {r.text}"
        )

    def test_get_by_id_returns_correct_freelancer(self, live_freelancer):
        """
        WHAT:  Fetch a freelancer by ID and verify the returned data matches.
        WHY:   The API must return the CORRECT freelancer, not a random one.
        CHECK: response.id matches the requested ID, and fullName matches.
        """
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
        """
        WHAT:  Fetch a freelancer and verify their nested user.email matches.
        WHY:   The email is inside the nested "user" object. If the relationship
               between Freelancer and User is broken, the email won't match.
        CHECK: response.user.email == the email we sent during creation.
        """
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
    """PUT /api/freelancer/{id} — update a freelancer's details."""

    def test_update_returns_200(self, live_freelancer):
        """
        WHAT:  Send a PUT request with a changed title field.
        WHY:   A valid update must return 200 (OK).
        CHECK: response.status_code == 200
        """
        fid = live_freelancer["id"]
        payload = {**live_freelancer["payload"], "title": "Senior QA Engineer"}
        r = requests.put(f"{BASE_URL}/{fid}", json=payload)
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}. Body: {r.text}"
        )

    def test_update_title_partial_update(self, live_freelancer):
        """
        WHAT:  Change ONLY the title field via PUT.
        WHY:   A partial update should modify only the title and leave all
               other fields (fullName, contactNumber, etc.) unchanged.
        CHECK: title == new value AND fullName == original value (unchanged).
        """
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
        """
        WHAT:  Change ONLY the contactNumber field via PUT.
        WHY:   Same as above — only the targeted field should change.
        CHECK: contactNumber == new value.
        """
        fid = live_freelancer["id"]
        update_payload = {**live_freelancer["payload"], "contactNumber": "0779999999"}
        r = requests.put(f"{BASE_URL}/{fid}", json=update_payload)
        assert r.status_code == 200, f"Update failed: {r.text}"
        body = r.json()
        assert body.get("contactNumber") == "0779999999", (
            f"[BUG] contactNumber not updated. Got: '{body.get('contactNumber')}'"
        )

    def test_update_returns_updated_freelancer_body(self, live_freelancer):
        """
        WHAT:  Verify the PUT response body contains the updated freelancer.
        WHY:   After an update, the API should return the full updated object
               so the frontend can refresh its state without a second GET call.
        CHECK: Response body contains "id" and "fullName" fields.
        """
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
    """DELETE /api/freelancer/{id} — remove a freelancer from the system."""

    def test_delete_returns_200(self):
        """
        WHAT:  Create a freelancer, then DELETE it by ID.
        WHY:   A successful deletion must return 200 (OK).
        CHECK: response.status_code == 200
        """
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
        """
        WHAT:  Delete a freelancer, then check if they still appear in GET /api/freelancer.
        WHY:   After deletion, the freelancer must be gone from the roster list.
               If they still show up, the delete didn't work properly.
        CHECK: Searching the roster by email returns None (not found).
        """
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=payload)
        assert r_create.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        fl_after = find_freelancer_by_email(payload["email"])
        assert fl_after is None, (
            f"[BUG] Freelancer (id={fid}) still appears in roster after DELETE."
        )

    def test_delete_makes_get_by_id_return_non_200(self):
        """
        WHAT:  Delete a freelancer, then try to GET them by ID.
        WHY:   Fetching a deleted freelancer should return a non-200 status
               (ideally 404) to indicate the resource no longer exists.
        CHECK: GET /api/freelancer/{deleted_id} status_code != 200
               (NOTE: this is a soft check — see test_02 for the strict 404 assertion)
        """
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
