# SaaSsum B2B Inquiry API

## Endpoint

`POST /api/v1/inquiry/submit/`

The former builder path `/api/site-builder/inquiry/` remains a compatibility alias. New clients
should use the versioned route. The builder reads its same-origin path from the trusted Django
setting `SAASSUM_INQUIRY_API_URL`; `SiteSchema` cannot supply or override the destination.
The default is `/api/v1/inquiry/submit/`; set the environment variable only when the deployed
application is mounted under a different same-origin path. No migration is needed for the URL
setting. Migration `app.0016_quoterequest_inquiry_idempotency_key` adds the nullable unique key
used to make request retries safe; apply it with `python manage.py migrate`.

## Security and workflow

- Same-origin Django session authentication is required. The account must be B2B or staff.
- Django's global `CsrfViewMiddleware` remains enabled. Browser requests include the rendered
  CSRF token; there is no CORS wildcard or CSRF exemption.
- A UUID `Idempotency-Key` header is required. Replaying the same key and same payload returns
  the original quote ID without creating another quote, verification token, or email. Reusing
  the key with different data returns `409`.
- Requests are limited to five per authenticated user/IP per ten minutes. Use a shared cache
  backend for consistent throttling across production workers.
- The API calls `app.quote_services.create_quote_request_workflow`, also used by the existing
  `/order/` HTML view. That service verifies that `pending` is a supported `QuoteRequest` status,
  persists the actual model, creates `EmailVerificationToken`, and queues the existing
  verification email. The request is not an order and does not reserve stock, apply discounts,
  or create a payment.

## Request

Headers:

```http
Content-Type: application/json
X-CSRFToken: <Django CSRF token>
Idempotency-Key: <UUID for this form submission and its retries>
```

Body; `size` or `capacity` is accepted. If both are supplied, they must match.

```json
{
  "name": "SaaSsum Integration QA",
  "email": "integration.qa@business.example",
  "company": "Integration QA",
  "capacity": "500 ml",
  "quantity": 250,
  "details": "Development verification inquiry"
}
```

Capacities must be one of `250 ml`, `500 ml`, `1000 ml`, or `2 litres`. Quantity must be an
integer from 1 through 1,000,000. Text is trimmed and length-limited; unknown fields are rejected.

## Responses

New request (`201 Created`):

```json
{
  "success": true,
  "quote_id": 123,
  "message": "Quote request received",
  "status": "pending"
}
```

Idempotent replay (`200 OK`) returns the same body and existing `quote_id`.

Errors use `{ "ok": false, "error": "..." }`: `400` invalid body/fields/key/content type,
`403` authentication or B2B authorization failure (CSRF failures are rejected by Django's
middleware), `405` unsupported method, `409` idempotency conflict, `429` rate limit,
`503` rate-limit service unavailable, and `500` persistence failure. Responses contain no
exception trace or customer record details.

## Verification checklist

1. Sign in as a B2B account and submit the builder quote form. Confirm the browser sends JSON,
   the CSRF header, and one UUID idempotency key; the form disables while submitting.
2. Confirm the response is `201`, displays the returned quote ID, and describes a pending
   inquiry rather than an order.
3. Inspect the actual `QuoteRequest` in Django admin or the B2B dashboard. Check the returned
   primary key, `pending` status, `email_verified=False`, and matching `EmailVerificationToken`.
4. Retry with the same idempotency key and identical payload. Confirm the same ID returns and
   no second `QuoteRequest` or verification email is created.
5. Try an invalid email/capacity/quantity, an anonymous session, and a B2C account. Confirm the
   appropriate error and that no quote record is created.
6. Confirm no payment, inventory deduction, discount, or `Order` is created by an inquiry.