# CheersthePure — Complete Technical Audit & Architecture Review

> **Audit Date:** 2026-09-29  
> **Project Root:** `e:\cheers_the_pure`  
> **Application:** CheersthePure Water (B2B/B2C E-Commerce & Distribution)  
> **Auditor:** Antigravity AI  

---

## 1. Current Programming Language & Framework

- **Language:** Python 3.12+ (x64)
- **Web Framework:** Django 5.x / 6.x architecture (`core` project and `app` application)
- **Web Server Interface:** WSGI (`core.wsgi:application`) and ASGI (`core.asgi:application`), with `gunicorn` for production deployment.

---

## 2. Existing Frontend Structure

- **Architecture:** Server-Side Rendered (SSR) Django Template system with HTML5, vanilla JavaScript, and modern CSS3 (custom CSS variables and glassmorphism styling).
- **Template Layout:**
  - `app/templates/app/base.html` — Main layout containing navbar, notification toasts, cart badge, and responsive footer.
  - `app/templates/app/` — 37 primary templates for store pages, cart, checkout, tracking, user dashboard, quote status, and admin ops dashboard.
  - `app/templates/registration/` — 4 standard templates for password reset workflow (forms, confirmation, emails).
- **Static Assets (`app/static/app/`):**
  - Styles: `style.css` (18.9 KB), `site.css` (22.4 KB), `animations.css` (8.8 KB), `dispatch_chat.css` (UI styles).
  - Scripts: `site.js` (8 KB), `main.js` (4.6 KB), `animations.js` (9.6 KB), `dispatch_chat.js` (widget client).
  - Media: Product visual assets (`250ml.jpg`, `500ml.jpg`, `1ltr.jpg`, `2ltr.jpg`, `cheers logo.jpeg`, `about-hero.jpeg`, showcase videos).

---

## 3. Existing Backend Structure

- **Project Core (`core/`):**
  - `settings.py` — Database routing, security headers, authentication backends, session cookies, rate-limiting, payment gateways, and AI configs.
  - `urls.py` — Root router directing to custom admin access (`portal-hq-access/`), main application routes (`app.urls`), and AI API endpoints (`api/dispatch/`).
  - `asgi.py` / `wsgi.py` — Server entrypoints.
- **Application (`app/`):**
  - `views.py` — Complete business logic for B2B quote management, B2C cart/checkout, geocoding delivery calculators, OTP password recovery, and admin management.
  - `models.py` — 13 database models mapped to SQLite/PostgreSQL.
  - `forms.py` — Form validation without mandatory usernames (email/mobile-driven auth).
  - `backends.py` — Custom dual-identifier authentication (`EmailOrMobileBackend`).
  - `account_utils.py` — Automatic B2B vs B2C classification based on public vs corporate email domains, plus domain name inference.
  - `decorators.py` — Role enforcement decorators (`@b2c_required`, `@b2b_required`).
  - `stripe_utils.py` — Checkout session creation, payment intent verification, and webhook receivers.
  - `email_utils.py` — HTML and plain text dispatch for order invoices, shipping notifications, and quote delivery notices.
  - `invoice_utils.py` — Cryptographic 64-character token generator for invoice URLs.

---

## 4. Existing Database & Database Models

### Core E-Commerce & User Models (13 Models in `app`)

| Model | Relationships | Key Fields / Responsibilities |
|---|---|---|
| **Category** | 1:N with `Product` | Product catalog hierarchy (`name`, `description`). |
| **Product** | FK to `Category`, 1:1 with `Inventory` | Capacities (`250 ml`, `500 ml`, `1000 ml`, `2 litres`), unit price, image, featured flag. |
| **Inventory** | 1:1 with `Product` | Stock quantity (`quantity_in_stock`), low stock threshold (`reorder_level`), restock dates. |
| **UserProfile** | 1:1 with `User` | `role` (customer, distributor, partner, staff), `account_type` (`b2b` vs `b2c`), `company_name`, `industry`, `phone`. |
| **Cart** | 1:1 with `User`, 1:N with `CartItem` | Active B2C basket, total quantity, and dynamic price calculation. |
| **CartItem** | FK to `Cart`, FK to `Product` | Quantities in active cart with inventory threshold validation. |
| **Order** | FK to `User` (or guest), 1:N with `OrderItem`, 1:1 with `OrderPayment` | Retail order record, delivery coordinates/fee, COD 30% advance split, milestone tracking, 64-char `invoice_token`. |
| **OrderItem** | FK to `Order`, FK to `Product` | Snapshotted price, product name, and purchased quantity. |
| **OrderPayment** | 1:1 with `Order` | Stripe / mock payment transaction record, status (`pending`, `success`, `failed`, `refunded`). |
| **QuoteRequest** | FK to `User`, FK to `Product`, 1:1 with `EmailVerificationToken`, 1:N with `QuoteReply` | Bulk wholesale inquiries, business details, verification status, workflow state (`pending`, `contacted`, `quoted`, `completed`). |
| **EmailVerificationToken** | 1:1 with `QuoteRequest` | UUID verification tokens for unauthenticated B2B quote inquiries with 24-hour expiration. |
| **QuoteReply** | FK to `QuoteRequest` | Admin-provided wholesale pricing per unit, delivery estimates, custom notes. |
| **PaymentTransaction** | FK to `QuoteRequest` | Online payments completed for approved B2B wholesale quotes. |
| **Notification** | Indexed by email | In-app notification queue for quotes, verification, and order updates. |
| **ContactMessage** & **Testimonial** | Standalone | Customer inquiries and social proof reviews. |

---

## 5. Existing Authentication System

- **Dual-Identifier Login:** Powered by `EmailOrMobileBackend` (`app/backends.py`), allowing users to sign in with either their email address or registered mobile number without entering a username.
- **Username Abstraction:** Internally auto-generated unique usernames (`_auto_username`) keeping the UI modern and clean.
- **Automated Account Classification:** On registration, users with personal email domains (`gmail.com`, `yahoo.com`, `outlook.com`, etc.) are tagged as `b2c` (`customer`), while corporate domains are tagged as `b2b` (`distributor`).
- **Security & Rate-Limiting:** Integrated with `django-axes` (5 failed attempts trigger a 1-hour IP lockout).
- **Password Reset:** Supports email reset links (Django SMTP) and SMS OTP 6-digit verification codes.
- **Owner Access:** Hardcoded emergency admin management endpoint at `/secret-management/`.

---

## 6. Existing Product / Catalog System

- Categorized bottle inventory supporting four distinct sizes:
  - 250 ml (Compact / Sport)
  - 500 ml (Standard Hydration)
  - 1000 ml / 1 Ltr (Premium Professional)
  - 2 litres (High-Capacity Hospitality / Office)
- Dynamic inventory checks during cart updates and checkout processing to prevent overselling.

---

## 7. Existing B2B vs B2C Functionality

- **B2C Retail:** Direct add-to-cart, cart quantity editing, distance-based delivery calculator, instant online card payment or COD with 30% advance deposit, automated invoice generation, and milestone tracking (`confirmed` → `processing` → `shipped` → `delivered`).
- **B2B Wholesale:** Direct quotation workflow for bulk volumes, negotiation pricing, business profile enrichment, email verification, and tokenized quote status review.
- **Access Control:** Enforced at view level using `@b2c_required` and `@b2b_required` decorators.

---

## 8. Existing Order & Quote Workflow

```
[B2C User] ──► Browse Catalog ──► Add to Cart ──► Checkout (Geocoding Delivery Fee) ──► Payment (Stripe/COD) ──► Order Confirmed ──► Invoice Generated ──► Delivery Milestones

[B2B User] ──► Submit Quote (/order/) ──► Email Verification ──► Admin Review (/admin-ops/) ──► Wholesale Quote Reply ──► Distributor Review & Payment ──► Bulk Fulfillment
```

---

## 9. Existing Payment Functionality

- **Stripe Checkout:** Full card checkout sessions for both B2C retail orders and B2B approved quotes.
- **Mock Gateway:** Built-in development fallback gateway when Stripe credentials are in sandbox/test mode.
- **Split Cash-on-Delivery (COD):** 30% online advance deposit to confirm dispatch + 70% cash balance due on delivery.
- **Webhook Integration:** `/webhook/stripe/` listener for `charge.succeeded` and payment fulfillment.

---

## 10. Existing API Endpoints

### Store & Utility APIs
- `GET /api/products/` — Full product catalog JSON.
- `GET /api/products/<pk>/` — Single product JSON.
- `GET /api/categories/` — Categories list.
- `GET /api/testimonials/` — Customer testimonials.
- `GET /api/cart/count/` — Current user's cart item count and subtotal.
- `POST /api/delivery-fee/` — OpenStreetMap Nominatim geocoding + Haversine distance fee calculation.
- `GET /api/orders/<id>/status/` — Real-time order delivery milestone tracking.

### Admin Operations APIs
- `POST /api/orders/<id>/update-status/` — Update order tracking state.
- `POST /api/quotes/<id>/reply/` — Dispatch wholesale quote price and terms.

### DispatchAI Integration APIs
- `POST /api/dispatch/chat/` — AI agent chat endpoint.
- `GET /api/dispatch/chat/stream/<session_id>/` — Server-Sent Events (SSE) streaming endpoint.
- `GET /api/dispatch/sessions/` & `GET /api/dispatch/sessions/<id>/` — Session state & conversation history.
- `GET /api/dispatch/decisions/` — Admin AI decision audit logs.
- `GET /api/dispatch/rules/` & `POST /api/dispatch/rules/` — Configurable business rules engine.

---

## 11. Existing Environment Configuration

- Configured via `python-dotenv` from `.env` and documented in `.env.sample` and `.env.example`:
  - `DATABASE_URL` — PostgreSQL connection string.
  - `STRIPE_PUBLIC_KEY`, `STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET` — Stripe API keys.
  - `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD` — SMTP settings.
  - `GROQ_API_KEY` — Groq Cloud LLM API key.
  - `HINDSIGHT_API_KEY`, `HINDSIGHT_URL`, `HINDSIGHT_APP_ID` — Hindsight persistent memory service.
  - `WAREHOUSE_LAT`, `WAREHOUSE_LON` — Logistics coordinates (Hyderabad HQ).

---

## 12. Existing Deployment Configuration

- `gunicorn` WSGI production server.
- Production security flags configured in `core/settings.py` (`SECURE_SSL_REDIRECT`, `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE`, `SECURE_HSTS_SECONDS`).
- SQLite default for local zero-dependency testing, PostgreSQL-ready via `psycopg2-binary`.

---

## 13. Existing Git Configuration

- `.gitignore` strictly protects `.env`, `.env.*`, database journals, Python virtual environments, and media caches from being committed.

---

## 14. What Can Be Reused vs What Must Be Modified vs Added

### What Can Be Reused (100% Preserved)
- All 13 existing database models in `app/models.py`.
- All 13 existing database migrations (`0001` through `0013`).
- All existing auth backends, login flows, forms, and validation rules.
- Existing Stripe payment processing, mock payment, and COD calculations.
- Existing email notification dispatches and invoice generation.
- All 40 existing Django templates and styling.

### What Must Be Modified (Additive Only)
- `core/settings.py` — Register `dispatch` in `INSTALLED_APPS` and load environment variables safely.
- `core/urls.py` — Route `/api/dispatch/` to the AI agent.
- `requirements.txt` — Include `groq`, `hindsight-client`, `httpx`, and `python-dotenv`.
- `dashboard.html` / `admin_ops_dashboard.html` — Include the AI chat widget tag.

### What Is Added for DispatchAI
- `dispatch/` app with models: `ConversationSession`, `ConversationMessage`, `DispatchDecision`, `BusinessRule`.
- `dispatch/groq_client.py` — Groq inference client.
- `dispatch/hindsight_client.py` — Persistent memory recall & retain client.
- `dispatch/context_builder.py` — Grounding engine assembling live DB products, inventory, and order history into LLM prompts.
- `dispatch/rules_engine.py` — Business constraint validator (MOQs, price floors, allowed regions).
- `dispatch/config.py` — Masked secret manager and startup health validator.
- `dispatch_chat.js` & `dispatch_chat.css` — Non-intrusive floating chat widget.

---

## 15. Potential Technical Conflicts & Resolutions

1. **Secret Exposure Risk:** Handled by `dispatch/config.py`, which masks all credentials (`gsk_...***`) before logging or transmission.
2. **Deterministic Data Duplication:** Transactional records (orders, payments, inventory) remain strictly in PostgreSQL/SQLite; Hindsight is used exclusively for behavioral context, client preferences, and negotiation memory.
3. **Database Write Safety:** DispatchAI interacts with existing application models in **read-only mode**, preventing data corruption.
4. **Third-Party Service Downtime:** Designed with graceful fallbacks; if Groq or Hindsight are unreachable, DispatchAI returns actionable fallback instructions without crashing the host web server.

---

## 16. Summary

1. **Current Stack:** Python 3.12, Django 5/6, SQLite/PostgreSQL, Stripe, Vanilla CSS/JS, Groq SDK, Hindsight Client.
2. **Important Existing Files:**
   - `core/settings.py`, `core/urls.py`
   - `app/models.py`, `app/views.py`, `app/urls.py`
   - `app/backends.py`, `app/account_utils.py`
   - `app/templates/app/dashboard.html`
3. **Recommended Integration Points:**
   - Isolated `dispatch` Django app mounted at `/api/dispatch/`.
   - Frontend widget injected via `{% include "app/dispatch_widget.html" %}`.
4. **Files That Should NOT Be Modified:**
   - `app/models.py`, `app/views.py`, `app/backends.py`, `app/invoice_utils.py`, `app/stripe_utils.py`
   - `app/migrations/*`
5. **Risks & Conflicts:** Fully mitigated through decoupled architecture, read-only database access for the AI agent, and masked configuration helpers.
