# CheersthePure & DispatchAI — Database & Memory Architecture

> **Document:** DATABASE_ARCHITECTURE.md  
> **Project:** CheersthePure (Django E-Commerce & B2B Distribution Platform)  
> **Integrated Component:** DispatchAI Agent  
> **Status:** Production Data Architecture & Storage Separation Specification  

---

## 1. Executive Summary & Core Philosophy

CheersthePure operates on a **hybrid data architecture**:
1. **Relational Database (SQL / PostgreSQL / SQLite):** The authoritative, ACID-compliant source of truth for all **deterministic, transactional, legal, and operational business data**.
2. **Hindsight Persistent Vector Memory:** The long-term contextual engine for **unstructured conversational memory, buyer preferences, negotiation context, and behavioral patterns**.

> ⚠️ **Strict Non-Duplication Rule:** Transactional entities (orders, invoices, inventory counts, payment IDs) are NEVER duplicated into Hindsight. Hindsight references the canonical `buyer_id` / `distributor_id` as a foreign memory key and stores only what cannot be represented in relational tables.

---

## 2. Comprehensive Model Mapping & Identity Schema

### A. Customer & Buyer Identity Schema

DispatchAI identifies every customer and distributor uniquely using a stable identity format.

```
Django User (ID: 42, Email: buyer@apexbev.com)
  └── 1:1 UserProfile
        ├── buyer_id: "DIST-00042" (Stable Unique Buyer Identity)
        ├── account_type: "b2b"
        ├── role: "distributor"
        ├── company_name: "Apex Beverage Distributors"
        ├── industry: "Hospitality & Event Supply"
        ├── phone: "+91 9876543210"
        ├── address: "Plot 14, Gachibowli Industrial Area"
        ├── city: "Hyderabad"
        ├── state: "Telangana"
        ├── postal_code: "500032"
        └── gstin: "36AAAAA0000A1Z5"
```

| Entity | Model Name | Primary Identifier | Fields & Attributes Supported |
|---|---|---|---|
| **User Account** | `django.contrib.auth.models.User` | `id`, `username`, `email` | Email, hashed password, staff flags, active status. |
| **Buyer Profile & Identity** | `app.models.UserProfile` | `buyer_id` (`DIST-00042` / `CUST-00010`) | `company_name`, `account_type` (`b2b`/`b2c`), `role`, `industry`, `phone`, `address`, `city`, `state`, `postal_code`, `gstin`. |
| **Products & Catalog** | `app.models.Product` | `id` | `name`, `capacity` (`250 ml`, `500 ml`, `1000 ml`, `2 litres`), `price`, `category_id`, `is_featured`, `image`. |
| **Inventory & Stock** | `app.models.Inventory` | `id`, `product_id` (1:1) | `quantity_in_stock`, `reorder_level`, `last_restocked`, `updated_at`. |
| **Categories** | `app.models.Category` | `id` | `name`, `description`. |
| **B2B Wholesale Quotes** | `app.models.QuoteRequest` | `id` | `user_id`, `product_id`, `name`, `email`, `company`, `size`, `quantity`, `details`, `status` (`pending`, `contacted`, `quoted`, `completed`). |
| **Quote Replies & Pricing** | `app.models.QuoteReply` | `id` | `quote_request_id`, `admin_name`, `message`, `price_per_unit`, `estimated_delivery`, `total_price` (computed). |
| **Email Verification** | `app.models.EmailVerificationToken` | `token` (UUID) | `quote_request_id`, `expires_at`, `verified`. |
| **B2C Retail Orders** | `app.models.Order` | `order_number` (`ORD-YYYYMMDD-XXXX`) | `user_id`, `shipping_name`, `shipping_email`, `shipping_phone`, `shipping_address`, `shipping_city`, `shipping_state`, `shipping_postal_code`, `total_amount`, `delivery_fee`, `delivery_distance_km`, `payment_method` (`online`/`cod`), `advance_paid`, `balance_due`, `status` (`pending`, `confirmed`, `processing`, `shipped`, `delivered`, `cancelled`), `invoice_token`. |
| **Order Items** | `app.models.OrderItem` | `id` | `order_id`, `product_id`, `product_name`, `product_price`, `quantity`, `get_total_price`. |
| **Quote Payments** | `app.models.PaymentTransaction` | `transaction_id` | `quote_request_id`, `amount`, `payment_method`, `status` (`pending`, `success`, `failed`). |
| **Order Payments** | `app.models.OrderPayment` | `transaction_id` | `order_id`, `amount`, `payment_method`, `status` (`pending`, `success`, `failed`, `refunded`). |
| **AI Chat Sessions** | `dispatch.models.ConversationSession` | `session_id` (UUID) | `user_id`, `title`, `is_active`, timestamps. |
| **AI Chat Messages** | `dispatch.models.ConversationMessage` | `id` | `session_id`, `role` (`user`/`assistant`/`system`), `content`, `metadata`. |
| **AI Decisions & Audits** | `dispatch.models.DispatchDecision` | `id` | `session_id`, `decision_type`, `input_data` (JSON), `output_data` (JSON), `rule_applied`, `groq_model`, `tokens_used`, `latency_ms`. |
| **Business Rules** | `dispatch.models.BusinessRule` | `id` | `name`, `rule_type` (`moq`, `price_floor`, `max_discount_pct`, `delivery_zone`), `parameters` (JSON), `is_active`, `priority`. |

---

## 3. Storage Separation: SQL Database vs. Hindsight Memory

```
┌────────────────────────────────────────────────────────────────────────┐
│                   INFORMATION ARCHITECTURE BOUNDARY                    │
├───────────────────────────────────┬────────────────────────────────────┤
│     RELATIONAL DATABASE (SQL)     │          HINDSIGHT MEMORY          │
│   (PostgreSQL / SQLite Storage)   │       (Vector Memory Store)        │
├───────────────────────────────────┼────────────────────────────────────┤
│                                   │                                    │
│  [1] Identity & Contacts          │  [1] Customer Nuance & Preference  │
│  • user_id: 42                    │  • "Prefers Eco-Friendly line"     │
│  • buyer_id: "DIST-00042"         │  • "Requests shrink-wrapped pallets│
│  • email: buyer@apexbev.com       │  • "Likes invoices CC'd to finance"│
│  • phone: +91 9876543210          │  • "Prefers WhatsApp updates"      │
│  • company_name: "Apex Beverage"  │                                    │
│  • gstin: "36AAAAA0000A1Z5"       │                                    │
│                                   │                                    │
│  [2] Product Catalog & Stock      │  [2] Negotiation Stances & History │
│  • Sport 500ML: ₹4.99 list price  │  • "Firm on ₹4.50 target price"    │
│  • Inventory: 2,400 units in stock│  • "Mentioned competitor @ ₹4.20"  │
│  • Reorder level: 100 units       │  • "Accepts 5% vol discount >1000" │
│                                   │                                    │
│  [3] Transactional Orders         │  [3] Purchasing Behavior & Trends  │
│  • ORD-20260901-4912: ₹2,250.00   │  • "Orders monthly in week 1"      │
│  • 500 units Sport 500ML          │  • "Scales up 2x before Diwali"    │
│  • Status: "delivered"            │  • "Always checks stock beforehand"│
│                                   │                                    │
│  [4] Formal Quotes & Payments     │  [4] Delivery Constraints & Context│
│  • Quote #14: 1,000 units         │  • "Loading dock closes at 4:30 PM"│
│  • Quoted: ₹4.50/unit by Admin    │  • "Bangalore route took 3 days"   │
│  • Payment: Stripe pi_3N9x...     │  • "East gate entrance for trucks" │
│                                   │                                    │
│  [5] Logistics Coordinates        │  [5] Relationship Intelligence     │
│  • Warehouse Lat: 17.3850° N      │  • "Expanding to Chennai Q4"       │
│  • Warehouse Lon: 78.4867° E      │  • "Procurement manager is Ramesh" │
│  • Distance: 12.4 km              │  • "Unhappy about delayed shipment"│
│                                   │                                    │
└───────────────────────────────────┴────────────────────────────────────┘
```

---

## 4. Database Access & Mutation Rules for DispatchAI

1. **Read-Only Access to Core `app/` Tables:** DispatchAI components (`dispatch/context_builder.py`, `dispatch/rules_engine.py`) perform strict **read-only ORM queries** against `Product`, `Inventory`, `Order`, `QuoteRequest`, and `UserProfile`.
2. **No Unsanctioned Writes:** DispatchAI never creates or modifies financial ledgers (`OrderPayment`, `PaymentTransaction`) or core product prices directly.
3. **Dedicated Write Sandbox in `dispatch/`:** DispatchAI writes exclusively to its own tables (`ConversationSession`, `ConversationMessage`, `DispatchDecision`).
4. **Hindsight Namespace Isolation:** Memory keys are prefixed with the application identifier and stable buyer ID:
   ```
   Memory Key: cheersthepure_DIST-00042
   ```

---

## 5. Verification & Schema Integrity

- **Database Migrations:** Applied safely through Django's migration chain:
  - `app/migrations/0014_userprofile_address_userprofile_buyer_id_and_more.py`
  - `dispatch/migrations/0001_initial.py`
- **Data Preservation:** Existing production rows retain full data integrity; `buyer_id` is automatically populated for legacy records.
- **Validation:** Automated unit test suite (`python manage.py test dispatch app`) confirms **24/24 tests passing** with zero schema conflicts.
