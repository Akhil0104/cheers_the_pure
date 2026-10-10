# SaaSsum AI — Current Repository State

**Audit date:** 2026-10-10  
**Scope:** Read-only audit for the SaaSsum AI website-builder integration  
**Repository:** `Akhil0104/cheers_the_pure`  

This document records implementation verified from source files. Statements marked
**documented** come from project documentation and were not treated as proof of runtime
behavior. No `.env` values, credentials, database rows, payment data, or personal information
were read or included.

## 1. Architecture and framework versions

### Verified

- The project is a Django application launched by [`manage.py`](../manage.py), with
  `DJANGO_SETTINGS_MODULE=core.settings`.
- [`core/settings.py`](../core/settings.py) configures Django apps `app`, `dispatch`, and
  `ai_builder`, Django templates under `app/templates`, static files under
  `app/static`, media under `media`, and SQLite at `db.sqlite3`.
- [`requirements.txt`](../requirements.txt) declares Django `>=5.0,<7.0`, Pydantic `>=2.7,<3.0`,
  Groq `>=0.9.0`, `hindsight-client>=0.10.0`, Stripe `>=7.0.0`, Pillow, Django-Axes,
  Django-OTP/two-factor-auth, HTTP clients, and Gunicorn. Exact installed versions were not
  verified because the available virtual-environment launchers are broken.
- The frontend is Django-template HTML, CSS, and browser JavaScript; there is no separate
  Node/Tailwind build system. Existing application assets are in
  [`app/static/app/`](../app/static/app/), and builder assets are in
  [`ai_builder/static/ai_builder/`](../ai_builder/static/ai_builder/).
- The repository contains both `env/` and `venv/`. Their Python launchers reference the missing
  executable `C:\Users\Dell\AppData\Local\Python\pythoncore-3.14-64\python.exe`.

### Not verified

- Production deployment topology, external database configuration, installed package versions,
  live Groq/Hindsight availability, Stripe account configuration, and production host behavior.
  The settings file currently selects SQLite regardless of the `DATABASE_URL` name documented
  elsewhere.

## 2. Existing features verified in source

- Public storefront routes: home, products, product detail, categories, category detail, about,
  and contact (`app/urls.py`, `app/views.py`).
- Catalog and content models: `Category`, `Product`, `Testimonial`, and `ContactMessage`
  ([`app/models.py`](../app/models.py)).
- Authentication supports email/mobile login, registration without exposing a username, email
  verification, password reset by email/SMS OTP, Django-Axes lockout, role/account-type
  handling, and staff/admin access (`app/forms.py`, `app/backends.py`, `app/views.py`,
  `core/settings.py`).
- B2B quote lifecycle includes quote submission, verification, status updates, replies, client
  status access, and payment processing (`QuoteRequest`, `QuoteReply`, `EmailVerificationToken`,
  `PaymentTransaction` in [`app/models.py`](../app/models.py); quote routes in
  [`app/urls.py`](../app/urls.py)).
- B2C commerce includes session/user cart, cart item updates, delivery-fee calculation,
  checkout, order creation, order history/details/tracking, invoice access, and payment
  status routes (`Cart`, `CartItem`, `Order`, `OrderItem`, `OrderPayment`, `Inventory`).
- Admin operations include product/category CRUD, quote/contact management, order status
  updates, user role updates, and an operations dashboard.
- Static UI includes storefront styles/scripts, DispatchAI chat widget assets, product/about
  images, and media video assets. Templates include storefront, dashboards, cart/checkout,
  payment, account, DispatchAI demo, and builder-related surfaces.

## 3. Product, inventory, quote, order, payment, and user workflows

### Product and inventory

- `Product` stores category, name, bottle capacity, decimal price, feature flag, description,
  image/image URL, and creation time.
- `Inventory` is a one-to-one product record with stock quantity, reorder level, and restock
  timestamps.
- Product/category forms and admin routes support create, edit, delete, and list operations.
- DispatchAI catalog services read product pricing and inventory from Django ORM records rather
  than allowing the model to invent authoritative values.

### Quote and B2B workflow

1. A user opens `/order/` (optionally for a product).
2. The application validates and persists a `QuoteRequest`.
3. An email-verification token is created and the user can view quote status using a token.
4. Staff can inspect, reply to, update, or delete quotes.
5. A quote can proceed through Stripe checkout or the configured mock/development path.
6. Payment records and notifications are persisted where the relevant path succeeds.

The exact validation and notification behavior is implemented in
[`app/views.py`](../app/views.py) and [`app/models.py`](../app/models.py); browser-only
confirmation should not be treated as persistence proof without runtime testing.

### B2C order workflow

1. A user adds products to a cart.
2. Cart contents and delivery distance/fee are calculated.
3. Checkout creates an `Order` and related `OrderItem` rows.
4. The user pays through Stripe when configured, or the explicit mock path in development.
5. The user can view order details, history, tracking, status, and an invoice token URL.
6. Staff can update operational order status.

### User workflow

`UserProfile` adds role, account type, company, phone, and buyer-related information to Django
auth users. B2B/distributor and B2C/customer paths are separated in dashboard and DispatchAI
authorization checks. Admin access is implemented both through Django staff checks and the
restricted operations dashboard.

## 4. DispatchAI, Groq, and Hindsight integration points

### DispatchAI

- Root routes in [`core/urls.py`](../core/urls.py) expose the agent endpoint and memory demo;
  [`dispatch/urls.py`](../dispatch/urls.py) exposes sessions, chat/streaming, decisions, and
  business-rule endpoints.
- [`dispatch/views.py`](../dispatch/views.py) validates request method/authentication,
  restricts access to B2B/staff users, applies a 30-per-minute rate limit, and serializes
  agent responses.
- [`dispatch/services/dispatch_ai_service.py`](../dispatch/services/dispatch_ai_service.py)
  orchestrates identity validation, database context, memory recall, Groq inference, response
  rules, decision logging, and memory retention.
- [`dispatch/models.py`](../dispatch/models.py) stores conversation sessions/messages,
  dispatch decisions, business rules, and agent action logs.
- [`dispatch/tools.py`](../dispatch/tools.py) and [`dispatch/services/catalog_service.py`](../dispatch/services/catalog_service.py)
  provide product, inventory, quote, order, payment, and delivery context.

### Groq

- [`dispatch/groq_client.py`](../dispatch/groq_client.py) provides lazy client creation,
  retrying chat, streaming chat, and memory extraction.
- [`dispatch/config.py`](../dispatch/config.py) reads configuration from Django settings,
  masks secrets for diagnostics, and reports configuration status without returning raw keys.
- The SaaSsum builder calls the shared Groq generation/refinement path from
  [`ai_builder/views.py`](../ai_builder/views.py), with strict schema validation before saving.

### Hindsight

- [`dispatch/services/hindsight_service.py`](../dispatch/services/hindsight_service.py)
  provides recall, retain, search, forget, availability checks, buyer-ID normalization,
  namespacing, and HTTP error handling.
- Root-level [`services/hindsight_service.py`](../services/hindsight_service.py) is a
  compatibility proxy to the DispatchAI implementation; the root `services/` package is not a
  second implementation.
- [`dispatch/context_builder.py`](../dispatch/context_builder.py) injects recalled memories
  into agent context. [`dispatch/memory_extractor.py`](../dispatch/memory_extractor.py)
  filters trivial content and extracts useful B2B context.
- The documented strategy in [`MEMORY_STRATEGY.md`](../MEMORY_STRATEGY.md) separates
  transactional truth in SQL from contextual preferences in Hindsight. Hindsight outages are
  designed to degrade to empty/non-fatal memory results, but live availability was not tested.

## 5. Existing tests and safe commands

### Test inventory

- [`app/tests.py`](../app/tests.py): authentication, quote/B2B dashboard, payment/order, and
  application workflows.
- [`dispatch/tests.py`](../dispatch/tests.py): configuration, models, authorization, catalog
  grounding, Hindsight, memory extraction, agent APIs, tools, dashboard, and demo flows.
- [`ai_builder/tests.py`](../ai_builder/tests.py): schema constraints, owner isolation,
  generation/refinement, publishing, inquiry persistence, rate limiting, and service failures.

### Safe commands

Run from the repository root after activating a working Python environment:

```powershell
python manage.py check
python manage.py test --verbosity 1
python manage.py test ai_builder app dispatch --verbosity 1
python manage.py migrate --plan
python -m pip check
```

`manage.py test` creates and destroys a separate test database; it does not use application
database rows. `migrate --plan` is read-only. Do not print `.env`, database dumps, or
unmasked configuration while diagnosing failures.

### Audit execution result

- `python manage.py check` and the targeted test command could not import Django because the
  default interpreter has no Django installed.
- `env\Scripts\python.exe` and `venv\Scripts\python.exe` both failed before startup because
  their launchers point to the missing Python executable described in section 1.
- Therefore, the source-reported result in [`TESTING.md`](../TESTING.md) (“79 tests, OK”) is
  historical documentation, not a result independently reproduced in this audit.

## 6. SaaSsum/website-builder work already present

The repository already contains a substantial SaaSsum implementation:

- [`ai_builder/schemas.py`](../ai_builder/schemas.py) defines a strict Pydantic v2
  `SiteSchema` with allowlisted themes, discriminated section types, bounded content,
  URL/content safety rules, unique section IDs, and product-price provenance rules.
- [`ai_builder/models.py`](../ai_builder/models.py) defines `CreatedWebsite`, owned by a
  Django user, storing the prompt, site/brand metadata, validated JSON schema, publication
  state, share token, and timestamps.
- [`ai_builder/views.py`](../ai_builder/views.py) implements authenticated workspace access,
  owned site list/save/load/update, Groq generation, one-section refinement, publishing,
  public read-only share links, and B2B inquiry submission.
- [`ai_builder/templates/ai_builder/`](../ai_builder/templates/ai_builder/) contains the
  workspace and shared-site templates. [`ai_builder/static/ai_builder/`](../ai_builder/static/ai_builder/)
  contains the renderer, builder application JavaScript, and builder CSS.
- `app/urls.py` wires `/builder/`, site CRUD/publish APIs, generation/refinement APIs, and both
  `/api/site-builder/inquiry/` and the trusted `/api/v1/inquiry/submit/` endpoint.
- [`docs/BUILDER_WORKSPACE.md`](./BUILDER_WORKSPACE.md) documents the current workflow,
  owner scoping, CSRF/session behavior, rate limiting, export boundary, and manual checks.
- [`docs/SITE_SCHEMA.md`](./SITE_SCHEMA.md) documents the schema contract and product trust
  boundary. The existing builder intentionally does not claim unverified water quality,
  certification, laboratory, or pricing facts.

## 7. Missing requirements, risks, and dependencies

### Environment and reproducibility

- Repair or recreate a Python virtual environment; both checked-in environments are stale and
  cannot run Django.
- Pin or lock resolved dependency versions for repeatable challenge evaluation. The current
  requirements use broad ranges.
- Re-run system checks, migrations plan, targeted tests, and the full suite after environment
  repair.

### Configuration and deployment

- Confirm whether production should use PostgreSQL as described in some architecture documents;
  current settings explicitly use SQLite.
- Remove or fail fast on insecure development defaults (`SECRET_KEY`, admin password, Stripe
  placeholders) in production configuration.
- Verify `ALLOWED_HOSTS`, HTTPS/CSRF settings, cache backend, email, Stripe webhook, Groq, and
  Hindsight configuration in a secret-safe environment.

### Integration risks

- The builder depends on Groq for generation/refinement and returns service errors when it is
  unavailable; a production UX/observability decision is still needed.
- Inquiry rate limiting uses Django cache; the builder documentation notes that the local
  default is process-local and requires a shared backend in multi-worker deployments.
- Some legacy storefront/payment/contact endpoints are marked `csrf_exempt` in
  [`app/views.py`](../app/views.py); these should be reviewed before expanding integrations.
- Existing documentation and code have multiple overlapping DispatchAI service entry points
  (root proxies and `dispatch/` implementations), increasing maintenance and import-path risk.
- Builder export is intentionally static/read-only: generation, saves, publishing, and inquiry
  submission still require the live Django backend; remote images/fonts require network access.

### Product and challenge scope

- The builder exists and is wired to CheersThePure’s quote workflow, but challenge acceptance
  still needs end-to-end browser verification once dependencies run.
- No separate SaaSsum billing/subscription, tenant isolation model, custom-domain publishing,
  analytics, or production deployment workflow was verified in source. These are requirements
  only if the challenge brief expects them.

## 8. Phased implementation plan for remaining prompts

### Phase 1 — Environment and baseline

1. Recreate a supported virtual environment from [`requirements.txt`](../requirements.txt).
2. Run `check`, migration plan, targeted builder tests, DispatchAI/app tests, then the full
   suite.
3. Record actual package versions and resolve any baseline failures without changing behavior.

### Phase 2 — SaaSsum builder acceptance

1. Execute the manual checks in [`docs/BUILDER_WORKSPACE.md`](./BUILDER_WORKSPACE.md):
   empty state, generation, mobile preview, inline edit/save, section refinement, publish/share,
   export, and inquiry validation.
2. Confirm owner isolation, signed-out read-only sharing, CSRF/session enforcement, and no
   prompt/account leakage.
3. Add only focused regression tests for any observed gap.

### Phase 3 — Production integration hardening

1. Decide and implement the production database/cache/deployment configuration.
2. Validate secret handling, Stripe webhook behavior, email/SMS delivery, HTTPS, host
   restrictions, and rate limits in a staging environment.
3. Review legacy CSRF exemptions and consolidate duplicate service proxies where safe.

### Phase 4 — Challenge-ready product polish

1. Confirm the challenge’s required SaaSsum feature set (tenancy, custom domains, billing,
   analytics, or export requirements) against the existing builder boundary.
2. Add missing requirements with schema-first validation and trusted server-side catalog
   enrichment.
3. Run the full test suite and browser smoke tests, then update the builder and deployment
   documentation with reproducible commands and observed results.

## Audit conclusion

The repository is not an empty integration target: it already contains a working-shaped
CheersThePure commerce application, a substantial DispatchAI/Groq/Hindsight stack, and an
implemented SaaSsum schema-driven website builder. The immediate blocker is reproducible
execution—the available Python environments are invalid—followed by runtime/browser
verification and production configuration decisions. No application code was changed during
this audit; only this state document was added.
