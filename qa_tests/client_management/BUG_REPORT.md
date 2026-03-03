# QA Bug Report — Client Management API
**Date:** 2026-03-03
**Backend:** Spring Boot · `com.freelance.freelancepm`
**Actual base URL:** `http://localhost:8080/clients`
**Test suite:** Python / pytest (`qa_tests/client_management/`)
**Run result:** 20 passed · **19 failed** · 0 skipped

---

## Executive Summary

| Category | Total Tests | Passed | Failed |
|---|---|---|---|
| Core CRUD | 16 | 10 | 6 |
| Edge Cases & Validation | 12 | 5 | 7 |
| Relational Integrity | 7 | 2 | 5 |
| Security | 1 | 1 | 0 |
| URL Convention | 3 | 1 | 2 |
| **TOTAL** | **39** | **20** | **19** |

The Client Management API has **critical implementation gaps** compared to the spec. Only 3 out of 5 required endpoints exist, several DB columns are not mapped in the entity, and there is no input validation or business logic.

---

## BUG-C01 · CRITICAL · GET by ID Endpoint Not Implemented
**Test failed:** `test_get_by_id_endpoint_exists`
**Expected endpoint:** `GET /clients/{id}`

### Description
The spec requires a "Search by ID" endpoint. The `ClientController` only defines three routes: `POST /clients/add`, `GET /clients/all`, and `DELETE /clients/delete/{id}`. There is no `@GetMapping("/{id}")` handler.

### Impact
- The frontend cannot load a single client's detail page.
- All client detail views will fail.

### Fix
Add to `ClientController.java`:
```java
@GetMapping("/{id}")
public ResponseEntity<Client> getClientById(@PathVariable Integer id) {
    return clientService.getClientById(id)
        .map(client -> new ResponseEntity<>(client, HttpStatus.OK))
        .orElseThrow(() -> new ResourceNotFoundException("Client not found with id: " + id));
}
```

---

## BUG-C02 · CRITICAL · PUT Update Endpoint Not Implemented
**Test failed:** `test_update_endpoint_exists`
**Expected endpoint:** `PUT /clients/{id}`

### Description
The spec requires a "Update Client Info" endpoint with partial update support. The `ClientController` has no `@PutMapping` handler at all.

### Impact
- Admins cannot edit any client details after creation.
- The only way to change a client is to delete and re-create.

### Fix
Add a `@PutMapping("/{id}")` handler in `ClientController` and an `updateClient()` method in `ClientService`.

---

## BUG-C03 · CRITICAL · Client Entity Missing 4 DB Columns
**Tests failed:** `test_client_response_has_company_name_field`, `test_client_response_has_contract_type_field`, `test_client_response_has_payment_status_field`, `test_created_client_has_manager_id`

### Description
The database schema defines these columns on the `client` table:

| DB Column | Type | Mapped in Client.java? |
|---|---|---|
| `manager_id` | INTEGER REFERENCES users(id) | **NO** |
| `company_name` | VARCHAR(255) | **NO** |
| `contract_type` | VARCHAR(100) | **NO** |
| `payment_status` | VARCHAR(50) | **NO** |

The `Client.java` entity only maps 4 fields: `id`, `name`, `email`, `phone`.

### Impact
- Company name, contract type, and payment status cannot be stored or retrieved via the API.
- Manager linkage is completely missing — admin views that depend on manager_id will fail.

### Fix
Add the missing fields to `Client.java`:
```java
@ManyToOne
@JoinColumn(name = "manager_id")
private User manager;

@Column(name = "company_name")
private String companyName;

@Column(name = "contract_type")
private String contractType;

@Column(name = "payment_status")
private String paymentStatus;
```

---

## BUG-C04 · HIGH · No Temporary Password Generation on Create
**Test failed:** `test_create_response_contains_temporary_password`

### Description
The spec requires the create response to include a `temporaryPassword` for client onboarding (similar to the Freelancer API). The `ClientService.saveClient()` simply saves the entity — it does not create a User record, generate a password, or return onboarding credentials.

### Impact
- Clients have no login credentials — they cannot access the system.

---

## BUG-C05 · HIGH · No Manager Assignment on Create
**Test failed:** `test_created_client_manager_id_is_1`

### Description
The spec says "Verify every created client is linked to Manager ID = 1." The `ClientService.saveClient()` does not assign any manager. The `manager_id` column in the DB is always NULL for API-created clients.

### Impact
- Admin "View Client" pages that filter by manager_id will not load.

---

## BUG-C06 · HIGH · URL Path Mismatch — `/clients/*` vs `/api/client/*`
**Tests failed:** `test_spec_url_create_exists`, `test_spec_url_get_all_exists`

### Description

| Spec URL | Actual URL |
|---|---|
| `POST /api/client/create` | `POST /clients/add` |
| `GET /api/client` | `GET /clients/all` |
| `GET /api/client/{id}` | Not implemented |
| `PUT /api/client/{id}` | Not implemented |
| `DELETE /api/client/{id}` | `DELETE /clients/delete/{id}` |

The controller uses `@RequestMapping("/clients")` instead of `@RequestMapping("/api/client")`.

### Impact
- Frontend code written against the spec URLs will get 404 errors.
- Inconsistent with the Freelancer API which uses `/api/freelancer`.

### Fix
Change `ClientController.java`:
```java
@RequestMapping("/api/client")  // was "/clients"
```

---

## BUG-C07 · HIGH · Create Returns 200 Instead of 201
**Test failed:** `test_create_returns_success`

### Description
The controller returns `new ResponseEntity<>(savedClient, HttpStatus.OK)` (200) for a successful creation. The HTTP standard and the spec expect 201 (Created).

### Fix
```java
return new ResponseEntity<>(savedClient, HttpStatus.CREATED);
```

---

## BUG-C08 · HIGH · No Duplicate Name/Email Prevention
**Tests failed:** `test_duplicate_name_is_rejected`, `test_duplicate_email_is_rejected`

### Description
The spec says "Attempt to POST a new client with a fullName that already exists → IllegalArgumentException." The `ClientService.saveClient()` has zero validation — it directly calls `clientRepository.save()`. Two clients with the same name or email are happily accepted.

Additionally, the DB schema has no UNIQUE constraint on `client.email` or `client.name`.

### Impact
- Multiple clients with identical names/emails can exist, causing confusion.

---

## BUG-C09 · MEDIUM · Missing Validation — Empty/Null Name and Email Accepted
**Tests failed:** 5 tests in `TestEmptyFieldsOnCreate`

| Input | Expected | Actual |
|---|---|---|
| `name` field missing | 400 | 500 (DataIntegrityViolation) |
| `name: null` | 400 | 500 |
| `name: ""` | 400 | **201 accepted** |
| `email: ""` | 400 | **201 accepted** |
| `email` field missing | 400 | **201 accepted** |

### Description
The Client entity has no Bean Validation annotations (`@NotBlank`, `@Email`, etc.). Empty strings pass the DB NOT NULL constraint, and missing email is accepted because the DB allows NULL on the email column.

### Fix
Add validation annotations and `@Valid` on the controller.

---

## Passing Checks (confirmed working)

| Area | Test | Result |
|---|---|---|
| Create | Returns response with id (auto-generated) | PASS |
| Create | Returns correct name | PASS |
| Create | Returns correct email | PASS |
| Create | Returns correct phone | PASS |
| List | Returns 200 | PASS |
| List | Returns JSON array | PASS |
| List | All records have id, name, email | PASS |
| Delete | Returns 200 | PASS |
| Delete | Removes client from list | PASS |
| Delete | Response says "deleted successfully" | PASS |
| Delete | Non-existent ID returns 404 | PASS |
| Delete (edge) | Non-existent ID returns 404 | PASS |
| Delete (edge) | Non-existent ID says "not found" | PASS |
| Not-found GET | Returns 404 (route doesn't exist) | PASS |
| Re-registration | Create → Delete → Re-create (email) | PASS |
| Re-registration | Create → Delete → Re-create (name) | PASS |
| Cascade delete | Client removed from list | PASS |
| Cascade delete | Email freed for re-registration | PASS |
| Security | No password hashes in GET responses | PASS |
| URL convention | DELETE /api/client/{id} route exists | PASS |

---

## Bug Priority Summary

| ID | Severity | Title |
|---|---|---|
| BUG-C01 | **CRITICAL** | GET by ID endpoint not implemented |
| BUG-C02 | **CRITICAL** | PUT update endpoint not implemented |
| BUG-C03 | **CRITICAL** | Client entity missing 4 DB columns (companyName, contractType, paymentStatus, manager_id) |
| BUG-C04 | **HIGH** | No temporary password generation on create |
| BUG-C05 | **HIGH** | No manager assignment on create |
| BUG-C06 | **HIGH** | URL path mismatch (`/clients/*` vs spec `/api/client/*`) |
| BUG-C07 | **HIGH** | Create returns 200 instead of 201 |
| BUG-C08 | **HIGH** | No duplicate name/email prevention |
| BUG-C09 | **MEDIUM** | No input validation — empty/null name and email accepted |

---

*Report generated by automated QA suite — `qa_tests/client_management/` · Run time: 25s · 39 tests*
