"""
test_02_edge_cases.py
=====================
Logical edge cases and payload validation tests.

These tests intentionally send BAD or unusual data to the API to verify
it handles errors correctly (proper HTTP status codes, no crashes).

Covers:
  - Duplicate fullName prevention on create
  - Update conflict when renaming to an existing fullName
  - ID not found (GET, DELETE, PUT with non-existent ID)
  - Empty / null email on create
  - Invalid salary values (negative, zero, string)
  - Re-registration loop (create → delete → re-create)
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
        WHAT:  Try to create a NEW freelancer using the same fullName as an
               existing one (but a different email).
        WHY:   The system has a business rule: no two freelancers can share
               the same fullName. The service checks existsByFullName() and
               should throw IllegalArgumentException → HTTP 400.
        CHECK: status_code == 400 (not 201, not 500).
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
        """
        WHAT:  Send a duplicate fullName and inspect the error message body.
        WHY:   Even when the request is rejected, the API should return a
               human-readable error message (e.g., "Freelancer already exists"),
               not a blank 500 page.
        CHECK: Response body contains keywords like "already exists" or "duplicate".
        """
        payload = {**live_freelancer["payload"]}
        payload["email"] = f"dup2.{payload['email']}"

        r = requests.post(f"{BASE_URL}/create", json=payload)
        if r.status_code == 201:
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
        WHAT:  Create TWO freelancers (A and B). Then try to rename B's
               fullName to A's fullName via PUT.
        WHY:   The system must block this rename because A already owns that
               name. The service checks findByFullName() and compares IDs.
        CHECK: PUT returns 400 (not 200, not 500).
        CLEANUP: Freelancer B is deleted in the finally block.
        """
        # Create a second freelancer (B)
        second_payload = make_payload()
        r_create = requests.post(f"{BASE_URL}/create", json=second_payload)
        assert r_create.status_code == 201, "Pre-condition: second freelancer creation failed."
        second_fl = find_freelancer_by_email(second_payload["email"])
        assert second_fl is not None

        try:
            # Attempt to rename B → A's fullName (conflict)
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
    """
    Requests with a non-existent ID (999999) must return HTTP 404.
    Currently the API returns 500 for all of these because there is
    no @ControllerAdvice mapping exceptions to proper status codes.
    """

    def test_get_nonexistent_id_returns_404(self):
        """
        WHAT:  GET /api/freelancer/999999 (an ID that doesn't exist).
        WHY:   The service throws ResourceNotFoundException, which should
               map to 404. Without a @ControllerAdvice, Spring returns 500.
        CHECK: status_code == 404
        """
        r = requests.get(f"{BASE_URL}/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] GET with non-existent ID returned {r.status_code} instead of 404. "
            f"ResourceNotFoundException is not mapped to 404. "
            f"A @ControllerAdvice / @ResponseStatus annotation is missing."
        )

    def test_delete_nonexistent_id_returns_404(self):
        """
        WHAT:  DELETE /api/freelancer/999999 (an ID that doesn't exist).
        WHY:   Attempting to delete a missing resource should return 404.
               The service currently throws IllegalArgumentException (wrong type)
               AND it's unmapped (returns 500).
        CHECK: status_code == 404
        """
        r = requests.delete(f"{BASE_URL}/{NON_EXISTENT_ID}")
        assert r.status_code == 404, (
            f"[BUG] DELETE with non-existent ID returned {r.status_code} instead of 404. "
            f"The service throws IllegalArgumentException (not ResourceNotFoundException) "
            f"and there is no exception-to-status mapping in place."
        )

    def test_put_nonexistent_id_returns_404(self):
        """
        WHAT:  PUT /api/freelancer/999999 with a valid body (ID doesn't exist).
        WHY:   Updating a non-existent resource should return 404.
        CHECK: status_code == 404
        """
        payload = make_payload()
        r = requests.put(f"{BASE_URL}/{NON_EXISTENT_ID}", json=payload)
        assert r.status_code == 404, (
            f"[BUG] PUT with non-existent ID returned {r.status_code} instead of 404."
        )

    def test_error_body_on_not_found_is_descriptive(self):
        """
        WHAT:  GET a non-existent ID and inspect the error response body.
        WHY:   The error response should NOT contain raw Java stack traces
               (e.g., "at com.freelance.freelancepm.service..."). Exposing
               internals is a security risk and bad UX.
        CHECK: Response body does NOT contain "at com.freelance".
        """
        r = requests.get(f"{BASE_URL}/{NON_EXISTENT_ID}")
        body = r.text.lower()
        assert "at com.freelance" not in body, (
            "[BUG] Error response exposes internal Java stack trace. "
            "This is a security / UX issue."
        )


# ===========================================================================
# TC-EDGE-04  Empty Email on Create
# ===========================================================================

@pytest.mark.edge
class TestEmptyEmailOnCreate:
    """
    POST /api/freelancer/create without a valid email must be rejected.
    The users.email column is NOT NULL + UNIQUE in the database, but the
    app has no Bean Validation (@NotBlank, @Email) on the DTO.
    """

    def test_create_without_email_returns_4xx(self):
        """
        WHAT:  Send a POST request with the "email" field completely missing.
        WHY:   The DB has a NOT NULL constraint on users.email. Without the
               field, the insert will fail. The API should return 400, but
               because there's no @ControllerAdvice, it returns 500.
        CHECK: status_code == 400
        """
        payload = make_payload()
        del payload["email"]  # Remove email entirely

        r = requests.post(f"{BASE_URL}/create", json=payload)

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
        """
        WHAT:  Send a POST with "email": null explicitly in the JSON body.
        WHY:   Same NOT NULL constraint as above. Null should be rejected.
        CHECK: status_code == 400
        """
        payload = make_payload()
        payload["email"] = None

        r = requests.post(f"{BASE_URL}/create", json=payload)

        if r.status_code == 201:
            pytest.fail("[BUG] Freelancer created with null email — should be rejected.")

        assert r.status_code == 400, (
            f"[BUG] Expected 400 for null email, got {r.status_code}."
        )

    def test_create_with_empty_string_email_returns_4xx(self):
        """
        WHAT:  Send a POST with "email": "" (empty string).
        WHY:   An empty string passes the NOT NULL constraint at DB level,
               but it's semantically invalid — you can't send onboarding
               credentials to "". The app needs @NotBlank validation.
        CHECK: status_code == 400 (currently returns 201 — this is a bug).
        """
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
    """
    Salary is a BigDecimal field. These tests verify the API handles
    bad salary values (negative, zero, non-numeric string) correctly.
    """

    def test_create_with_negative_salary_is_rejected(self):
        """
        WHAT:  Send a POST with "salary": -1000.00.
        WHY:   A negative salary makes no business sense — no freelancer
               should owe money for working. The API should reject this
               with 400. Currently it accepts it (201) — this is a bug.
        CHECK: status_code == 400
        """
        payload = make_payload()
        payload["salary"] = -1000.00

        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")

        assert r.status_code == 400, (
            f"[BUG] Negative salary was accepted (status {r.status_code}). "
            f"The API has no validation to prevent negative salary values. "
            f"A @Positive or @Min(0) constraint is needed on the salary field."
        )

    def test_create_with_zero_salary_is_accepted(self):
        """
        WHAT:  Send a POST with "salary": 0.
        WHY:   Zero salary is considered valid (e.g., unpaid intern or volunteer).
               The API should accept it with 201.
        CHECK: status_code == 201
        """
        payload = make_payload()
        payload["salary"] = 0

        r = requests.post(f"{BASE_URL}/create", json=payload)
        fl = find_freelancer_by_email(payload["email"])
        if fl:
            requests.delete(f"{BASE_URL}/{fl['id']}")

        assert r.status_code == 201, (
            f"[BUG] Zero salary was rejected (status {r.status_code}). "
            f"Zero salary should be valid for unpaid interns or volunteers."
        )

    def test_create_with_string_salary_returns_4xx(self):
        """
        WHAT:  Send "salary": "not-a-number" (a string where BigDecimal is expected).
        WHY:   Spring/Jackson cannot deserialize "not-a-number" into BigDecimal.
               It should return 400 (Bad Request) automatically.
        CHECK: status_code == 400
        """
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
# TC-EDGE-06  Re-Registration Loop (Create → Delete → Re-Create)
# ===========================================================================

@pytest.mark.edge
class TestReRegistrationLoop:
    """
    After a freelancer is deleted, their email and fullName should be
    freed up so a new freelancer can be created with the same values.
    This validates that DELETE actually cleans up all records.
    """

    def test_recreate_after_delete_with_same_email(self):
        """
        WHAT:  Create freelancer A → Delete A → Create B with A's email.
        WHY:   The users.email column has a UNIQUE constraint. If DELETE
               doesn't remove the user row, the email is still "taken" and
               re-registration fails with a constraint violation.
               This would leave "ghost" login accounts in the DB.
        CHECK: The second POST returns 201 (re-registration succeeds).
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

        # Cleanup
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
        WHAT:  Create freelancer A → Delete A → Create C with A's fullName.
        WHY:   The service has a duplicate-name check (existsByFullName).
               If DELETE doesn't remove the freelancer row, the fullName is
               still "taken" and creation fails with "Freelancer already exists".
        CHECK: The second POST returns 201 (re-registration succeeds).
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
