# DispatchAI Architecture & Integration Plan for CheersthePure

> **Project:** CheersthePure × DispatchAI  
> **Document:** DISPATCHAI_ARCHITECTURE.md  
> **Date:** 2026-09-29  
> **Status:** Architectural Specification & Implementation Plan  

---

## Conceptual Pipeline Overview

```
User (B2B Distributor)
        ↓
CheersthePure B2B Dashboard (/dashboard/)
        ↓
DispatchAI Chat Interface ({% include "app/dispatch_widget.html" %})
        ↓
Authenticated Buyer / Distributor ID (request.user.id)
        ↓
Hindsight Recall (Persistent Unstructured Memory)
        ↓
Existing Business & Database Data (Products, Inventory, Quotes, Orders)
        ↓
Groq Reasoning (LLM Inference Engine)
        ↓
Business-Rule Validation (MOQ, Price Floors, Region Constraints)
        ↓
Grounded Response Generation
        ↓
Hindsight Retain (Store New Insights, Behavioral Context & Negotiation History)
        ↓
UI Response (Rendered in Chat Interface / SSE Stream)
```

---

## 1. Existing CheersthePure Architecture

### System Topology
```
┌──────────────────────────────────────────────────────────────┐
│                    Client Browser                            │
│  - Django Server-Side Rendered Templates (40 HTML files)     │
│  - Vanilla JavaScript (site.js, main.js, animations.js)      │
│  - Vanilla CSS3 (style.css, site.css, animations.css)        │
└──────────────────────────────┬───────────────────────────────┘
                               │ HTTP / HTTPS (CSRF Protected)
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   Django Web Framework                       │
│  ├── core/ (Project configuration, settings.py, urls.py)     │
│  └── app/ (E-commerce app, models, views, forms, auth)       │
└──────────────────────────────┬───────────────────────────────┘
                               │ ORM
                               ▼
┌──────────────────────────────────────────────────────────────┐
│                   Relational Database                        │
│  - SQLite (Local Development) / PostgreSQL (Production)      │
│  - 13 E-Commerce & Account Models                            │
└──────────────────────────────────────────────────────────────┘
```

### Core Components Preserved
- **Authentication:** `app/backends.py` (`EmailOrMobileBackend`) allows login using email or phone number with auto-generated internal usernames and rate-limiting via `django-axes`.
- **B2B / B2C Classification:** `app/account_utils.py` automatically distinguishes retail accounts (`b2c`) from wholesale corporate accounts (`b2b`) via email domain analysis.
- **Workflow Security:** `@b2b_required` and `@b2c_required` decorators in `app/decorators.py`.
- **E-Commerce & Logistics:** Product catalog, inventory tracking, distance-based delivery calculator using Haversine formula + OpenStreetMap geocoding, Stripe card checkout, split COD (30% advance / 70% delivery), and invoice generation.

---

## 2. New DispatchAI Architecture

DispatchAI is architected as an **independent, decoupled Django application** (`dispatch/`) that interfaces with the existing codebase without mutating existing models or modifying business-critical e-commerce views.

### Architectural Component Diagram
```
┌────────────────────────────────────────────────────────────────────────┐
│                        CheersthePure Website                           │
│  (B2B Distributor Dashboard / Admin Operations Dashboard)              │
│  └─ Floating Chat Widget: static/app/dispatch_chat.js & .css           │
└───────────────────────────────────┬────────────────────────────────────┘
                                    │ AJAX POST / SSE Stream
                                    ▼
┌────────────────────────────────────────────────────────────────────────┐
│                     dispatch/ (DispatchAI App)                         │
│                                                                        │
│   ┌─────────────────────┐               ┌──────────────────────────┐   │
│   │   views.py          │ ────────────► │   agent.py               │   │
│   │   (API Controllers) │               │   (Orchestrator Pipeline)│   │
│   └─────────────────────┘               └─────────────┬────────────┘   │
│                                                       │                │
│         ┌──────────────────────┬──────────────────────┼────────────┐   │
│         ▼                      ▼                      ▼            ▼   │
│  ┌──────────────┐      ┌──────────────┐      ┌─────────────┐ ┌─────┴─┐ │
│  │config.py     │      │context_      │      │rules_       │ │models │ │
│  │(Safe Settings│      │builder.py    │      │engine.py    │ │.py    │ │
│  │& Masking)    │      │(DB Grounding)│      │(Validations)│ │(AI    │ │
│  └──────────────┘      └──────────────┘      └─────────────┘ │ State)│ │
│                                                              └───────┘ │
└──────────────────────────┬───────────────────────────┬─────────────────┘
                           │                           │
                           ▼                           ▼
        ┌──────────────────────────────────┐ ┌───────────────────┐
        │        External AI Layer         │ │ Database Layer    │
        │                                  │ │                   │
        │  ┌────────────────────────────┐  │ │ ┌───────────────┐ │
        │  │ Groq Cloud API             │  │ │ │ app/ Models   │ │
        │  │ (llama-3.3-70b-versatile)  │  │ │ │ (Read-Only    │ │
        │  └────────────────────────────┘  │ │ │  Grounding)   │ │
        │  ┌────────────────────────────┐  │ │ └───────────────┘ │
        │  │ Hindsight Service          │  │ │ ┌───────────────┐ │
        │  │ (Persistent Unstructured   │  │ │ │ dispatch/     │ │
        │  │  Memory Store)             │  │ │ │ Models (State/│ │
        │  └────────────────────────────┘  │ │ │  Audit Log)   │ │
        └──────────────────────────────────┘ │ └───────────────┘ │
                                             └───────────────────┘
```

### New DispatchAI Data Models (`dispatch/models.py`)
1. **`ConversationSession`**: Tracks multi-turn chat sessions per user with UUID identifiers and timestamps.
2. **`ConversationMessage`**: Stores user queries and AI responses with metadata and token counts.
3. **`DispatchDecision`**: Complete audit log for administrative oversight (decision type, inputs, outputs, applied rules, latency, model used).
4. **`BusinessRule`**: Dynamically configurable constraints (MOQ thresholds, price floors, discount ceilings, delivery restrictions).

---

## 3. Data Flow

```
1. User submits inquiry via UI Widget
   │
2. Request received at POST /api/dispatch/chat/ with Session Cookie + CSRF Token
   │
3. Authentication check validates user is authenticated and possesses B2B / Staff role
   │
4. dispatch/agent.py initializes pipeline with authenticated user.id
   │
5. Hindsight Recall retrieves unstructured historical memories for user.id
   │
6. context_builder.py queries app models (read-only) for catalog, inventory & order history
   │
7. System prompt constructed combining:
   Identity + Business Rules + DB Context + Recalled Memories + Conversation History
   │
8. Groq LLM processes context and returns structured candidate response
   │
9. rules_engine.py checks response against active business rules (e.g., MOQ >= 100, Price >= ₹3.00)
   │
10. Assistant message and DispatchDecision audit log saved to database
    │
11. Hindsight Retain extracts and stores new behavioral insights and negotiations
    │
12. Grounded response sent to client via JSON payload or Server-Sent Events (SSE) stream
```

---

## 4. Hindsight Memory Flow

Hindsight functions as the **unstructured, persistent long-term memory engine**. It ensures continuity across sessions without polluting the relational schema.

```
                  ┌─────────────────────────────────────┐
                  │          HINDSIGHT SERVICE          │
                  │   api.hindsight.vectorize.io        │
                  └───────────────┬─────────────────────┘
                                  │
                 ┌────────────────┴────────────────┐
                 │                                 │
                 ▼                                 ▼
      ┌────────────────────┐            ┌────────────────────┐
      │  RECALL (Pre-LLM)  │            │  RETAIN (Post-LLM) │
      └──────────┬─────────┘            └──────────▲─────────┘
                 │                                 │
[Query: Buyer message + user_id]        [Extracted conversational insights]
                 │                                 │
                 ▼                                 │
┌─────────────────────────────────┐                │
│ Recalled Memory Context:        │                │
│ - "Prefers Eco-Friendly line"   │                │
│ - "Warehouse closes at 5:00 PM" │                │
│ - "Previous deal: ₹4.50/500ml"  │                │
└────────────────┬────────────────┘                │
                 │                                 │
                 └────────► [Groq Inference] ──────┘
```

### Memory Lifecycle Operations
- **Recall (`hindsight_client.recall`):** Executed before LLM inference. Queries Hindsight using the buyer's unique key (`cheersthepure_user_<id>`) to retrieve top relevant behavioral memories.
- **Reason:** Recalled memories are injected into the LLM system prompt under `"WHAT YOU KNOW ABOUT THIS BUYER"`.
- **Retain (`hindsight_client.retain`):** Executed after generating the response. A fast utility model (`llama-3.1-8b-instant`) extracts 0–5 durable facts from the conversation turn and pushes them to Hindsight.
- **Fail-Safe Operation:** All Hindsight operations fail gracefully with logging. A network interruption to Hindsight never halts chat functionality.

---

## 5. Groq Inference Flow

```
┌────────────────────────────────────────────────────────────────────────┐
│                       Groq LLM Pipeline                                │
│                                                                        │
│  1. Prompt Assembly                                                    │
│     ├── Identity: Cheers the Pure Water B2B distribution expert        │
│     ├── Active Rules: Dynamic BusinessRule database records            │
│     ├── Live DB Context: Current products, stock counts, order history │
│     ├── Recalled Memories: Hindsight client profile context            │
│     └── History: Last 20 messages from ConversationSession             │
│                                                                        │
│  2. Model Execution (dispatch/groq_client.py)                          │
│     ├── Primary Model: llama-3.3-70b-versatile (Temp: 0.3)             │
│     ├── Fast/Extraction: llama-3.1-8b-instant (Temp: 0.1)              │
│     └── Retry Protocol: Exponential backoff on rate limits (429)       │
│                                                                        │
│  3. Response Validation & Auditing                                     │
│     ├── rules_engine.py checks prices, quantities, and delivery zones  │
│     └── DispatchDecision logs tokens, latency, model, and applied rules│
└────────────────────────────────────────────────────────────────────────┘
```

---

## 6. Database Responsibility vs. 7. Hindsight Responsibility

A strict separation of concerns prevents data duplication and keeps transactional systems accurate.

```
┌────────────────────────────────────────┬────────────────────────────────────────┐
│          RELATIONAL DATABASE           │           HINDSIGHT MEMORY             │
│        (PostgreSQL / SQLite)           │         (Vector Memory Store)          │
├────────────────────────────────────────┼────────────────────────────────────────┤
│  DETERMINISTIC / TRANSACTIONAL FACTS   │  UNSTRUCTURED / BEHAVIORAL CONTEXT     │
├────────────────────────────────────────┼────────────────────────────────────────┤
│ • Product catalog, SKUs, and capacities│ • Customer packaging preferences       │
│ • Real-time stock levels (Inventory)   │ • Preferred delivery time windows      │
│ • Confirmed Orders & Line Items        │ • Past negotiation stances & targets   │
│ • Official Quote Requests & Replies    │ • Purchasing frequency & seasonality   │
│ • Payment transaction IDs & amounts    │ • Expansion plans & business context   │
│ • User credentials, emails, & phones   │ • Special conversational commitments   │
│ • Order delivery milestone status      │ • Sentiment and historical tone        │
│ • Active BusinessRule definitions      │ • Communication language preferences   │
│ • DispatchDecision audit trail records │ • Implicit brand loyalty & competitor  │
│                                        │   mentions                             │
└────────────────────────────────────────┴────────────────────────────────────────┘
```

> **Rule of Thumb:** If it belongs on an official invoice, financial ledger, or stock audit, it lives exclusively in the **Database**. If it represents nuance, habit, negotiation history, or operational context learned through conversation, it lives in **Hindsight**.

---

## 8. Frontend-to-Agent Communication

### Widget Architecture
- **Inclusion Tag:** The chat widget is injected into existing authenticated templates using:
  ```django
  {% include "app/dispatch_widget.html" %}
  ```
- **Styling:** `app/static/app/dispatch_chat.css` provides a modern, responsive, dark glassmorphism interface that matches CheersthePure's brand identity.
- **Client Controller:** `app/static/app/dispatch_chat.js` manages message sending, session switching, auto-scrolling, typing animations, and rule violation indicators.

### Communication Channels
1. **Primary REST API (`POST /api/dispatch/chat/`):**
   - Receives JSON: `{"session_id": "<uuid>", "message": "<text>"}`
   - Responds with validated assistant message, applied business rules, and metadata.
2. **Streaming API (`GET /api/dispatch/chat/stream/<session_id>/`):**
   - Server-Sent Events (SSE) protocol delivering token-by-token typewriter rendering for low perceived latency.

---

## 9. Authentication Flow

DispatchAI reuses Django's native session authentication and does not introduce separate token complexity.

```
User signs in via existing /login/ (Email or Mobile)
                      │
                      ▼
Session cookie (`sessionid`) created in browser
                      │
                      ▼
User navigates to B2B Dashboard (/dashboard/)
                      │
                      ▼
Chat widget initialized with CSRF token from DOM
                      │
                      ▼
Fetch request sent to /api/dispatch/chat/ with credentials: 'same-origin'
                      │
                      ▼
Django Authentication Middleware resolves request.user
                      │
                      ▼
dispatch/views.py checks:
  1. Is user.is_authenticated? ──► No ──► HTTP 401 Unauthorized
  2. Is user.profile.account_type == 'b2b' OR is_staff? ──► No ──► HTTP 403 Forbidden
  3. Authorized B2B User ──► Continue to Agent Pipeline
```

---

## 10. Error Handling & Graceful Degradation

DispatchAI implements a 6-layer defense strategy ensuring the user always receives a coherent response:

| Failure Scenario | Internal Agent Action | User-Facing Outcome |
|---|---|---|
| **Hindsight Service Offline** | Catches connection error, logs warning, bypasses recall, and proceeds with DB context alone. | Agent answers query normally without personalized recall. |
| **Groq API Rate Limit (429)** | Triggers automatic exponential backoff retry (up to 3 attempts). | Brief response delay, succeeds transparently. |
| **Groq API Complete Outage** | Catches `RuntimeError`, flags decision log, and generates pre-configured fallback response. | *"I'm experiencing technical difficulties right now. Your message has been saved. Please contact cheersthepure@gmail.com."* |
| **Business Rule Violation** | `rules_engine.py` detects out-of-bounds price or quantity and appends correction note. | *"Our minimum wholesale quantity is 100 units. I have adjusted the quote accordingly."* |
| **Database Read Error** | Catches query exceptions, sets `products_unavailable=True`, instructs LLM not to quote exact stock. | Agent politely notes catalog maintenance and invites distributor to submit formal inquiry. |
| **Hindsight Retain Failure** | Swallows retention errors in background task to avoid blocking response. | User receives full response immediately; uncommitted memory logged for inspection. |

---

## 11. Implementation Files Summary

### Files Created
- [`dispatch/config.py`](file:///e:/cheers_the_pure/dispatch/config.py) — Masked configuration manager & startup health validator.
- [`dispatch/models.py`](file:///e:/cheers_the_pure/dispatch/models.py) — AI database models (`ConversationSession`, `ConversationMessage`, `DispatchDecision`, `BusinessRule`).
- [`dispatch/groq_client.py`](file:///e:/cheers_the_pure/dispatch/groq_client.py) — Groq LLM API wrapper (sync, streaming, memory extraction).
- [`dispatch/hindsight_client.py`](file:///e:/cheers_the_pure/dispatch/hindsight_client.py) — Hindsight persistent memory client (`recall`, `retain`, `search`, `forget`).
- [`dispatch/context_builder.py`](file:///e:/cheers_the_pure/dispatch/context_builder.py) — Read-only live database context assembler.
- [`dispatch/rules_engine.py`](file:///e:/cheers_the_pure/dispatch/rules_engine.py) — Business rules validator (MOQs, price floors, discounts).
- [`dispatch/prompts/system.py`](file:///e:/cheers_the_pure/dispatch/prompts/system.py) — 5-layer system prompt generator.
- [`dispatch/agent.py`](file:///e:/cheers_the_pure/dispatch/agent.py) — Pipeline orchestrator.
- [`dispatch/views.py`](file:///e:/cheers_the_pure/dispatch/views.py) — REST & SSE API endpoints.
- [`dispatch/urls.py`](file:///e:/cheers_the_pure/dispatch/urls.py) — URL routing under `/api/dispatch/`.
- [`dispatch/admin.py`](file:///e:/cheers_the_pure/dispatch/admin.py) — Admin panel registrations.
- [`dispatch/tests.py`](file:///e:/cheers_the_pure/dispatch/tests.py) — Test suite (12/12 passing).
- [`app/templates/app/dispatch_widget.html`](file:///e:/cheers_the_pure/app/templates/app/dispatch_widget.html) — Includable widget template.
- [`app/static/app/dispatch_chat.js`](file:///e:/cheers_the_pure/app/static/app/dispatch_chat.js) & [`dispatch_chat.css`](file:///e:/cheers_the_pure/app/static/app/dispatch_chat.css) — Frontend assets.

### Additive Modifications (Existing Code Preserved)
- [`core/settings.py`](file:///e:/cheers_the_pure/core/settings.py) — Added `dispatch` to `INSTALLED_APPS`, loaded `.env` via `python-dotenv`.
- [`core/urls.py`](file:///e:/cheers_the_pure/core/urls.py) — Included `dispatch.urls` under `api/dispatch/`.
- [`requirements.txt`](file:///e:/cheers_the_pure/requirements.txt) — Added `groq`, `hindsight-client`, `httpx`, and `python-dotenv`.
- [`app/templates/app/dashboard.html`](file:///e:/cheers_the_pure/app/templates/app/dashboard.html) — Injected widget include tag.
- [`app/templates/app/admin_ops_dashboard.html`](file:///e:/cheers_the_pure/app/templates/app/admin_ops_dashboard.html) — Injected widget include tag.
- [`.env.sample`](file:///e:/cheers_the_pure/.env.sample) & [`.env.example`](file:///e:/cheers_the_pure/.env.example) — Documented AI environment variables.
- [`.gitignore`](file:///e:/cheers_the_pure/.gitignore) — Added secure environment variable patterns.
