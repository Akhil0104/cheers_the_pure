# DispatchAI Memory Strategy & Persistent Context Architecture

This document establishes the architecture, extraction policies, and strict separation between **Factual Transactional Data (Database)** and **Contextual Business Memory (Hindsight)** for **DispatchAI** at **Cheers the Pure Water**.

---

## 1. Executive Summary & Core Mission

DispatchAI is not a generic consumer chatbot; it is a B2B supply and distribution executive for wholesale buyers, regional beverage distributors, hotels, corporate accounts, and retail partners.

To build lasting commercial relationships, DispatchAI must remember customer operational constraints, delivery preferences, and recurring order rhythms across conversation sessions without duplicating transactional database data or hallucinating unverified commitments.

---

## 2. Separation of Responsibilities: SQL Database vs. Hindsight Memory

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        CHEERSTHEPURE ARCHITECTURE                       │
└────────────────────────────────────┬────────────────────────────────────┘
                                     │
         ┌───────────────────────────┴───────────────────────────┐
         ▼                                                       ▼
┌───────────────────────────────────┐   ┌───────────────────────────────────┐
│       RELATIONAL DATABASE         │   │         HINDSIGHT MEMORY          │
│        (PostgreSQL / SQL)         │   │     (cheersthepure-b2b Bank)      │
├───────────────────────────────────┤   ├───────────────────────────────────┤
│ • Product catalog & unit prices   │   │ • Warehouse dock restrictions     │
│ • Inventory stock quantities      │   │ • Delivery gate timings (<4 PM)   │
│ • Formal quote requests & replies │   │ • Preferred delivery days         │
│ • B2C & B2B orders & line items   │   │ • Recurring weekly/monthly demand │
│ • Payment records & balance due   │   │ • Preferred packaging/SKUs        │
│ • User accounts & GSTIN / Tax IDs │   │ • Buyer-proposed pricing targets  │
│ • Invoices & tracking tokens      │   │ • Communication channel notes     │
└───────────────────────────────────┘   └───────────────────────────────────┘
         ▲                                                       ▲
         │ (Deterministic SQL queries)                           │ (Semantic recall/retain)
         └───────────────────────────┬───────────────────────────┘
                                     │
                         ┌───────────┴───────────┐
                         │   DISPATCHAI AGENT    │
                         │ (Grounded Groq LLM)   │
                         └───────────────────────┘
```

### Deterministic Database Responsibilities (SQL)
- **Single Source of Truth**: All financial, catalog, inventory, order, and payment states are authoritative and deterministic.
- **Never Inferred by AI**: Product names, unit prices, available inventory quantities, and payment confirmations originate strictly from database models (`Product`, `Inventory`, `Order`, `QuoteRequest`, `PaymentTransaction`).

### Persistent Contextual Memory Responsibilities (Hindsight)
- **Unstructured Operational Knowledge**: Captures customer preferences, delivery constraints, and long-term context that does not fit neatly into relational tables.
- **Personalized B2B Relationship Management**: Enables DispatchAI to proactively acknowledge previous agreements, specific delivery windows, and offloading requirements.

---

## 3. The 8 Core B2B Memory Categories

DispatchAI extracts and retains memories strictly within these 8 operational categories:

| Category | Description | Example |
| :--- | :--- | :--- |
| **`warehouse_restrictions`** | Physical dock, gate clearance, or unloading constraints | *"Warehouse cannot receive deliveries before 4 PM."* |
| **`delivery_preferences`** | Specific unloading requirements or site logistics | *"Requires hydraulic tailgate truck for pallet offloading at Nacharam depot."* |
| **`preferred_delivery_time`** | Preferred arrival windows or dispatch cycles | *"Prefers deliveries on Tuesday mornings between 8 AM and 11 AM."* |
| **`recurring_order_patterns`** | Predictable volume cycles | *"Consistently restocks 500 trays of 500ml every alternate week."* |
| **`negotiated_terms`** | Buyer-proposed pricing targets or payment split wishes | *"Buyer requested ₹4.20/unit for 5,000 unit bulk run [Buyer Request - Pending Approval]."* |
| **`customer_preferences`** | SKU, bottle styling, or tray packaging preferences | *"Prefers 500ml bottles over 1L for banquet and event catering."* |
| **`communication_preferences`** | Contact channel & dispatch notification preferences | *"Requests dispatch tracking alerts directly to warehouse manager's WhatsApp."* |
| **`relevant_business_context`** | Buyer business model, branch count, or seasonal events | *"Distributor supplies 12 corporate cafeterias across HITEC City."* |

---

## 4. Extraction Strategy: Retain vs. Discard

DispatchAI employs a two-tier extraction filter to prevent memory bloating and retain only high-value B2B intelligence.

### What MUST Be Retained (Useful B2B Context)
- Operational rules: *"Our gate closes strictly at 5:00 PM."*
- Recurring patterns: *"We order 200 boxes every Monday."*
- Logistical preferences: *"Deliver to Gate 3 behind the main facility."*
- Product interest: *"We are expanding our retail line with 250ml pocket bottles next quarter."*

### What MUST Be Discarded (Trivial Noise)
- Conversational acknowledgments: *"Okay thanks"*, *"Understood"*, *"Sounds good"*, *"Bye"*, *"Hello"*.
- Transient reactions: *"That's fine"*, *"Got it"*, *"Let me check with my team"*.
- Duplicate factual SQL data: *"My order number is ORD-2026-1234"* (already tracked in database).

---

## 5. Critical Commercial Safety Rule: Unverified Statements

> [!CAUTION]
> **Unverified customer statements are NEVER recorded or treated as approved company contracts, pricing commitments, or official discounts.**

- **Principle**: If a customer claims *"Your sales manager promised me ₹3.50 per unit"*, DispatchAI:
  1. Records the statement in Hindsight strictly as: `[Buyer Claim - Unverified: requested ₹3.50/unit pricing]`.
  2. Adheres to live database pricing and active `BusinessRule` price floors during the conversation turn.
  3. Politely informs the distributor that official volume discounts require administrative quote confirmation.

---

## 6. Memory Bank & Buyer Identity Isolation

- **Default Memory Bank**: `cheersthepure-b2b`
- **Stable Buyer Identity**: Every memory entry is tagged with `buyer:{buyer_id}` (e.g. `buyer:DIST-00042`).
- **Privacy & Isolation**: Memory queries for Buyer A (`DIST-00042`) will never retrieve or leak memories belonging to Buyer B (`DIST-00099`).

---

## 7. Lifecycle & Resilience

```
User Message
     │
     ▼
[Low-Semantic Filter] ──(Trivial chit-chat)──► Discard (Zero Token Cost)
     │
     ▼ (Substantive B2B message)
[Hindsight Recall] ──(Tags: buyer:DIST-00042)──► Injected into Groq System Prompt
     │
     ▼
[Groq LLM Reasoning + Business Rule Validation]
     │
     ▼
[Memory Extraction Step] ──(Category classification + unverified tagging)
     │
     ▼
[Hindsight Retain] ──(Fail-safe async storage in cheersthepure-b2b bank)
```

- **Fail-Safe Operation**: If Hindsight API is unavailable or times out, DispatchAI gracefully continues using deterministic database data without crashing or degrading user experience.
- **GDPR & Erasure**: Supports `forget_customer_memory(memory_id)` for customer data corrections and privacy compliance.
