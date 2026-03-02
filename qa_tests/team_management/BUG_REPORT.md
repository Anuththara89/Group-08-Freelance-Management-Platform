# QA Bug Report — Freelancer Management API
**Date:** 2026-03-02
**Backend:** Spring Boot · `com.freelance.freelancepm`
**Base URL tested:** `http://localhost:8080/api/freelancer`
**Test suite:** Python / pytest (`qa_tests/`)
**Run result:** 34 passed · **12 failed** · 0 errors · 0 skipped

---

## Executive Summary

| Category | Total Tests | Passed | Failed |
|---|---|---|---|
| Core CRUD | 19 | 19 | 0 |
| Edge Cases & Validation | 15 | 8 | 7 |
| Relational Integrity | 5 | 5 | 0 |
| Security | 7 | 3 | 4 |
| **TOTAL** | **46** | **34** | **12** |

All CRUD operations work correctly. The failures fall into **two distinct root-cause categories**:

1. **Missing global exception handler** — causes 12 error-status failures across multiple test cases.
2. **Password hash leak** — user and manager password fields serialized into every GET response.

---

## BUG-01 · CRITICAL · Missing Global Exception Handler (`@ControllerAdvice`)
**Tests failed:** 8
**Affected endpoints:** ALL

### Description
The application has no `@ControllerAdvice` or `@ResponseStatus` annotation to map domain exceptions to appropriate HTTP status codes. Spring Boot's default error handler converts *every* unhandled exception into **HTTP 500 Internal Server Error**, regardless of whether the cause is a client error (invalid input, missing resource) or a genuine server fault.

### Observed vs Expected

| Scenario | Expected | Actual |
|---|---|---|
| Create with duplicate fullName | `400 Bad Request` | `500 Internal Server Error` |
| PUT update to conflicting fullName | `400 Bad Request` | `500 Internal Server Error` |
| GET /api/freelancer/{non-existent-id} | `404 Not Found` | `500 Internal Server Error` |
| DELETE /api/freelancer/{non-existent-id} | `404 Not Found` | `500 Internal Server Error` |
| PUT /api/freelancer/{non-existent-id} | `404 Not Found` | `500 Internal Server Error` |
| POST without email field | `400 Bad Request` | `500 Internal Server Error` |
| POST with `null` email | `400 Bad Request` | `500 Internal Server Error` |

### Root Cause
```
FreelancerService.java:31  → throws IllegalArgumentException      (unmapped → 500)
FreelancerService.java:64  → throws ResourceNotFoundException     (unmapped → 500)
FreelancerService.java:88  → throws IllegalArgumentException      (unmapped → 500)
UserRepository.save()      → throws DataIntegrityViolationException (unmapped → 500)
```

### Impact
- **Frontend developers** cannot distinguish between a client-side mistake (bad input) and a real server crash. Every error looks the same.
- **Users** see cryptic 500 errors instead of actionable messages.
- **Security:** Raw Spring error objects may leak internal paths and class names.

### Fix
Create a `@RestControllerAdvice` class in `com.freelance.freelancepm.exception`:

```java
@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(ResourceNotFoundException.class)
    public ResponseEntity<Map<String, String>> handleNotFound(ResourceNotFoundException ex) {
        return ResponseEntity.status(HttpStatus.NOT_FOUND)
            .body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<Map<String, String>> handleBadRequest(IllegalArgumentException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Map.of("error", ex.getMessage()));
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<Map<String, String>> handleDataIntegrity(DataIntegrityViolationException ex) {
        return ResponseEntity.status(HttpStatus.BAD_REQUEST)
            .body(Map.of("error", "A required field is missing or violates a uniqueness constraint."));
    }
}
```

---

## BUG-02 · CRITICAL · BCrypt Password Hashes Exposed in GET Responses
**Tests failed:** 4
**Affected endpoints:** `GET /api/freelancer`, `GET /api/freelancer/{id}`

### Description
Every `GET` response includes the full nested `User` object, which contains the `password` field storing the BCrypt hash. This hash is serialized into the JSON response and sent to any client that calls the list or detail endpoint.

### Evidence (live response excerpt)
```json
{
  "id": 5,
  "fullName": "John Doe",
  "user": {
    "id": 5,
    "email": "johndoe@example.com",
    "password": "$2a$10$S3truZZpIUVqbwhdGtni4efh6Trp9HpAramc.QppK4rwkIgKZnAUK",
    "role": "Freelancer"
  },
  "manager": {
    "id": 1,
    "email": "manager@kingsman.com",
    "password": "dummy_hash",
    "role": "MANAGER"
  }
}
```

### Impact
- Exposes credential hashes to frontend / any authenticated client — violates OWASP A02:2021 (Cryptographic Failures).
- Even though BCrypt hashes cannot be reversed easily, exposing them allows offline brute-force attacks.
- The manager's password is stored as the **plaintext string `"dummy_hash"`** — this is a critical seed-data vulnerability (see BUG-03).

### Fix (Option A — quickest)
Add `@JsonIgnore` to the `password` field in `User.java`:

```java
// User.java
import com.fasterxml.jackson.annotation.JsonIgnore;

@JsonIgnore
@Column(name = "password", length = 255, nullable = false)
private String password;
```

### Fix (Option B — recommended)
Return a dedicated `FreelancerResponseDTO` from the GET endpoints that excludes the `user` and `manager` nested objects entirely, exposing only safe fields (`id`, `fullName`, `email`, `title`, `contactNumber`, `salary`, `status`, `driveLink`, `managerId`).

---

## BUG-03 · HIGH · Manager Seed Data Stores Plaintext Password
**Detected by:** `test_manager_password_not_exposed_in_get_all`

### Description
The `manager` user (ID=1) in the database has `password = "dummy_hash"` — a plaintext string, not a BCrypt hash. If anyone ever tries to log in with this account, authentication will fail unpredictably, and the value itself is insecure.

### Evidence
```json
"manager": {
  "id": 1,
  "password": "dummy_hash",   ← plaintext, not BCrypt
  "role": "MANAGER"
}
```

### Fix
Update the seed/migration script to store a proper BCrypt hash for the manager:

```sql
UPDATE users SET password = '$2a$10$<proper_bcrypt_hash>' WHERE id = 1;
```

Or regenerate via the application's `PasswordEncoder` at startup.

---

## BUG-04 · MEDIUM · Empty String Email Accepted on Create
**Test failed:** `test_create_with_empty_string_email_returns_4xx`
**Endpoint:** `POST /api/freelancer/create`

### Description
When `email` is sent as an empty string `""`, the API creates the freelancer successfully and returns `201`. The `users.email` column has a `NOT NULL` constraint, but an empty string satisfies that constraint at the DB level. No application-layer validation prevents it.

### Observed
- `POST` with `{"email": ""}` → **201 Created**
- A freelancer with `user.email = ""` is inserted into the database.

### Impact
- Two freelancers with empty-string emails can coexist (violating intent).
- The `email UNIQUE` constraint technically prevents a second empty-string user, but the first one should never be created.
- Login with an empty email would be non-functional.

### Fix
Add Bean Validation annotations to `FreelancerDTO`:

```java
@NotBlank(message = "Email is required")
@Email(message = "Email must be a valid address")
private String email;

@NotBlank(message = "Full name is required")
private String fullName;
```

And enable validation in the controller:

```java
@PostMapping("/create")
public ResponseEntity<Object> create(@Valid @RequestBody FreelancerDTO freelancerDTO) { ... }
```

---

## BUG-05 · MEDIUM · `deleteFreelancer` Throws Wrong Exception Type for Not Found
**Endpoint:** `DELETE /api/freelancer/{id}`
**Source:** `FreelancerService.java:88`

### Description
When a non-existent ID is passed to `deleteFreelancer`, the service throws `IllegalArgumentException("Freelancer not found with id: " + user_id)`. All other lookup methods (`getFreelancerById`) correctly throw `ResourceNotFoundException`. This inconsistency means:

1. Even after BUG-01 is fixed, `DELETE` with a missing ID would return `400 Bad Request` instead of `404 Not Found`.
2. The error message "Freelancer not found" in an `IllegalArgumentException` is semantically incorrect (that exception is for invalid arguments, not missing resources).

### Fix
Change `FreelancerService.java:88`:

```java
// Before
if (!userRepository.existsById(user_id)) {
    throw new IllegalArgumentException("Freelancer not found with id: " + user_id);
}

// After
if (!userRepository.existsById(user_id)) {
    throw new ResourceNotFoundException("Freelancer not found with id: " + user_id);
}
```

---

## BUG-06 · LOW · Create Response Does Not Return the Freelancer ID
**Endpoint:** `POST /api/freelancer/create`
**Note:** Design gap, not a crash bug

### Description
The `TeamResponseDTO` returned by `POST /create` contains `{ memberName, email, password }` but **no `id`**. Callers have no direct way to know the ID of the newly created freelancer without making a subsequent `GET /api/freelancer` call and searching by email.

### Impact
- Makes the API harder to use programmatically.
- Creates a race condition if two freelancers are created simultaneously and the caller tries to find the right one by email.

### Fix
Add `id` to `TeamResponseDTO`:

```java
@Data
public class TeamResponseDTO {
    private Integer id;
    private String memberName;
    private String email;
    private String password;
}
```

And set it in `FreelancerService.createFreelancer` after saving.

---

## Passing Checks (confirmed working)

| Area | Test | Result |
|---|---|---|
| Create | Returns 201 | ✅ PASS |
| Create | Returns `memberName`, `email`, `password` | ✅ PASS |
| Create | Password is exactly 12 characters | ✅ PASS |
| Create | Password is plain-text (not BCrypt) | ✅ PASS |
| View Roster | Returns 200 + JSON array | ✅ PASS |
| View Roster | Every freelancer linked to Manager ID 1 | ✅ PASS |
| Get by ID | Returns 200 + correct freelancer | ✅ PASS |
| Update | Returns 200 + updated body | ✅ PASS |
| Update (partial) | Only changed field updates | ✅ PASS |
| Delete | Returns 200 | ✅ PASS |
| Delete | Freelancer removed from roster | ✅ PASS |
| Cascade Delete | Freelancer+User both removed | ✅ PASS |
| Re-registration | Create → Delete → Re-create succeeds | ✅ PASS |
| String salary | Returns 400 (Jackson deserialization) | ✅ PASS |
| Error body | No Java stack trace in response body | ✅ PASS |
| Password complexity | Generated password has all character types | ✅ PASS |
| BCrypt match | Generated password verifies against stored hash | ✅ PASS |
| Manager linkage | All freelancers linked to manager ID 1 | ✅ PASS |

---

## Bug Priority Summary

| ID | Severity | Title | Fix Effort |
|---|---|---|---|
| BUG-01 | **CRITICAL** | Missing `@ControllerAdvice` — all errors return 500 | Low (~1h) |
| BUG-02 | **CRITICAL** | BCrypt hashes exposed in every GET response | Low (~30min) |
| BUG-03 | **HIGH** | Manager seed data uses plaintext password | Low (~15min) |
| BUG-04 | **MEDIUM** | Empty string email creates a freelancer | Low (~30min) |
| BUG-05 | **MEDIUM** | DELETE throws `IllegalArgumentException` instead of `ResourceNotFoundException` | Trivial |
| BUG-06 | **LOW** | Create response missing freelancer `id` | Low (~30min) |

---

*Report generated by automated QA suite — `qa_tests/` · Run time: 64s · 46 tests*
