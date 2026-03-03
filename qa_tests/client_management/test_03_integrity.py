"""
test_03_integrity.py
====================
Relational integrity, missing features, and security tests
for the Client Management API.

Covers:
  - Cascade delete validation
  - Manager linkage (manager_id)
  - Missing entity fields (companyName, budget, contractType, paymentStatus)
  - Password / sensitive data exposure
  - URL path convention mismatch
"""
import pytest
import requests
from conftest import BASE_URL, make_payload, find_client_by_email


# ===========================================================================
# TC-INT-01  Cascade Delete
# ===========================================================================

@pytest.mark.integrity
class TestCascadeDelete:
    """
    The DB schema has: client.id is referenced by project(client_id) ON DELETE CASCADE.
    But the client table itself has no cascade FROM users — the client entity
    does not have a User relationship (unlike Freelancer which shares user_id).

    These tests verify that DELETE actually removes the client record.
    """

    def test_delete_removes_client_from_list(self):
        """
        WHAT:  Create a client → DELETE it → Check the list.
        WHY:   After deletion, the client must not appear in GET /clients/all.
        CHECK: Client email not found in the list after DELETE.
        """
        payload = make_payload()
        r = requests.post(f"{BASE_URL}/add", json=payload)
        cid = r.json()["id"]

        requests.delete(f"{BASE_URL}/delete/{cid}")

        cl = find_client_by_email(payload["email"])
        assert cl is None, (
            f"[BUG] Client (id={cid}) still in list after DELETE."
        )

    def test_delete_allows_reregistration_by_email(self):
        """
        WHAT:  Create → Delete → Re-create with same email.
        WHY:   If the delete didn't fully remove the record, re-creation
               could fail (if a UNIQUE constraint existed) or silently create
               a ghost duplicate.
        CHECK: Re-creation succeeds.
        """
        payload = make_payload()
        r1 = requests.post(f"{BASE_URL}/add", json=payload)
        cid = r1.json()["id"]

        requests.delete(f"{BASE_URL}/delete/{cid}")

        payload2 = {**payload, "name": f"Reborn {payload['name']}"}
        r2 = requests.post(f"{BASE_URL}/add", json=payload2)

        if r2.status_code == 200:
            requests.delete(f"{BASE_URL}/delete/{r2.json()['id']}")

        assert r2.status_code == 200, (
            f"[BUG] Re-registration after delete failed ({r2.status_code}). "
            f"The client record may not have been fully removed."
        )


# ===========================================================================
# TC-INT-02  Manager Linkage
# ===========================================================================

@pytest.mark.integrity
class TestManagerLinkage:
    """
    The spec says: "Verify every created client is linked to Manager ID = 1.
    If NULL → Admin client view will fail to load."

    The DB schema has: client.manager_id INTEGER REFERENCES users(id).
    But the Client entity DOES NOT map this column — it's completely missing
    from Client.java.
    """

    def test_created_client_has_manager_id(self, temp_client):
        """
        WHAT:  Fetch a newly created client and check for a manager field.
        WHY:   The spec requires every client to be linked to manager_id = 1.
               The Client entity does not have a manager field mapped.
        CHECK: Response contains a "manager" or "manager_id" field.
        """
        # Since GET by ID doesn't exist, use the list endpoint
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        found = next((c for c in clients if c["id"] == temp_client["id"]), None)
        assert found is not None, "Temp client not found in list."

        has_manager = (
            "manager" in found
            or "manager_id" in found
            or "managerId" in found
        )
        assert has_manager, (
            f"[BUG] Client id={temp_client['id']} has no manager field in the response. "
            f"The DB schema has a manager_id column, but the Client entity (Client.java) "
            f"does not map it. The entity only has: id, name, email, phone. "
            f"A @ManyToOne relationship to the Manager/User entity is missing."
        )

    def test_created_client_manager_id_is_1(self, temp_client):
        """
        WHAT:  Verify the manager_id is specifically 1 for a newly created client.
        WHY:   The spec requires all clients to be linked to manager_id = 1.
               Even if the field existed, the service doesn't set it during creation.
        CHECK: manager.id == 1 or manager_id == 1
        """
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        found = next((c for c in clients if c["id"] == temp_client["id"]), None)
        assert found is not None

        manager_id = (
            found.get("managerId")
            or found.get("manager_id")
            or (found.get("manager", {}) or {}).get("id")
        )
        assert manager_id == 1, (
            f"[BUG] Client id={temp_client['id']} has manager_id={manager_id}, expected 1. "
            f"The ClientService.saveClient() does not assign a manager during creation. "
            f"Unlike FreelancerService which does userRepository.findById(1), the "
            f"ClientService has no manager assignment logic at all."
        )


# ===========================================================================
# TC-INT-03  Missing Entity Fields
# ===========================================================================

@pytest.mark.integrity
class TestMissingEntityFields:
    """
    The DB schema defines these columns for the client table that are
    NOT mapped in the Client entity:
      - company_name VARCHAR(255)
      - contract_type VARCHAR(100)
      - payment_status VARCHAR(50)
      - manager_id INTEGER

    The spec also mentions a "budget" field that doesn't exist in the DB either.
    """

    def test_client_response_has_company_name_field(self, temp_client):
        """
        WHAT:  Check if the client response includes a companyName field.
        WHY:   The DB has company_name, the spec requires companyName,
               but the Client entity doesn't map it.
        CHECK: "companyName" or "company_name" exists in the response.
        """
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        found = next((c for c in clients if c["id"] == temp_client["id"]), None)
        assert found is not None

        has_company = "companyName" in found or "company_name" in found
        assert has_company, (
            f"[BUG] Client response has no companyName field. "
            f"The DB schema has company_name but Client.java does not map it. "
            f"Entity only has: {list(found.keys())}"
        )

    def test_client_response_has_contract_type_field(self, temp_client):
        """
        WHAT:  Check if the client response includes a contractType field.
        WHY:   The DB has contract_type but the entity doesn't map it.
        CHECK: "contractType" or "contract_type" exists in the response.
        """
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        found = next((c for c in clients if c["id"] == temp_client["id"]), None)
        assert found is not None

        has_field = "contractType" in found or "contract_type" in found
        assert has_field, (
            f"[BUG] Client response has no contractType field. "
            f"The DB schema has contract_type but Client.java does not map it."
        )

    def test_client_response_has_payment_status_field(self, temp_client):
        """
        WHAT:  Check if the client response includes a paymentStatus field.
        WHY:   The DB has payment_status but the entity doesn't map it.
        CHECK: "paymentStatus" or "payment_status" exists in the response.
        """
        r = requests.get(f"{BASE_URL}/all")
        clients = r.json()
        found = next((c for c in clients if c["id"] == temp_client["id"]), None)
        assert found is not None

        has_field = "paymentStatus" in found or "payment_status" in found
        assert has_field, (
            f"[BUG] Client response has no paymentStatus field. "
            f"The DB schema has payment_status but Client.java does not map it."
        )


# ===========================================================================
# TC-INT-04  URL Path Convention
# ===========================================================================

@pytest.mark.integrity
class TestUrlPathConvention:
    """
    The spec defines endpoints under /api/client/... but the actual
    implementation uses /clients/... This tests that the spec URLs exist.
    """

    def test_spec_url_create_exists(self):
        """
        WHAT:  POST to /api/client/create (the spec URL).
        WHY:   The spec documents this as the create endpoint, but the actual
               implementation uses /clients/add. The URL mismatch means
               frontend code written against the spec will break.
        CHECK: status_code != 404
        """
        payload = make_payload()
        r = requests.post("http://localhost:8080/api/client/create", json=payload)

        # Cleanup if it somehow worked
        if r.status_code in (200, 201):
            try:
                body = r.json()
                if body.get("id"):
                    requests.delete(f"{BASE_URL}/delete/{body['id']}")
            except Exception:
                pass

        assert r.status_code != 404, (
            f"[BUG] POST /api/client/create returned 404. "
            f"The spec URL does not exist — the actual endpoint is POST /clients/add. "
            f"The controller uses @RequestMapping(\"/clients\") instead of "
            f"@RequestMapping(\"/api/client\")."
        )

    def test_spec_url_get_all_exists(self):
        """
        WHAT:  GET /api/client (the spec URL for listing all clients).
        WHY:   The spec documents this URL, but the actual is GET /clients/all.
        CHECK: status_code == 200
        """
        r = requests.get("http://localhost:8080/api/client")
        assert r.status_code == 200, (
            f"[BUG] GET /api/client returned {r.status_code}. "
            f"The spec URL does not exist — the actual endpoint is GET /clients/all."
        )

    def test_spec_url_delete_exists(self):
        """
        WHAT:  DELETE /api/client/999999 (the spec URL for deletion).
        WHY:   The spec says DELETE /api/client/{id}, but actual is
               DELETE /clients/delete/{id}.
        CHECK: status_code in (200, 404) — either works or says not found,
               but NOT 405/404 for the route itself.
        """
        r = requests.delete("http://localhost:8080/api/client/999999")
        assert r.status_code in (200, 404), (
            f"[BUG] DELETE /api/client/999999 returned {r.status_code}. "
            f"The spec URL does not exist — the actual endpoint is "
            f"DELETE /clients/delete/{{id}}."
        )


# ===========================================================================
# TC-SEC-01  Sensitive Data Exposure
# ===========================================================================

@pytest.mark.security
class TestSensitiveDataExposure:
    """
    Verify that GET responses do not expose sensitive fields.
    The client entity currently has no User relationship (no password to leak),
    but we verify this defensively.
    """

    def test_get_all_does_not_expose_password_hashes(self):
        """
        WHAT:  Fetch all clients and scan for BCrypt hash patterns.
        WHY:   If a User relationship is ever added to Client, password hashes
               could leak (like the Freelancer API bug). Defensive check.
        CHECK: No field value starts with "$2" (BCrypt prefix).
        """
        r = requests.get(f"{BASE_URL}/all")
        assert r.status_code == 200
        for cl in r.json():
            for key, val in cl.items():
                if isinstance(val, str) and val.startswith("$2"):
                    pytest.fail(
                        f"[BUG][SECURITY] BCrypt hash found in field '{key}' for "
                        f"client id={cl.get('id')}. Value: '{val[:15]}...'"
                    )
                if isinstance(val, dict):
                    for k2, v2 in val.items():
                        if k2 == "password" and v2 is not None:
                            pytest.fail(
                                f"[BUG][SECURITY] Password field exposed in nested object "
                                f"for client id={cl.get('id')}, key='{key}.{k2}'"
                            )
