# DispatchAI Security Review

## Scope
This review covers the DispatchAI B2B customer assistant, the B2B dashboard, and the API endpoints used by authenticated users and administrators.

## Verified controls

### 1. Authentication
- All DispatchAI endpoints require a logged-in user via `@login_required` or explicit session checks.
- The app uses Django authentication with email/mobile login via `app.backends.EmailOrMobileBackend`.
- The admin workspace requires the operational admin session token and authorized email.

### 2. Authorization
- Non-B2B users are rejected with a 403 in the DispatchAI access helper.
- Only staff/superusers are allowed to access admin-only DispatchAI views and the agent activity log.
- A non-staff user is never permitted to impersonate another buyer ID.

### 3. CSRF protection
- The project keeps Django’s CSRF middleware enabled.
- The interactive DispatchAI API endpoints use JSON and validate authenticated-user access.
- Sensitive write actions remain protected by Django’s CSRF framework.

### 4. Input validation
- `agent_chat_api` validates JSON structure, message presence, message length, and request type.
- Empty messages and overlong messages return 400 responses with user-safe text.
- Request bodies that are not valid JSON are rejected.

### 5. Rate limiting
- The API uses a per-user cache-based rate limiter (`is_rate_limited`) to cap requests per minute.
- When exceeded, the endpoint returns HTTP 429 with a clear user message.

### 6. API error handling
- The backend catches invalid JSON, authentication errors, and unexpected execution failures.
- User-facing responses avoid stack traces and return simple messages like “DispatchAI is temporarily unavailable. Please try again.”
- Technical errors are logged server-side instead of exposed to end users.

### 7. Secret management
- Sensitive credentials are read from environment variables and masked in any configuration reporting.
- Secret-bearing values are never returned in the API response payload.
- Hindsight and Groq configuration metadata are filtered to avoid raw credential leakage.

### 8. SQL injection protection
- The application primarily uses Django ORM with parameterized queries.
- The project avoids direct string concatenation for database queries in the dashboard and DispatchAI services.
- Database access follows Django query objects and prebuilt filters.

### 9. XSS protection
- Templates render user-provided values with Django autoescaping.
- The dashboard avoids unsafe raw HTML insertion.
- The JSON API returns structured data rather than arbitrary HTML.

### 10. Secure session handling
- Django session middleware is enabled and the app uses the standard secure session primitives.
- Session-based ownership is used to derive the active buyer identity for authenticated users.

### 11. Buyer ID authorization
- The backend currently derives the buyer identity from the authenticated session and never trusts a caller-provided buyer_id when the caller is not staff.
- Staff users may request a buyer override, but the API still requires valid authorized context.
- A B2B customer cannot send another customer’s buyer_id and retrieve that customer’s memory or account context.

### 12. Sensitive data protection
- Responses do not expose raw database objects, hidden prompts, or secret credentials.
- Business memory is shown only in user-facing labels such as “Remembered context” and not as raw Hindsight internals.
- The admin activity log is restricted to privileged users and does not expose secrets.

## Important safeguards

- Raw Hindsight memory is not exposed casually in the normal user dashboard.
- The admin area allows operational management but is restricted to authorized staff.
- When external services fail, the app returns a generic fallback message rather than crashing.

## Security posture
Current status: Verified in code and protected by configuration, ownership checks, and Django’s built-in security primitives. The remaining risk is operational: production deployments should ensure environment variables are set and the admin workspace is restricted to trusted staff only.
