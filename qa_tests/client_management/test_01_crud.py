"""
test_01_crud.py
===============
Core CRUD lifecycle tests for the Client Management API.

Actual endpoints tested:
  1. CREATE  - POST   /clients/add
  2. READ    - GET    /clients/all
  3. READ    - GET    /clients/{id}          ← NOT IMPLEMENTED
  4. UPDATE  - PUT    /clients/{id}          ← NOT IMPLEMENTED
  5. DELETE  - DELETE /clients/delete/{id}
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_client_by_email


# ===========================================================================
# TC-CRUD-01  Create Client
# ===========================================================================

@pytest.mark.crud
class TestCreateClient:
    """POST /clients/add"""

    def test_create_returns_success(self):
        """
        WHAT:  Send a valid POST to /clients/add with name, email, phone.
        WHY:   Creating a client must succeed. The spec expects HTTP 201 (Created),
               but the actual implementation returns 200.
        CHECK: status_code == 201 (per spec).
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        assert r.status_code == 201, (
            f"[BUG] Expected 201 Created, got {r.status_code}. "
            f"The controller returns HttpStatus.OK (200) instead of HttpStatus.CREATED (201)."
        )

    def test_create_response_contains_id(self):
        """
        WHAT:  Verify the create response includes an auto-generated ID.
        WHY:   The frontend needs the ID to navigate to the client's detail page.
        CHECK: "id" key exists in the response and is an integer.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        assert "id" in body, (
            f"[BUG] 'id' missing from create response. Got: {body}"
        )
        assert isinstance(body["id"], int), (
            f"[BUG] 'id' should be an integer, got {type(body['id']).__name__}"
        )

    def test_create_response_contains_name(self):
        """
        WHAT:  Verify the create response echoes back the client name.
        WHY:   Confirms the correct record was created.
        CHECK: response.name == the name we sent.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        assert body.get("name") == payload["name"], (
            f"[BUG] Name mismatch: got '{body.get('name')}', expected '{payload['name']}'"
        )

    def test_create_response_contains_email(self):
        """
        WHAT:  Verify the create response echoes back the email.
        WHY:   Confirms the correct email was stored.
        CHECK: response.email == the email we sent.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        assert body.get("email") == payload["email"], (
            f"[BUG] Email mismatch: got '{body.get('email')}', expected '{payload['email']}'"
        )

    def test_create_response_contains_phone(self):
        """
        WHAT:  Verify the create response includes the phone/contact number.
        WHY:   The spec calls this field "contactNumber" but the entity uses "phone".
        CHECK: response.phone == the phone we sent.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        assert body.get("phone") == payload["phone"], (
            f"[BUG] Phone mismatch: got '{body.get('phone')}', expected '{payload['phone']}'"
        )

    def test_create_response_contains_company_name(self):
        """
        WHAT:  Verify the create response includes the companyName field.
        WHY:   The spec requires a companyName field on the client. The DB schema
               has a company_name column, but the Client entity does not map it.
        CHECK: "companyName" or "company_name" key exists in response.
        """
        payload = {**make_payload(), "companyName": "Test Corp"}
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        has_company = "companyName" in body or "company_name" in body
        assert has_company, (
            f"[BUG] 'companyName' field is missing from the Client entity and API response. "
            f"The DB schema has a company_name column but the Java entity does not map it. "
            f"Got keys: {list(body.keys())}"
        )

    def test_create_response_contains_temporary_password(self):
        """
        WHAT:  Verify the create response includes a temporary password.
        WHY:   Per spec, creating a client should generate a temporary password
               for onboarding (like the Freelancer API does). The current
               implementation does NOT generate any password.
        CHECK: "temporaryPassword" or "password" key exists in response.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        body = r.json()
        cl = find_client_by_email(payload["email"])
        if cl:
            requests.delete(f"{BASE_URL}/delete/{cl['id']}")
        has_pwd = "temporaryPassword" in body or "password" in body
        assert has_pwd, (
            f"[BUG] No temporary password in create response. "
            f"The spec requires a temporaryPassword for client onboarding, "
            f"but the ClientService does not generate one (unlike FreelancerService). "
            f"Got keys: {list(body.keys())}"
        )


# ===========================================================================
# TC-CRUD-02  View All Clients
# ===========================================================================

@pytest.mark.crud
class TestViewAllClients:
    """GET /clients/all"""

    def test_get_all_returns_200(self):
        """
        WHAT:  Send a GET request to the client list endpoint.
        WHY:   The roster endpoint must always return 200.
        CHECK: status_code == 200
        """
        r = requests.get(f"{BASE_URL}/all")
        assert r.status_code == 200, (
            f"[BUG] Expected 200, got {r.status_code}"
        )

    def test_get_all_returns_json_array(self):
        """
        WHAT:  Verify the response body is a JSON array.
        WHY:   The frontend expects an array of client objects for the table.
        CHECK: response.json() is a Python list.
        """
        r = requests.get(f"{BASE_URL}/all")
        body = r.json()
        assert isinstance(body, list), (
            f"[BUG] Expected a JSON array, got {type(body).__name__}: {body}"
        )

    def test_get_all_clients_have_required_fields(self, temp_client):
        """
        WHAT:  Verify every object in the list has the minimum required fields.
        WHY:   Each client record needs at least id, name, and email for the UI.
        CHECK: Every object has "id", "name", "email".
        """
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        assert len(clients) > 0, "Client list should not be empty."
        required_fields = {"id", "name", "email"}
        for cl in clients:
            missing = required_fields - cl.keys()
            assert not missing, (
                f"[BUG] Client record is missing fields {missing}. Record: {cl}"
            )


# ===========================================================================
# TC-CRUD-03  Search by ID
# ===========================================================================

@pytest.mark.crud
class TestGetClientById:
    """
    GET /clients/{id} — this endpoint is NOT IMPLEMENTED.
    The spec requires it but the controller only has /clients/all.
    """

    def test_get_by_id_endpoint_exists(self, live_client):
        """
        WHAT:  Try to GET a single client by ID using GET /clients/{id}.
        WHY:   The spec requires a "Search by ID" endpoint. Without it,
               the frontend cannot load a single client's detail page.
        CHECK: status_code == 200 (will FAIL — endpoint doesn't exist).
        """
        cid = live_client["id"]
        r = requests.get(f"{BASE_URL}/{cid}")
        assert r.status_code == 200, (
            f"[BUG] GET /clients/{cid} returned {r.status_code}. "
            f"The 'Search by ID' endpoint (GET /clients/{{id}}) is NOT IMPLEMENTED. "
            f"The ClientController only has /clients/add, /clients/all, and "
            f"/clients/delete/{{id}}. A @GetMapping(\"/{{id}}\") handler is missing."
        )


# ===========================================================================
# TC-CRUD-04  Update Client Info
# ===========================================================================

@pytest.mark.crud
class TestUpdateClient:
    """
    PUT /clients/{id} — this endpoint is NOT IMPLEMENTED.
    The spec requires partial update support (e.g., change companyName or contactNumber).
    """

    def test_update_endpoint_exists(self, live_client):
        """
        WHAT:  Try to PUT an update to an existing client.
        WHY:   The spec requires a "Update Client Info" endpoint for partial
               updates. Without it, the admin cannot edit any client details.
        CHECK: status_code == 200 (will FAIL — endpoint doesn't exist).
        """
        cid = live_client["id"]
        payload = {**live_client["payload"], "name": "Updated Client Name"}
        r = requests.put(f"{BASE_URL}/{cid}", json=payload)
        assert r.status_code == 200, (
            f"[BUG] PUT /clients/{cid} returned {r.status_code}. "
            f"The 'Update Client' endpoint (PUT /clients/{{id}}) is NOT IMPLEMENTED. "
            f"The ClientController has no @PutMapping handler."
        )


# ===========================================================================
# TC-CRUD-05  Delete Client
# ===========================================================================

@pytest.mark.crud
class TestDeleteClient:
    """DELETE /clients/delete/{id}"""

    def test_delete_returns_200(self):
        """
        WHAT:  Create a client, then DELETE it by ID.
        WHY:   A successful deletion must return 200.
        CHECK: status_code == 200
        """
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/add", json=payload)
        body = r_create.json()
        cid = body["id"]

        r_delete = requests.delete(f"{BASE_URL}/delete/{cid}")
        assert r_delete.status_code == 200, (
            f"[BUG] Expected 200 on delete, got {r_delete.status_code}. Body: {r_delete.text}"
        )

    def test_delete_removes_client_from_list(self):
        """
        WHAT:  Delete a client, then check if they still appear in GET /clients/all.
        WHY:   After deletion, the client must be gone from the list.
        CHECK: The deleted client's email is NOT found in the list.
        """
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/add", json=payload)
        cid = r_create.json()["id"]

        requests.delete(f"{BASE_URL}/delete/{cid}")

        cl_after = find_client_by_email(payload["email"])
        assert cl_after is None, (
            f"[BUG] Client (id={cid}) still appears in the list after DELETE."
        )

    def test_delete_response_body_contains_success_message(self):
        """
        WHAT:  Check the DELETE response body text.
        WHY:   The controller returns "Client deleted successfully" on success.
        CHECK: Response body contains "deleted" or "success".
        """
        payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/add", json=payload)
        cid = r_create.json()["id"]

        r_delete = requests.delete(f"{BASE_URL}/delete/{cid}")
        body = r_delete.text.lower()
        assert "deleted" in body or "success" in body, (
            f"[BUG] Delete response body does not confirm success. Got: '{r_delete.text}'"
        )

    def test_delete_nonexistent_id_returns_404(self):
        """
        WHAT:  Try to DELETE a client with a non-existent ID (999999).
        WHY:   The controller checks if the client exists and returns 404 if not.
        CHECK: status_code == 404
        """
        r = requests.delete(f"{BASE_URL}/delete/999999")
        assert r.status_code == 404, (
            f"[BUG] DELETE with non-existent ID returned {r.status_code} instead of 404."
        )
