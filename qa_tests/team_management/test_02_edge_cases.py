"""
test_02_edge_cases.py
=====================
Logical edge cases and payload validation tests.

Covers:
  - Duplicate fullName prevention on create
  - Update conflict when renaming to an existing fullName
  - ID not found (GET, DELETE with non-existent ID)
  - Empty / null email on create
  - Invalid salary values
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_freelancer_by_email


NON_EXISTENT_ID = 999999


# ===========================================================================
# TC-EDGE-01  Duplicate Name Prevention on Create
# ===========================================================================

@pytest.mark.edge
class TestDuplicateNameOnCreate:
    """POST /api/freelancer/create with an already-used fullName must be rejected."""

    def test_duplicate_fullName_returns_4xx(self, live_freelancer):
        """
        Expected: 400 Bad Request (IllegalArgumentException).
        Spring Boot default maps unhandled exceptions to 500 — this test
        verifies any non-2xx response, flagging 500 as a missing error handler.
        """
        payload = {**live_freelancer["payload"]}
        # Use a different email so the uniqueness constraint on email doesn't fire first
        payload["email"] = f"dup.trigger.{payload['email']}"

        r = requests.post(f"{BASE_URL}/create", json=payload)

        assert r.status_code != 201, (
            "[BUG] Duplicate fullName was accepted — duplicate prevention is BROKEN."
        )
        assert r.status_code == 400, (
            f"[BUG] Expected HTTP 400 for duplicate fullName, "
            f"got {r.status_code}. "
            f"The IllegalArgumentException is not mapped to 400; "
            f"a @ControllerAdvice / @ExceptionHandler is missing."
        )

    def test_duplicate_fullName_response_contains_error_message(self, live_freelancer):
        """Error response for duplicate name must contain a meaningful message."""
        payload = {**live_freelancer["payload"]}
        payload["email"] = f"dup2.{payload['email']}"

        r = requests.post(f"{BASE_URL}/create", json=payload)
        if r.status_code == 201:
            # Cleanup if somehow created
            fl = find_freelancer_by_email(payload["email"])
            if fl:
                requests.delete(f"{BASE_URL}/{fl['id']}")
            pytest.fail("[BUG] Duplicate fullName was accepted — should have been rejected.")

        body = r.text.lower()
        assert any(kw in body for kw in ("already exists", "duplicate", "freelancer")), (
            f"[BUG] Error response for duplicate does not contain a descriptive message. "
            f"Got: {r.text}"
        )


# ===========================================================================
# TC-EDGE-02  Update Conflict — rename to an existing fullName
# ===========================================================================

@pytest.mark.edge
class TestUpdateNameConflict:
    """PUT /api/freelancer/{id} renaming to an existing fullName must be blocked."""

    def test_update_to_existing_fullName_returns_4xx(self, live_freelancer):
        """
        Create a second freelancer, then try to rename it to the first one's name.
        Expected: 400.  Actual likely: 500 (missing error handler).
        """
        # Create a second freelancer
        second_payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=second_payload)
        assert r_create.status_code == 201, "Pre-condition: second freelancer creation failed."
        second_fl = find_freelancer_by_email(second_payload["email"])
        assert second_fl is not None

        try:
            # Attempt to rename second → first's fullName (conflict)
            conflict_payload = {**second_payload, "fullName": live_freelancer["payload"]["fullName"]}
            r = requests.put(f"{BASE_URL}/{second_fl['id']}", json=conflict_payload)

            assert r.status_code != 200, (
                "[BUG] Renaming to an existing fullName was ACCEPTED — conflict check is BROKEN."
            )
            assert r.status_code == 400, (
                f"[BUG] Expected 400 for update name conflict, got {r.status_code}. "
                f"IllegalArgumentException not mapped to 400."
            )
        finally:
            requests.delete(f"{BASE_URL}/{second_fl['id']}")


# ===========================================================================
# TC-EDGE-03  ID Not Found
# ===========================================================================

@pytest.mark.edge
class TestIdNotFound:
    """Requests with non-existent IDs must return 404, not 500."""

    def test_get_nonexistent_id_returns_404(self):
        """
        GET /api/freelancer/{non-existent-id} should return 404.
        Expected: 404 (ResourceNotFoundException).
        Actual likely: 500 (no @ResponseStatus or @ExceptionHandler).
        """
        r = requests.get(f"{BASE_URL}/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] GET with non-existent ID returned {r.status_code} instead of 404. "
            f"ResourceNotFoundException is not mapped to 404. "
            f"A @ControllerAdvice / @ResponseStatus annotation is missing."
        )

    def test_delete_nonexistent_id_returns_404(self):
        """
        DELETE /api/freelancer/{non-existent-id} should return 404.
        Expected: 404.
        Actual likely: 500 (IllegalArgumentException thrown in deleteFreelancer,
        not mapped to any HTTP status).
        """
        r = requests.delete(f"{BASE_URL}/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] DELETE with non-existent ID returned {r.status_code} instead of 404. "
            f"The service throws IllegalArgumentException (not ResourceNotFoundException) "
            f"and there is no exception-to-status mapping in place."
        )

    def test_put_nonexistent_id_returns_404(self):
        """
        PUT /api/freelancer/{non-existent-id} should return 404.
        """
        payload = make_payload()
        r = requests.put(f"{BASE_URL}/{NON_EXISTENT_ID}", json=payload)
        assert r.status_code == 404, (
            f"[BUG] PUT with non-existent ID returned {r.status_code} instead of 404."
        )

    def test_error_body_on_not_found_is_descriptive(self):
        """Error response for not-found should contain a useful message, not a raw stack trace."""
        r = requests.get(f"{BASE_URL}/{NON_EXISTENT_ID}")
        body = r.text.lower()
        # Should NOT expose internal stack traces
        assert "at com.freelance" not in body, (
            "[BUG] Error response exposes internal Java stack trace. "
            "This is a security / UX issue."
        )


# ===========================================================================
# TC-EDGE-04  Empty Email on Create
# ===========================================================================

@pytest.mark.edge
class TestEmptyEmailOnCreate:
    """POST /api/freelancer/create without an email must be rejected."""

    def test_create_without_email_returns_4xx(self):
        """
        Expected: 400 (DataIntegrityViolationException from NOT NULL constraint).
        Actual likely: 500.
        """
        payload = make_payload()
        del payload["email"]  # Remove email entirely

        r = requests.post(f"{BASE_URL}/create", json=payload)

        # If it somehow succeeded, clean up
        if r.status_code == 201:
            body = r.json()
            fl = find_freelancer_by_email(body.get("email", ""))
            if fl:
                requests.delete(f"{BASE_URL}/{fl['id']}")
            pytest.fail(
                "[BUG] Freelancer created without an email — NOT NULL constraint is not enforced "
                "at the application layer."
            )

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for missing email, got {r.status_code}. "
            f"DataIntegrityViolationException / validation is not mapped to 400."
        )

    def test_create_with_null_email_returns_4xx(self):
        """Explicitly passing null email must also be rejected."""
        payload = make_payload()
        payload["email"] = None

        r = requests.post(f"{BASE_URL}/create", json=payload)

        if r.status_code == 201:
            pytest.fail("[BUG] Freelancer created with null email — should be rejected.")

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for null email, got {r.status_code}."
        )

    def test_create_with_empty_string_email_returns_4xx(self):
        """Empty string email must be rejected."""
        payload = make_payload()
        payload["email"] = ""

        r = requests.post(f"{BASE_URL}/create", json=payload)

        if r.status_code == 201:
            fl = find_freelancer_by_email("")
            if fl:
                requests.delete(f"{BASE_URL}/{fl['id']}")
            pytest.fail("[BUG] Freelancer created with empty string email — should be rejected.")

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for empty email, got {r.status_code}."
        )


# ===========================================================================
# TC-EDGE-05  Invalid Salary Values
# ===========================================================================

@pytest.mark.edge
class TestInvalidSalary:
    """Salary field must handle invalid inputs gracefully."""

    def test_create_with_negative_salary_is_rejected_or_succeeds_gracefully(self):
        """
        A negative salary is questionable business logic.
        At minimum, it must not cause an unhandled 500 error.
        Expected: either 400 (validation) or 201 if negative salaries are allowed by design.
        """
        payload = make_payload()
        payload["salary"] = -1000.00

        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")

        assert r.status_code in (201, 400), (
            f"[BUG] Negative salary caused unexpected server error {r.status_code}. "
            f"The API should either accept or explicitly reject it with 400."
        )

    def test_create_with_string_salary_returns_4xx(self):
        """
        Sending a non-numeric string as salary must be rejected cleanly.
        Spring's BigDecimal deserialization should return 400.
        """
        # Send raw JSON with a string where a number is expected
        import json
        payload_str = json.dumps({
            "email": f"badsalary.{make_payload()['email']}",
            "fullName": f"BadSalary {make_payload()['fullName']}",
            "salary": "not-a-number",
        })
        r = requests.post(
            f"{BASE_URL}/create",
            data=payload_str,
            headers={"Content-Type": "application/json"},
        )
        assert r.status_code == 400, (
            f"[BUG] String salary caused {r.status_code} instead of 400. "
            f"Jackson deserialization error is not handled as a 400 Bad Request."
        )


# ===========================================================================
# TC-EDGE-06  Re-Registration Loop
# ===========================================================================

@pytest.mark.edge
class TestReRegistrationLoop:
    """Create → Delete → Re-create with same email must succeed."""

    def test_recreate_after_delete_with_same_email(self):
        """
        After deleting a freelancer, creating a new one with the same email
        must succeed (email unique constraint in users table must be cleared).
        """
        payload = make_payload()

        # Step 1: Create
        r1 = requests.post(f"{BASE_URL}/create", json=payload)
        assert r1.status_code == 201, f"Step 1 create failed: {r1.text}"
        fl = find_freelancer_by_email(payload["email"])
        assert fl is not None, "Step 1: freelancer not found after create."
        fid = fl["id"]

        # Step 2: Delete
        r2 = requests.delete(f"{BASE_URL}/{fid}")
        assert r2.status_code == 200, f"Step 2 delete failed: {r2.text}"

        # Step 3: Re-create with same email, different fullName
        payload2 = {**payload, "fullName": f"Renewed {payload['fullName']}"}
        r3 = requests.post(f"{BASE_URL}/create", json=payload2)

        # Cleanup if it succeeded
        fl2 = find_freelancer_by_email(payload2["email"])
        if fl2:
            requests.delete(f"{BASE_URL}/{fl2['id']}")

        assert r3.status_code == 201, (
            f"[BUG] Re-registration after delete FAILED with status {r3.status_code}. "
            f"The DELETE endpoint did not fully remove the User record, so the email "
            f"unique constraint in the users table is blocking re-registration. "
            f"Body: {r3.text}"
        )

    def test_recreate_after_delete_with_same_fullname(self):
        """
        After deleting, creating with the same fullName must also succeed.
        (The fullName duplicate check in the service must be cleared after delete.)
        """
        payload = make_payload()

        # Create
        r1 = requests.post(f"{BASE_URL}/create", json=payload)
        assert r1.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        # Delete
        requests.delete(f"{BASE_URL}/{fid}")

        # Re-create with same fullName but different email
        payload3 = {**payload, "email": f"renewed.{payload['email']}"}
        r3 = requests.post(f"{BASE_URL}/create", json=payload3)

        fl3 = find_freelancer_by_email(payload3["email"])
        if fl3:
            requests.delete(f"{BASE_URL}/{fl3['id']}")

        assert r3.status_code == 201, (
            f"[BUG] Re-registration with same fullName after delete FAILED with {r3.status_code}. "
            f"The freelancer record may not have been fully deleted. Body: {r3.text}"
        )
