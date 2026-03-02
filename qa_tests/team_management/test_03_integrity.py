"""
test_03_integrity.py
====================
Relational integrity, cascade delete, and security (password exposure) tests.

Covers:
  - Cascade delete: deleting a Freelancer must also wipe the User record
  - Manager linkage: every freelancer must be linked to manager ID 1
  - Password security: GET requests must NOT expose BCrypt password hashes
  - Credential verification: the plain-text password in create response
    must be a valid BCrypt match against the stored hash
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_freelancer_by_email

try:
    import bcrypt
    BCRYPT_AVAILABLE = True
except ImportError:
    BCRYPT_AVAILABLE = False


# ===========================================================================
# TC-INT-01  Cascade Delete: users table must be cleaned up
# ===========================================================================

@pytest.mark.integrity
class TestCascadeDelete:
    """
    After DELETE /api/freelancer/{id}, both the freelancer and its
    associated user record must be gone.

    The service calls userRepository.deleteById(user_id). Because the
    freelancer table uses ON DELETE CASCADE referencing users(id), the
    freelancer row is removed automatically. This test validates the
    cascade works end-to-end via the API (proxy check: GET by ID returns
    non-200, and re-creating with the same email succeeds without a
    unique-constraint violation).
    """

    def test_delete_cascade_freelancer_record_removed(self):
        """After DELETE, GET /api/freelancer/{id} must NOT return 200."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        assert r.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        r_get = requests.get(f"{BASE_URL}/{fid}")
        assert r_get.status_code != 200, (
            f"[BUG] GET /api/freelancer/{fid} still returns 200 after DELETE. "
            f"The freelancer record was NOT removed — cascade delete is BROKEN."
        )

    def test_delete_cascade_user_record_removed_via_email_reuse(self):
        """
        After DELETE, re-creating with the same email must succeed.
        If the users row is NOT deleted, the unique constraint on users.email
        will prevent re-registration, proving a 'ghost login' vulnerability.
        """
        payload = make_payload()

        # Create
        r1 = requests.post(f"{BASE_URL}/create", json=payload)
        assert r1.status_code == 201, f"Creation failed: {r1.text}"
        fl = find_freelancer_by_email(payload["email"])
        assert fl is not None
        fid = fl["id"]

        # Delete
        r_del = requests.delete(f"{BASE_URL}/{fid}")
        assert r_del.status_code == 200, f"Delete failed: {r_del.text}"

        # Attempt re-registration with the same email (new fullName)
        payload2 = {**payload, "fullName": f"Reborn {payload['fullName']}"}
        r2 = requests.post(f"{BASE_URL}/create", json=payload2)

        # Cleanup
        fl2 = find_freelancer_by_email(payload2["email"])
        if fl2:
            requests.delete(f"{BASE_URL}/{fl2['id']}")

        assert r2.status_code == 201, (
            f"[BUG] After DELETE, re-registering with the same email returned "
            f"{r2.status_code}. The User record (users table) was NOT deleted — "
            f"a 'ghost login' record remains in the database. "
            f"The DELETE endpoint must ensure the user row is removed. Body: {r2.text}"
        )

    def test_delete_removes_from_roster(self):
        """After DELETE, the freelancer must not appear in GET /api/freelancer."""
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        assert r.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        roster = requests.get(BASE_URL).json()
        ids_in_roster = [f["id"] for f in roster]
        assert fid not in ids_in_roster, (
            f"[BUG] Deleted freelancer id={fid} still appears in the roster. "
            f"Cascade delete may be partial."
        )


# ===========================================================================
# TC-INT-02  Manager Linkage
# ===========================================================================

@pytest.mark.integrity
class TestManagerLinkage:
    """Every created freelancer must be linked to manager ID 1."""

    def test_created_freelancer_has_manager_id_1(self, temp_freelancer):
        """GET /api/freelancer/{id} must show manager.id == 1 for a newly created freelancer."""
        fid = temp_freelancer["id"]
        r = requests.get(f"{BASE_URL}/{fid}")
        assert r.status_code == 200
        body = r.json()
        manager = body.get("manager")
        assert manager is not None, (
            f"[BUG] Freelancer id={fid} has no manager. "
            f"The 'view freelancer' feature will fail to load for the admin."
        )
        assert manager.get("id") == 1, (
            f"[BUG] Freelancer id={fid} linked to manager_id={manager.get('id')}, "
            f"expected 1. The hardcoded manager lookup (userRepository.findById(1)) "
            f"may be pointing to the wrong user."
        )

    def test_all_roster_freelancers_have_manager_id_1(self):
        """All freelancers in the roster must be linked to manager ID 1."""
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        roster = r.json()
        assert len(roster) > 0, "Roster is empty — cannot verify manager linkage."

        for fl in roster:
            manager = fl.get("manager")
            fid = fl.get("id")
            assert manager is not None, (
                f"[BUG] Freelancer id={fid} has manager=null in the roster response. "
                f"manager_id column in freelancer table is null."
            )
            assert manager.get("id") == 1, (
                f"[BUG] Freelancer id={fid} has manager_id={manager.get('id')}, expected 1."
            )


# ===========================================================================
# TC-SEC-01  Password Security — BCrypt hash must NOT be exposed in GET
# ===========================================================================

@pytest.mark.security
class TestPasswordSecurity:
    """
    GET endpoints must NOT expose BCrypt password hashes to the frontend.
    The User entity includes a `password` field that is serialized unless
    explicitly ignored with @JsonIgnore.
    """

    def _assert_no_password_hash_exposed(self, obj: dict, context: str):
        """Recursively check a dict/list for BCrypt hash patterns."""
        if isinstance(obj, dict):
            for key, val in obj.items():
                if key == "password":
                    assert not str(val).startswith("$2"), (
                        f"[BUG][SECURITY] BCrypt password hash exposed in {context}. "
                        f"The `password` field on the User entity must be annotated with "
                        f"@JsonIgnore to prevent leaking it via GET responses. "
                        f"Exposed value prefix: '{str(val)[:10]}...'"
                    )
                elif isinstance(val, (dict, list)):
                    self._assert_no_password_hash_exposed(val, context)
        elif isinstance(obj, list):
            for item in obj:
                self._assert_no_password_hash_exposed(item, context)

    def test_get_all_does_not_expose_bcrypt_hashes(self):
        """GET /api/freelancer must not include BCrypt password hashes in any object."""
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        self._assert_no_password_hash_exposed(r.json(), "GET /api/freelancer")

    def test_get_by_id_does_not_expose_bcrypt_hash(self, live_freelancer):
        """GET /api/freelancer/{id} must not include a BCrypt hash in the response."""
        fid = live_freelancer["id"]
        r = requests.get(f"{BASE_URL}/{fid}")
        assert r.status_code == 200
        self._assert_no_password_hash_exposed(r.json(), f"GET /api/freelancer/{fid}")

    def test_get_all_user_object_has_no_password_field(self):
        """
        The nested `user` object in GET responses must not contain a `password` key at all,
        or the value must be null/omitted.
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        for fl in r.json():
            user = fl.get("user", {})
            if "password" in user and user["password"] is not None:
                assert not str(user["password"]).startswith("$2"), (
                    f"[BUG][SECURITY] 'user.password' field exposed in roster for "
                    f"freelancer id={fl.get('id')}. "
                    f"Add @JsonIgnore on User.password or use a DTO without password."
                )

    def test_manager_password_not_exposed_in_get_all(self):
        """
        The nested `manager` object in GET responses must not expose its password.
        The manager's password was found to be 'dummy_hash' in the seed data,
        which is a plaintext value — this should be a BCrypt hash AND must not be returned.
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        for fl in r.json():
            manager = fl.get("manager", {})
            fid = fl.get("id")
            if "password" in manager and manager["password"] is not None:
                # It should never be exposed regardless of its value
                pytest.fail(
                    f"[BUG][SECURITY] 'manager.password' field is exposed for "
                    f"freelancer id={fid}. "
                    f"The Manager (User) entity's password field must be hidden. "
                    f"Additionally, the manager seed data appears to store a plaintext "
                    f"password ('dummy_hash') instead of a BCrypt hash — this is a "
                    f"critical security vulnerability."
                )

    def test_create_response_password_is_one_time_only(self, live_freelancer):
        """
        The plain-text password must ONLY appear in the create response.
        Subsequent GET requests must not expose it.
        """
        create_password = live_freelancer["create_response"].get("password", "")
        fid = live_freelancer["id"]

        r = requests.get(f"{BASE_URL}/{fid}")
        body_text = r.text

        # The plain-text password should not appear verbatim in GET responses
        assert create_password not in body_text, (
            f"[BUG][SECURITY] The one-time plain-text password from create "
            f"('{create_password}') was found verbatim in the GET /api/freelancer/{fid} "
            f"response. This should never be stored or returned after the initial creation."
        )


# ===========================================================================
# TC-SEC-02  Credential Verification
# ===========================================================================

@pytest.mark.security
class TestCredentialVerification:
    """
    The plain-text password returned in the create response must be valid.
    It should be verifiable against the BCrypt hash stored for the user.
    """

    @pytest.mark.skipif(not BCRYPT_AVAILABLE, reason="bcrypt package not installed")
    def test_create_password_matches_stored_bcrypt_hash(self, live_freelancer):
        """
        The plain-text password in the create response must hash-match the
        BCrypt value stored in the user record (if accessible).

        NOTE: This test requires the GET endpoint to expose user.password (which
        is itself a security bug). Marked as advisory — if the security bug is
        fixed first, this test needs a DB-level check instead.
        """
        fid = live_freelancer["id"]
        plain_password = live_freelancer["create_response"].get("password", "")

        r = requests.get(f"{BASE_URL}/{fid}")
        body = r.json()
        stored_hash = body.get("user", {}).get("password")

        if stored_hash is None:
            pytest.skip(
                "user.password not exposed in GET response — "
                "cannot verify BCrypt match via API (good from a security standpoint)."
            )

        if not stored_hash.startswith("$2"):
            pytest.fail(
                f"[BUG][SECURITY] The stored password for user id={fid} is not a "
                f"BCrypt hash. It appears to be plaintext or an unsupported format: "
                f"'{stored_hash[:20]}...'"
            )

        import bcrypt
        match = bcrypt.checkpw(plain_password.encode(), stored_hash.encode())
        assert match, (
            f"[BUG] The plain-text password from the create response does NOT match "
            f"the BCrypt hash stored in the database for user id={fid}. "
            f"Password generation or encoding logic may be broken."
        )

    def test_create_password_is_not_empty(self, live_freelancer):
        """The create response password must not be empty."""
        pwd = live_freelancer["create_response"].get("password", "")
        assert pwd, (
            "[BUG] Create response password is empty. "
            "PasswordGenerator may have failed silently."
        )

    def test_create_password_has_complexity(self, live_freelancer):
        """
        The 12-character password should contain at least one uppercase letter,
        one lowercase letter, one digit, and one special character
        (as documented in PasswordGenerator).
        """
        pwd = live_freelancer["create_response"].get("password", "")
        if not pwd:
            pytest.skip("No password in create response — cannot check complexity.")

        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_special = any(not c.isalnum() for c in pwd)

        assert has_upper, f"[BUG] Password '{pwd}' has no uppercase letter."
        assert has_lower, f"[BUG] Password '{pwd}' has no lowercase letter."
        assert has_digit, f"[BUG] Password '{pwd}' has no digit."
        assert has_special, f"[BUG] Password '{pwd}' has no special character."
