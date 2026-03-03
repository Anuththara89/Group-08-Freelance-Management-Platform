"""
Shared fixtures and helpers for the Freelancer API QA test suite.
"""
import uuid
import pytest
import requests

BASE_URL = "http://localhost:8080/api/freelancer"


# ---------------------------------------------------------------------------
# Payload factory
# ---------------------------------------------------------------------------

def make_payload(suffix: str | None = None) -> dict:
    """Return a valid FreelancerDTO payload with unique identifiers."""
    s = suffix or str(uuid.uuid4())[:8]
    return {
        "email": f"qa.{s}@testdomain.com",
        "fullName": f"QA Tester {s}",
        "title": "QA Engineer",
        "contactNumber": "0771234567",
        "salary": 4500.00,
        "status": "Active",
        "driveLink": "https://drive.google.com/qa-test",
    }


# ---------------------------------------------------------------------------
# Session-level connectivity check
# ---------------------------------------------------------------------------

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "smoke: quick sanity checks that the server is up"
    )
    config.addinivalue_line(
        "markers", "crud: core create/read/update/delete lifecycle"
    )
    config.addinivalue_line(
        "markers", "edge: boundary and error-handling edge cases"
    )
    config.addinivalue_line(
        "markers", "security: password exposure and access-control checks"
    )
    config.addinivalue_line(
        "markers", "integrity: relational / cascade integrity checks"
    )


@pytest.fixture(scope="session", autouse=True)
def verify_server():
    """Fail fast if the backend is not reachable."""
    try:
        r = requests.get(BASE_URL, timeout=5)
        if r.status_code not in (200, 401, 403):
            pytest.exit(f"Backend returned unexpected status {r.status_code}. Aborting.")
    except requests.exceptions.ConnectionError:
        pytest.exit(
            f"Cannot reach backend at {BASE_URL}. "
            "Please start the Spring Boot server before running QA tests."
        )


# ---------------------------------------------------------------------------
# Reusable helper: find a freelancer by email from the list endpoint
# ---------------------------------------------------------------------------

def find_freelancer_by_email(email: str) -> dict | None:
    """Return the Freelancer object from GET /api/freelancer whose user.email matches."""
    r = requests.get(BASE_URL)
    if r.status_code != 200:
        return None
    for fl in r.json():
        user = fl.get("user") or {}
        if user.get("email") == email:
            return fl
    return None


# ---------------------------------------------------------------------------
# Class-scoped fixture: create a fresh freelancer for a test class, clean up after
# ---------------------------------------------------------------------------

@pytest.fixture(scope="class")
def live_freelancer():
    """
    Create a unique freelancer before the test class runs.
    Yields a dict with keys: id, payload, create_response.
    Attempts cleanup (DELETE) after the class is done.
    """
    payload = make_payload()
    r = requests.post(f"{BASE_URL}/create", json=payload)
    assert r.status_code == 201, (
        f"Pre-condition failed: could not create test freelancer. "
        f"Status={r.status_code}, Body={r.text}"
    )

    fl = find_freelancer_by_email(payload["email"])
    assert fl is not None, "Pre-condition failed: created freelancer not found in list."

    context = {
        "id": fl["id"],
        "payload": payload,
        "create_response": r.json(),
    }
    yield context

    # Cleanup — best-effort
    requests.delete(f"{BASE_URL}/{context['id']}")


# ---------------------------------------------------------------------------
# Function-scoped fixture: create + auto-delete for isolation
# ---------------------------------------------------------------------------

@pytest.fixture()
def temp_freelancer():
    """
    Create a unique freelancer for a single test, delete it automatically afterward.
    """
    payload = make_payload()
    r = requests.post(f"{BASE_URL}/create", json=payload)
    if r.status_code != 201:
        pytest.skip(f"Could not create temp freelancer (status={r.status_code})")

    fl = find_freelancer_by_email(payload["email"])
    if fl is None:
        pytest.skip("Temp freelancer not found after creation.")

    context = {"id": fl["id"], "payload": payload}
    yield context

    requests.delete(f"{BASE_URL}/{context['id']}")
