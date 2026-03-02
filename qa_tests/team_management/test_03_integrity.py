"""
test_03_integrity.py
====================
Relational integrity, cascade delete, and security (password exposure) tests.

These tests go deeper than basic CRUD — they verify:
  - CASCADE DELETE: deleting a freelancer must also wipe the associated User row
  - MANAGER LINKAGE: every freelancer must be linked to manager ID 1
  - PASSWORD SECURITY: GET responses must NOT expose BCrypt hashes
  - CREDENTIAL VERIFICATION: the generated password must actually work
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
    The database schema has: freelancer.user_id REFERENCES users(id) ON DELETE CASCADE.
    The service calls userRepository.deleteById(user_id), which deletes the User row.
    The CASCADE should automatically remove the Freelancer row too.

    If this is broken, we'll have "ghost" logins in the users table —
    accounts that can still authenticate but have no corresponding freelancer profile.
    """

    def test_delete_cascade_freelancer_record_removed(self):
        """
        WHAT:  Create a freelancer, DELETE it, then try to GET it by ID.
        WHY:   After deletion, fetching the same ID must return 404 (not 200).
               If it still returns 200, the freelancer record was NOT deleted.
        CHECK: GET /api/freelancer/{deleted_id} returns 404.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/create", json=payload)
        assert r.status_code == 201
        fl = find_freelancer_by_email(payload["email"])
        fid = fl["id"]

        requests.delete(f"{BASE_URL}/{fid}")

        r_get = requests.get(f"{BASE_URL}/{fid}")
        assert r_get.status_code == 404, (
            f"[BUG] GET /api/freelancer/{fid} returned {r_get.status_code} after DELETE. "
            f"Expected 404. The freelancer record was NOT removed — cascade delete "
            f"may be broken, or the exception is not mapped to 404."
        )

    def test_delete_cascade_user_record_removed_via_email_reuse(self):
        """
        WHAT:  Create a freelancer → Delete it → Try to re-create with the SAME email.
        WHY:   The users.email column is UNIQUE. If the User row was NOT deleted by
               the cascade, re-creating with the same email will fail because the
               old email still occupies the unique slot. This proves "ghost logins" exist.
        CHECK: Re-creation returns 201 (the old user row was fully cleaned up).
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

        # Re-create with the same email (new fullName to avoid name-duplicate check)
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
        """
        WHAT:  Create a freelancer → Delete it → Check the roster list.
        WHY:   The deleted freelancer's ID must not appear in the
               GET /api/freelancer response anymore.
        CHECK: The deleted ID is NOT in the list of roster IDs.
        """
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
    """
    The service hardcodes: userRepository.findById(1) to get the manager.
    Every freelancer is linked to this manager (user ID 1).
    If manager_id is null, the admin's "View Freelancer" page will fail.
    """

    def test_created_freelancer_has_manager_id_1(self, temp_freelancer):
        """
        WHAT:  Fetch a newly created freelancer by ID and check its manager.
        WHY:   The freelancer's manager field must point to user ID 1 (the
               system manager). A null or wrong manager breaks the admin UI.
        CHECK: response.manager.id == 1
        """
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
        """
        WHAT:  Fetch ALL freelancers and verify each one has manager.id == 1.
        WHY:   This is a global check — not just newly created ones, but every
               freelancer in the system must be linked to the manager.
        CHECK: For every freelancer in the roster: manager is not null AND id == 1.
        """
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
    The User entity has a "password" field that stores BCrypt hashes.
    When the Freelancer entity is serialized to JSON (via GET endpoints),
    the nested User object's password field gets included in the response.

    This is a CRITICAL security vulnerability — BCrypt hashes should NEVER
    be sent to the frontend. The fix is to add @JsonIgnore on User.password.
    """

    def _assert_no_password_hash_exposed(self, obj: dict, context: str):
        """Helper: recursively scan a JSON object for BCrypt hash patterns."""
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
        """
        WHAT:  Fetch the full roster and scan every nested object for BCrypt hashes.
        WHY:   The GET /api/freelancer response includes nested "user" and "manager"
               objects. Both contain a "password" field with BCrypt hashes that
               should never be sent to the frontend.
        CHECK: No field named "password" contains a value starting with "$2".
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        self._assert_no_password_hash_exposed(r.json(), "GET /api/freelancer")

    def test_get_by_id_does_not_expose_bcrypt_hash(self, live_freelancer):
        """
        WHAT:  Fetch a single freelancer by ID and check for BCrypt hash exposure.
        WHY:   Same vulnerability as the roster — the single-record endpoint also
               returns the nested User object with the password hash.
        CHECK: No "password" field contains a BCrypt hash.
        """
        fid = live_freelancer["id"]
        r = requests.get(f"{BASE_URL}/{fid}")
        assert r.status_code == 200
        self._assert_no_password_hash_exposed(r.json(), f"GET /api/freelancer/{fid}")

    def test_get_all_user_object_has_no_password_field(self):
        """
        WHAT:  Check that the nested "user" object does NOT contain a "password"
               key AT ALL in the roster response.
        WHY:   Even if the password value were null, the key's mere presence
               signals to attackers that credentials are stored here. The field
               should be completely hidden via @JsonIgnore.
        CHECK: "password" key does NOT exist in any user object.
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        for fl in r.json():
            user = fl.get("user", {})
            assert "password" not in user, (
                f"[BUG][SECURITY] 'user.password' field is present in roster for "
                f"freelancer id={fl.get('id')}. "
                f"Add @JsonIgnore on User.password or use a DTO without password. "
                f"Value: '{str(user.get('password', ''))[:15]}...'"
            )

    def test_manager_password_not_exposed_in_get_all(self):
        """
        WHAT:  Check that the nested "manager" object does NOT expose its password.
        WHY:   The manager is also a User entity. Its password field is exposed too.
               Worse: the manager's seed data stores "dummy_hash" as plaintext
               (not even a BCrypt hash) — a critical security vulnerability.
        CHECK: "password" key does NOT exist in any manager object.
        """
        r = requests.get(BASE_URL)
        assert r.status_code == 200
        for fl in r.json():
            manager = fl.get("manager", {})
            fid = fl.get("id")
            if "password" in manager and manager["password"] is not None:
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
        WHAT:  After creating a freelancer, fetch it via GET and verify the
               plain-text password from the create response is NOT in the GET body.
        WHY:   The plain-text password should only appear ONCE (in the create
               response for onboarding). It should never be stored or returned
               in subsequent GET requests.
        CHECK: The exact plain-text password string is NOT found in the GET response.
        """
        create_password = live_freelancer["create_response"].get("password", "")
        fid = live_freelancer["id"]

        r = requests.get(f"{BASE_URL}/{fid}")
        body_text = r.text

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
    The system generates a 12-character password, hashes it with BCrypt,
    and stores the hash in the users table. These tests verify the
    generated password is valid, complex, and matches the stored hash.
    """

    @pytest.mark.skipif(not BCRYPT_AVAILABLE, reason="bcrypt package not installed")
    def test_create_password_matches_stored_bcrypt_hash(self, live_freelancer):
        """
        WHAT:  Take the plain-text password from the create response and verify
               it matches the BCrypt hash stored in the database (accessed via GET).
        WHY:   If the password doesn't match the hash, the freelancer will NEVER
               be able to log in — the onboarding password is useless.
        NOTE:  This test relies on the GET endpoint exposing user.password (BUG-02).
               If BUG-02 is fixed (password hidden), this test will fail with a
               clear message explaining that a DB-level check is needed instead.
        CHECK: bcrypt.checkpw(plain_password, stored_hash) == True
        """
        fid = live_freelancer["id"]
        plain_password = live_freelancer["create_response"].get("password", "")

        r = requests.get(f"{BASE_URL}/{fid}")
        body = r.json()
        stored_hash = body.get("user", {}).get("password")

        if stored_hash is None:
            pytest.fail(
                "[INFO] user.password not exposed in GET response — "
                "cannot verify BCrypt match via API. "
                "This means BUG-02 (password exposure) is fixed. "
                "Replace this test with a direct DB query to verify BCrypt match."
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
        """
        WHAT:  Check that the create response actually contains a password.
        WHY:   If the PasswordGenerator fails silently, the response might
               contain an empty string — making onboarding impossible.
        CHECK: password is not empty and not None.
        """
        pwd = live_freelancer["create_response"].get("password", "")
        assert pwd, (
            "[BUG] Create response password is empty. "
            "PasswordGenerator may have failed silently."
        )

    def test_create_password_has_complexity(self, live_freelancer):
        """
        WHAT:  Verify the generated password contains all required character types.
        WHY:   The PasswordGenerator is documented to produce passwords with
               uppercase, lowercase, digits, and special characters. If any
               category is missing, the password may be weak.
        CHECK: At least 1 uppercase, 1 lowercase, 1 digit, 1 special character.
        """
        pwd = live_freelancer["create_response"].get("password", "")
        assert pwd, (
            "[BUG] Create response password is empty — cannot check complexity."
        )

        has_upper = any(c.isupper() for c in pwd)
        has_lower = any(c.islower() for c in pwd)
        has_digit = any(c.isdigit() for c in pwd)
        has_special = any(not c.isalnum() for c in pwd)

        assert has_upper, f"[BUG] Password '{pwd}' has no uppercase letter."
        assert has_lower, f"[BUG] Password '{pwd}' has no lowercase letter."
        assert has_digit, f"[BUG] Password '{pwd}' has no digit."
        assert has_special, f"[BUG] Password '{pwd}' has no special character."
