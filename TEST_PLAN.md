# CheersthePure DispatchAI Test Plan

## QA Scope

This plan is intentionally limited to testing and verification. It does not modify application behavior or introduce speculative features. The goal is to validate the current project without changing working functionality.

The project must be classified as one of:
- PASS
- FAIL
- WARNING
- NOT TESTED

No API keys, secrets, tokens, or private customer data are to be exposed in logs, screenshots, or chat output.

---

## A. Environment

Objective:
- Confirm the runtime environment is valid and reproducible.

Checks:
- Python version and platform compatibility
- Virtual environment state
- Dependency installation state
- OS-specific behavior
- Repository path and working tree status

Evidence:
- python --version
- pip freeze or requirements verification
- local environment status

Status expectation:
- PASS if the project runs in a clean supported Python environment.
- FAIL if the runtime cannot start or cannot import Django.
- WARNING if the runtime works but the environment is inconsistent or undocumented.
- NOT TESTED if no environment validation has been executed yet.

---

## B. Dependencies

Objective:
- Verify required packages are installed and compatible.

Checks:
- requirements.txt contents
- version compatibility between Django, Django-Axes, Stripe, Groq, Hindsight client, etc.
- missing or conflicting packages
- unused or duplicate dependencies

Evidence:
- dependency install log
- import checks
- pip check

Status expectation:
- PASS if all declared dependencies can be imported and are consistent.
- FAIL if dependency resolution is broken or incompatible.
- WARNING if a dependency is installed but not required or is outdated.
- NOT TESTED if dependency verification has not occurred.

---

## C. Configuration

Objective:
- Verify configuration is safe and complete.

Checks:
- environment variables in .env.example and .env usage
- SECRET_KEY handling
- DEBUG mode behavior
- ALLOWED_HOSTS
- database configuration
- admin configuration
- external service settings for Stripe, Groq, Hindsight

Evidence:
- settings inspection
- environment variable review
- Django startup and system checks

Status expectation:
- PASS if configuration is documented and safe.
- FAIL if required configuration is missing or misconfigured.
- WARNING if defaults are used in a non-production setting.
- NOT TESTED if the configuration has not been executed in a live environment.

---

## D. Django/System Checks

Objective:
- Validate project startup health.

Checks:
- python manage.py check
- django system checks for models, URLs, templates, and app wiring
- warnings and deprecations
- missing authentication backend configuration

Evidence:
- manage.py check output
- warnings list

Status expectation:
- PASS if the project passes system checks.
- FAIL if the app cannot start or has blocking issues.
- WARNING if only non-blocking warnings remain.
- NOT TESTED if no system check has been run.

---

## E. Database

Objective:
- Verify schema and database integrity.

Checks:
- migration state
- SQLite database usability
- schema consistency across app and dispatch models
- data creation and retrieval behavior
- index usage and query performance risks

Evidence:
- python manage.py migrate
- python manage.py showmigrations
- database query inspection for critical paths

Status expectation:
- PASS if migrations are clean and app data is created/retrieved correctly.
- FAIL if migrations are broken or data model behavior is inconsistent.
- WARNING if data integrity is likely okay but query performance is not yet measured.
- NOT TESTED if no migration or DB validation has been run.

---

## F. Existing CheersthePure Application

Objective:
- Confirm the base storefront and business functionality remain intact.

Checks:
- homepage loads correctly
- catalog pages render
- user account flow works
- core business pages function
- order and quote workflows still work without regression

Evidence:
- URL-by-URL smoke tests
- Django view tests
- browser verification of key pages

Status expectation:
- PASS if all critical site functions still work.
- FAIL if a stock flow breaks.
- WARNING if a feature works but is visually or behaviorally weak.
- NOT TESTED if smoke tests are not yet executed.

---

## G. Authentication

Objective:
- Verify user login and account security remain correct.

Checks:
- login by email/mobile
- Django auth backend behavior
- rate limiting and lockout behavior
- password validation and session handling
- staff/admin distinction

Evidence:
- auth tests
- login smoke tests
- lockout simulation within safe test scope

Status expectation:
- PASS if login and authentication are stable and secure.
- FAIL if unauthorized access is possible or valid users are blocked.
- WARNING if auth works but logging is weak or error flow is unclear.
- NOT TESTED if auth is not yet exercised.

---

## H. B2B

Objective:
- Validate B2B operations for wholesale buyers and distributor accounts.

Checks:
- B2B dashboard access
- buyer profile data and company context
- quote request creation
- distributor-specific workflows
- access control to B2B-only screens

Evidence:
- B2B view tests
- workflow smoke tests
- role assertions

Status expectation:
- PASS if B2B workflow is functional and isolated to correct roles.
- FAIL if B2B path is inconsistent or exposed incorrectly.
- WARNING if one B2B feature is functional but not polished or not fully protected.
- NOT TESTED if B2B flow has not yet been exercised.

---

## I. B2C

Objective:
- Validate B2C retail functionality remains intact.

Checks:
- retail account registration
- cart flow
- checkout flow
- order creation
- delivery and payment behavior for B2C accounts
- removal of B2C access to B2B-only flows

Evidence:
- B2C tests
- order creation logs
- product/cart workflow verification

Status expectation:
- PASS if B2C features continue to work without regression.
- FAIL if retail users are blocked or able to access B2B-only features.
- WARNING if retail flow is functional but incomplete.
- NOT TESTED if no B2C verification has run.

---

## J. Product Catalog

Objective:
- Verify the catalog is valid, visible, and grounded in real data.

Checks:
- category and product existence
- price values
- image and description rendering
- product capacity consistency
- catalog API responses

Evidence:
- catalog page checks
- API verification
- DB query validation

Status expectation:
- PASS if the product catalog is complete and consistent.
- FAIL if product data is incorrect or unavailable.
- WARNING if catalog works but there are missing validations or inconsistent pricing metadata.
- NOT TESTED if not exercised.

---

## K. Quote/Order Flow

Objective:
- Validate quote and order operations across B2B and B2C.

Checks:
- quote creation
- quote status transitions
- email verification flow
- admin reply flow
- order creation from approved quotes or direct orders
- status tracking and notifications

Evidence:
- admin and user action tests
- quote lifecycle checks
- status transitions

Status expectation:
- PASS if quote and order flows match expected business workflow.
- FAIL if statuses are wrong or lifecycle breaks.
- WARNING if some steps work but key validations are missing.
- NOT TESTED if no end-to-end test has been run.

---

## L. Payment Flow

Objective:
- Validate the payment workflow and transaction records.

Checks:
- Stripe config presence and safe handling
- payment intent or mock payment flow
- success/failure transitions
- transaction persistence
- COD split logic if applicable

Evidence:
- payment tests
- transaction model checks
- safe configuration review with no secret exposure

Status expectation:
- PASS if payments complete cleanly in supported modes.
- FAIL if a payment path creates invalid records or fails silently.
- WARNING if the flow is incomplete or requires manual verification.
- NOT TESTED if payment flow has not been tested in an actual environment.

---

## M. DispatchAI

Objective:
- Validate the AI assistant path and integration behavior.

Checks:
- request validation
- authenticated access
- session handling
- chat endpoint behavior
- grounding and structured responses
- admin audit logging

Evidence:
- API tests
- chat smoke tests
- audit log verification

Status expectation:
- PASS if DispatchAI returns grounded, role-appropriate responses.
- FAIL if unauthorized or invalid requests are accepted.
- WARNING if the feature works but logging or response consistency needs improvement.
- NOT TESTED if no DispatchAI interaction has been executed.

---

## N. Hindsight Recall

Objective:
- Validate memory recall behavior is real and scoped correctly.

Checks:
- recall is triggered only for valid buyers
- memory matches business context and not unrelated users
- no cross-customer leakage
- fallback behavior when service is unavailable

Evidence:
- buyer-specific recall tests
- cross-customer isolation tests
- fallback/error logs

Status expectation:
- PASS if recall works for valid buyer context and rejects invalid scope.
- FAIL if a different buyer's memory is returned.
- WARNING if recall works but is too permissive or poorly scoped.
- NOT TESTED if recall is not yet evaluated with real data.

---

## O. Groq Inference

Objective:
- Verify LLM inference path behaves correctly without fake success proofs.

Checks:
- model call path
- API key safety
- prompt construction
- response parsing and validation
- fallback or graceful handling when unconfigured

Evidence:
- request/response validation
- config masking review
- error logs for unavailable external service

Status expectation:
- PASS if the LLM path is safe, configured correctly, and handled gracefully.
- FAIL if the app pretends a live AI call succeeded without real service evidence.
- WARNING if the service is partially configured or only fallback-safe.
- NOT TESTED if Groq path has not been executed against actual infrastructure.

---

## P. Hindsight Retain

Objective:
- Validate memory retention is real and beneficial, not noise-heavy or unsafe.

Checks:
- meaningful context extraction
- retention only for relevant business context
- no retention of transactional secrets or private unrelated data
- safe fallback when retention is unavailable

Evidence:
- retained memory inspection
- buyer-specific memory logs
- action validation

Status expectation:
- PASS if the app retains only useful memory and respects safe boundaries.
- FAIL if it stores sensitive or unrelated data.
- WARNING if the mechanism is working but too permissive or noisy.
- NOT TESTED if retention has not been observed in real use.

---

## Q. Database Grounding

Objective:
- Confirm responses are grounded in real business data rather than invented details.

Checks:
- price lookup from product data
- order status from authoritative tables
- payment status from real records
- unsupported discount refusal
- no invented fulfillment claims

Evidence:
- DB-backed product and order tests
- AI response validation against real records
- refusal and grounding assertions

Status expectation:
- PASS if responses align with real database records.
- FAIL if the AI invents pricing, quantities, or actions.
- WARNING if it mostly aligns but occasionally overstates certainty.
- NOT TESTED if grounding was not evaluated against real data.

---

## R. Business Rules

Objective:
- Validate the business-rule layer enforces operational constraints.

Checks:
- MOQ logic
- price threshold checks
- discount ceilings or rules
- delivery constraints
- validation of allowed actions

Evidence:
- business-rule unit tests
- response validation against rule engine output

Status expectation:
- PASS if rule enforcement is consistent and non-bypassable.
- FAIL if policy violations are accepted.
- WARNING if rule checks exist but are incomplete.
- NOT TESTED if rules have not been systematically exercised.

---

## S. Cross-Customer Isolation

Objective:
- Ensure business memory and retrieval are customer-scoped.

Checks:
- user A cannot access user B memory
- buyer_id override attempts are ignored for non-staff users
- stored memory is not shared across accounts
- admin access is separate and controlled

Evidence:
- security tests
- authorization validation
- isolated recall/retain tests

Status expectation:
- PASS if memory cannot cross customer boundaries.
- FAIL if any customer can access another customer’s memory.
- WARNING if access is restricted only in some flows.
- NOT TESTED if isolation has not been tested.

---

## T. Security

Objective:
- Validate hardening and safe handling of secrets and customer data.

Checks:
- secret masking
- no raw API keys in templates or logs
- CSRF and authentication handling
- authorization separation
- input validation and output safety
- no raw internal prompts or internal memory leakage to normal users
- no private customer data belonging to other users exposed

Evidence:
- secure config review
- request validation tests
- replay of restricted access attempts

Status expectation:
- PASS if proper access control and secret handling are enforced.
- FAIL if any private or cross-user data is exposed.
- WARNING if a security control is present but weak or incomplete.
- NOT TESTED if security verification has not run.

---

## U. Frontend

Objective:
- Validate the user experience and UI reliability.

Checks:
- accessibility
- keyboard interactions
- button state clarity
- forms and error states
- loading states
- responsive layout
- business dashboard UX
- DispatchAI interface consistency

Evidence:
- browser smoke tests
- keyboard-only navigation checks
- layout and readability review

Status expectation:
- PASS if the interface is readable, usable, and responsive.
- FAIL if core flows break or important controls are unusable.
- WARNING if the feature works but the UI is inconsistent or difficult to use.
- NOT TESTED if no UI smoke test has been performed.

---

## V. API

Objective:
- Validate all relevant API endpoints and JSON contract behavior.

Checks:
- schema correctness
- auth requirements
- error status handling
- rate limiting behavior
- proper JSON and response contract
- admin-only endpoint hygiene

Evidence:
- endpoint-by-endpoint tests
- response code validation
- contract review for success and error responses

Status expectation:
- PASS if API behavior is deterministic and correctly protected.
- FAIL if protected APIs are accessible without auth or return unsafe data.
- WARNING if some endpoints are functional but not fully documented or validated.
- NOT TESTED if API verification has not been executed.

---

## W. End-to-End Workflow

Objective:
- Validate the full operational journey from login through quote or order to response.

Checks:
- B2B user logs in
- sees dashboard
- opens DispatchAI
- asks a business question
- Hindsight recall occurs when relevant
- business data is used
- validation or refusal occurs if needed
- response is delivered
- admin review path is possible where applicable

Evidence:
- end-to-end smoke test script
- user journey logs
- final-response validation

Status expectation:
- PASS if the whole journey works without regression.
- FAIL if a major step breaks.
- WARNING if the journey works but depends on manual intervention.
- NOT TESTED if no end-to-end route has been exercised.

---

## X. Error Handling

Objective:
- Verify graceful failure and honest user-facing messaging.

Checks:
- invalid form input
- missing data
- unauthorized access
- external-service failure
- malformed payloads
- fallback path quality

Evidence:
- negative path tests
- logs and user-visible responses

Status expectation:
- PASS if failures are handled cleanly and safely.
- FAIL if crashes, leaks, or misleading success happen.
- WARNING if errors are handled but not user-friendly.
- NOT TESTED if error paths have not been executed.

---

## Y. Performance

Objective:
- Identify risk points without changing behavior prematurely.

Checks:
- slow database queries
- repeated API calls
- Hindsight call patterns
- Groq call overhead
- frontend responsiveness
- large dataset behavior

Evidence:
- query timing
- browser timing
- request tracing

Status expectation:
- PASS if response times are healthy and no major inefficiency is found.
- FAIL if a critical path is slow enough to block workflow.
- WARNING if optimization is needed but the project still works.
- NOT TESTED if no performance measurement has been performed.

---

## Z. Final Demo

Objective:
- Validate the judge/demo scenario is straightforward, stable, and honest.

Checks:
- safe demo data only
- no fake API success claims
- persistence and recall logic are real
- unsupported discount scenario is grounded and refuses invention
- user can explain the flow in under two minutes
- no secrets or private data are exposed

Evidence:
- demo script walkthrough
- live evaluation checklist
- user-facing output review

Status expectation:
- PASS if the demo is stable and demonstrates the real innovation without manipulation.
- FAIL if the demo depends on fabricated or deceptive behavior.
- WARNING if the demo is possible but needs careful presenter guidance.
- NOT TESTED if no live demo rehearsal has happened.

---

## Proposed Test Execution Sequence

1. Environment verification
2. Dependency and import validation
3. Django system checks
4. Database migration and schema validation
5. Authentication and authorization smoke tests
6. B2C and B2B functional smoke tests
7. Product catalog validation
8. Quote and order workflow validation
9. Payment flow validation
10. DispatchAI API and session validation
11. Hindsight recall validation
12. Groq inference validation and fallback behavior
13. Hindsight retain validation
14. Database grounding checks
15. Business-rule enforcement validation
16. Cross-customer isolation tests
17. Security checks and secret masking review
18. Frontend and accessibility smoke tests
19. API contract tests
20. End-to-end demonstration flow
21. Error handling and resilience tests
22. Performance risk review
23. Demo rehearsal and final sign-off

This is the planned QA sequence. It is intentionally executed without changing application behavior before the initial inspection is complete.
