"""
Shared fixtures and helpers for the Client Management API QA test suite.

NOTE: The actual endpoints are:
  POST   /clients/add          (spec says /api/client/create)
  GET    /clients/all           (spec says /api/client)
  DELETE /clients/delete/{id}   (spec says /api/client/{id})
  GET    /clients/{id}          NOT IMPLEMENTED (spec says /api/client/{id})
  PUT    /clients/{id}          NOT IMPLEMENTED (spec says /api/client/{id})
"""
import uuid
import pytest
import requests

BASE_URL = "http://localhost:8080/clients"


# ---------------------------------------------------------------------------
# Payload factory
# ---------------------------------------------------------------------------

def make_payload(suffix: str | None = None) -> dict:
    """Return a valid client payload with unique identifiers."""
    s = suffix or str(uuid.uuid4())[:8]
    return {
        "name": f"QA Client {s}",
        "email": f"qa.client.{s}@testdomain.com",
        "phone": "0771234567",
    }


# ---------------------------------------------------------------------------
# Markers
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line("markers", "crud: core CRUD lifecycle tests")
    config.addinivalue_line("markers", "edge: boundary and error-handling tests")
    config.addinivalue_line("markers", "integrity: relational / cascade / missing-feature tests")
    config.addinivalue_line("markers", "security: password and data exposure checks")


# ---------------------------------------------------------------------------
# Session-level connectivity check
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session", autouse=True)
def verify_server():
    """Fail fast if the backend is not reachable."""
    try:
        r = requests.get(f"{BASE_URL}/all", timeout=5)
        if r.status_code not in (200, 401, 403):
            pytest.exit(
                f"Backend returned {r.status_code} for GET /clients/all. Aborting."
            )
    except requests.exceptions.ConnectionError:
        pytest.exit(
            f"Cannot reach backend at {BASE_URL}. "
            "Please start the Spring Boot server before running QA tests."
        )


# ---------------------------------------------------------------------------
# Helper: find a client by email from the list endpoint
# ---------------------------------------------------------------------------

def find_client_by_email(email: str) -> dict | None:
    """Return the Client object from GET /clients/all whose email matches."""
    r = requests.get(f"{BASE_URL}/all")
    if r.status_code != 200:
        return None
    for cl in r.json():
        if cl.get("email") == email:
            return cl
    return None


def find_client_by_name(name: str) -> dict | None:
    """Return the Client object from GET /clients/all whose name matches."""
    r = requests.get(f"{BASE_URL}/all")
    if r.status_code != 200:
        return None
    for cl in r.json():
        if cl.get("name") == name:
            return cl
    return None


# ---------------------------------------------------------------------------
# Class-scoped fixture: create a client for a test class, clean up after
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def live_client():
    """
    Create a unique client before the test class runs.
    Yields a dict with keys: id, payload, create_response.
    Attempts cleanup (DELETE) after the class is done.
    """
    payload = make_payload()
    r = requests.post(f"{BASE_URL}/add", json=payload)
    assert r.status_code == 200, (
        f"Pre-condition failed: could not create test client. "
        f"Status={r.status_code}, Body={r.text}"
    )
    body = r.json()
    client_id = body.get("id")
    assert client_id is not None, "Pre-condition failed: create response has no 'id'."

    context = {
        "id": client_id,
        "payload": payload,
        "create_response": body,
    }
    yield context

    # Cleanup
    requests.delete(f"{BASE_URL}/delete/{context['id']}")


# ---------------------------------------------------------------------------
# Function-scoped fixture: create + auto-delete for isolation
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_client():
    """Create a unique client for a single test, delete it afterward."""
    payload = make_payload()
    r = requests.post(f"{BASE_URL}/add", json=payload)
    if r.status_code != 200:
        pytest.fail(f"Could not create temp client (status={r.status_code})")

    body = r.json()
    client_id = body.get("id")
    if client_id is None:
        pytest.fail("Temp client create response has no 'id'.")

    context = {"id": client_id, "payload": payload, "create_response": body}
    yield context

    requests.delete(f"{BASE_URL}/delete/{context['id']}")
