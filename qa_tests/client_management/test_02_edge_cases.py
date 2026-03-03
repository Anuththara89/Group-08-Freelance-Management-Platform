"""
test_02_edge_cases.py
=====================
Logical edge cases and payload validation tests for Client Management API.

Covers:
  - Duplicate name prevention on create
  - ID not found for DELETE
  - Empty / null email and name on create
  - Re-registration loop (create → delete → re-create same email)
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_client_by_email, find_client_by_name


NON_EXISTENT_ID = 999999


# ===========================================================================
# TC-EDGE-01  Duplicate Name Prevention on Create
# ===========================================================================

@pytest.mark.edge
class TestDuplicateNameOnCreate:
    """
    The spec says: "Attempt to POST a new client with a fullName that
    already exists. Expected: IllegalArgumentException should be thrown."

    The actual implementation has NO duplicate checking at all —
    ClientService.saveClient() just delegates to repository.save() directly.
    """

    def test_duplicate_name_is_rejected(self, live_client):
        """
        WHAT:  Create a second client with the SAME name as an existing one.
        WHY:   The spec requires duplicate name prevention. Two clients with
               the same name creates confusion in the admin panel.
        CHECK: status_code != 200/201 (should reject the duplicate).
        """
        payload = {**live_client["payload"]}
        # Use a different email to avoid email collision
        payload["email"] = f"dup.{payload['email']}"

        r = requests.post(f"{BASE_URL}/add", json=payload)

        # Cleanup if it was accepted
        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")

        assert r.status_code not in (200, 201), (
            f"[BUG] Duplicate client name was ACCEPTED (status {r.status_code}). "
            f"The spec requires IllegalArgumentException for duplicate names, but "
            f"ClientService.saveClient() has NO duplicate checking — it directly "
            f"calls repository.save(). An existsByName() check must be added."
        )

    def test_duplicate_email_is_rejected(self, live_client):
        """
        WHAT:  Create a second client with the SAME email as an existing one.
        WHY:   Two clients sharing an email causes login/notification conflicts.
        CHECK: status_code != 200/201 (should reject the duplicate).
        """
        payload = {**live_client["payload"]}
        # Use a different name to avoid name collision
        payload["name"] = f"Different {payload['name']}"

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")

        assert r.status_code not in (200, 201), (
            f"[BUG] Duplicate client email was ACCEPTED (status {r.status_code}). "
            f"The DB schema does not have a UNIQUE constraint on client.email, "
            f"and the service has no duplicate-email check. Two clients can share "
            f"the same email address."
        )


# ===========================================================================
# TC-EDGE-02  ID Not Found
# ===========================================================================

@pytest.mark.edge
class TestIdNotFound:
    """
    Requests with non-existent IDs must return 404.
    The controller manually checks Optional for DELETE,
    but GET by ID and PUT don't exist at all.
    """

    def test_delete_nonexistent_id_returns_404(self):
        """
        WHAT:  DELETE /clients/delete/999999 (non-existent ID).
        WHY:   The controller checks getClientById() and returns 404 if empty.
               This is one of the few error cases that IS handled correctly.
        CHECK: status_code == 404
        """
        r = requests.delete(f"{BASE_URL}/delete/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] DELETE with non-existent ID returned {r.status_code} instead of 404."
        )

    def test_delete_nonexistent_returns_descriptive_message(self):
        """
        WHAT:  DELETE a non-existent client and check the error message.
        WHY:   The response should say "Client not found", not a blank error.
        CHECK: Response body contains "not found".
        """
        r = requests.delete(f"{BASE_URL}/delete/{NON_EXISTENT_ID}")
        body = r.text.lower()
        assert "not found" in body, (
            f"[BUG] Delete error response is not descriptive. Got: '{r.text}'"
        )

    def test_get_by_id_nonexistent_returns_404(self):
        """
        WHAT:  GET /clients/999999 (non-existent ID).
        WHY:   The spec requires GET by ID to return 404 for missing resources.
               But the endpoint itself doesn't exist.
        CHECK: status_code == 404
        NOTE:  This will fail because the GET-by-ID endpoint is not implemented.
               Spring returns 404 for the missing route, so it may accidentally pass.
        """
        r = requests.get(f"{BASE_URL}/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] GET /clients/{NON_EXISTENT_ID} returned {r.status_code}. "
            f"Expected 404."
        )


# ===========================================================================
# TC-EDGE-03  Empty / Null Fields on Create
# ===========================================================================

@pytest.mark.edge
class TestEmptyFieldsOnCreate:
    """
    The DB has NOT NULL on client.name. Email is nullable in the schema.
    The Client entity has no Bean Validation annotations.
    """

    def test_create_without_name_returns_4xx(self):
        """
        WHAT:  POST with email and phone but NO name field.
        WHY:   The DB has NOT NULL on client.name. Without validation,
               this should fail at the DB level (DataIntegrityViolation → 500).
               Ideally it should return 400.
        CHECK: status_code == 400
        """
        payload = {"email": "noname@test.com", "phone": "1234"}

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")
            pytest.fail(
                "[BUG] Client created without a name — NOT NULL constraint not enforced."
            )

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for missing name, got {r.status_code}. "
            f"No Bean Validation on the Client entity — the DB constraint "
            f"triggers a DataIntegrityViolationException which is not mapped to 400."
        )

    def test_create_with_null_name_returns_4xx(self):
        """
        WHAT:  POST with "name": null explicitly.
        WHY:   Null name should be rejected.
        CHECK: status_code == 400
        """
        payload = {"name": None, "email": "nullname@test.com", "phone": "1234"}

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")
            pytest.fail("[BUG] Client created with null name — should be rejected.")

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for null name, got {r.status_code}."
        )

    def test_create_with_empty_string_name_returns_4xx(self):
        """
        WHAT:  POST with "name": "" (empty string).
        WHY:   An empty string passes NOT NULL at DB level but is semantically
               invalid. There should be @NotBlank validation.
        CHECK: status_code == 400
        """
        payload = {"name": "", "email": "emptyname@test.com", "phone": "1234"}

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")
            pytest.fail(
                "[BUG] Client created with empty string name — should be rejected. "
                "No @NotBlank validation on the Client entity."
            )

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for empty name, got {r.status_code}."
        )

    def test_create_with_empty_email_is_rejected(self):
        """
        WHAT:  POST with "email": "" (empty string).
        WHY:   An empty email is useless for contact/login purposes.
        CHECK: status_code == 400
        """
        payload = {"name": "No Email Client", "email": "", "phone": "1234"}

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")
            pytest.fail(
                "[BUG] Client created with empty string email — should be rejected."
            )

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for empty email, got {r.status_code}."
        )

    def test_create_without_email_is_rejected(self):
        """
        WHAT:  POST with name and phone but NO email field at all.
        WHY:   Per the spec, email is required ("Body must include email and fullName").
        CHECK: status_code == 400
        """
        payload = {"name": "Missing Email", "phone": "1234"}

        r = requests.post(f"{BASE_URL}/add", json=payload)

        if r.status_code in (200, 201):
            body = r.json()
            if body.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body['id']}")
            pytest.fail(
                "[BUG] Client created without email field — spec says email is required."
            )

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for missing email, got {r.status_code}."
        )


# ===========================================================================
# TC-EDGE-04  Re-Registration Loop
# ===========================================================================

@pytest.mark.edge
class TestReRegistrationLoop:
    """
    Create → Delete → Re-create with the same email must succeed.
    This ensures DELETE actually cleans up all records.
    """

    def test_recreate_after_delete_with_same_email(self):
        """
        WHAT:  Create client A → Delete A → Create B with A's email.
        WHY:   After deletion, the email should be freed up. If the record
               still exists, re-registration will silently create a duplicate
               (since there's no UNIQUE constraint on client.email in the schema).
        CHECK: The second POST succeeds (status 200 or 201).
        """
        payload = make_payload()

        # Step 1: Create
        r1 = requests.post(f"{BASE_URL}/add", json=payload)
        assert r1.status_code == 200, f"Step 1 create failed: {r1.text}"
        cid = r1.json()["id"]

        # Step 2: Delete
        r2 = requests.delete(f"{BASE_URL}/delete/{cid}")
        assert r2.status_code == 200, f"Step 2 delete failed: {r2.text}"

        # Step 3: Re-create with same email, different name
        payload2 = {**payload, "name": f"Renewed {payload['name']}"}
        r3 = requests.post(f"{BASE_URL}/add", json=payload2)

        # Cleanup
        if r3.status_code in (200, 201):
            body3 = r3.json()
            if body3.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body3['id']}")

        assert r3.status_code == 200, (
            f"[BUG] Re-registration after delete FAILED with status {r3.status_code}. "
            f"The DELETE did not fully remove the client record. Body: {r3.text}"
        )

    def test_recreate_after_delete_with_same_name(self):
        """
        WHAT:  Create client A → Delete A → Create C with A's name.
        WHY:   After deletion, the name should be freed up.
        CHECK: The second POST succeeds.
        """
        payload = make_payload()

        # Create
        r1 = requests.post(f"{BASE_URL}/add", json=payload)
        assert r1.status_code == 200
        cid = r1.json()["id"]

        # Delete
        requests.delete(f"{BASE_URL}/delete/{cid}")

        # Re-create with same name, different email
        payload3 = {**payload, "email": f"renewed.{payload['email']}"}
        r3 = requests.post(f"{BASE_URL}/add", json=payload3)

        if r3.status_code in (200, 201):
            body3 = r3.json()
            if body3.get("id"):
                requests.delete(f"{BASE_URL}/delete/{body3['id']}")

        assert r3.status_code == 200, (
            f"[BUG] Re-registration with same name after delete FAILED ({r3.status_code}). "
            f"Body: {r3.text}"
        )
