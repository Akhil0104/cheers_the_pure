# DispatchAI Production API Documentation

**Endpoint**: `POST /api/agent/chat`  
**Service**: DispatchAI B2B Supply & Distribution Assistant  
**Authentication**: Required (Django Session Cookie or Authenticated B2B Credentials)  
**Rate Limit**: 30 requests / minute per authenticated user

---

## 1. Overview

The `POST /api/agent/chat` endpoint is the production interface for interacting with **DispatchAI**. It coordinates **Groq LLM inference**, **Hindsight persistent memory**, and **authoritative PostgreSQL catalog & order records** to deliver commercial wholesale assistance for distributors, regional buyers, hotels, and corporate accounts.

---

## 2. Request Specifications

### HTTP Headers
```http
POST /api/agent/chat HTTP/1.1
Host: cheersthepure.in
Content-Type: application/json
Accept: application/json
```

### Request JSON Body
```json
{
  "buyer_id": "DIST-00042",
  "message": "We need 500 trays of 500ml pure mineral water delivered to our Nacharam warehouse next Tuesday.",
  "session_id": "8f3b6c42-2b6d-498c-8f4b-724128f9c731"
}
```

| Field | Type | Required | Description |
| :--- | :--- | :--- | :--- |
| **`message`** | `string` | **Yes** | The distributor's inquiry, quote request, or logistical question (1 to 4,000 characters). |
| **`buyer_id`** | `string` | *Optional* | The stable buyer identifier (e.g. `DIST-00042`). If omitted, securely derived from the authenticated session. Non-staff users cannot impersonate other accounts. |
| **`session_id`** | `string (UUID)` | *Optional* | Existing conversation session UUID to maintain multi-turn history. If omitted or not found, a new session is initialized automatically. |

---

## 3. Response Specifications

### Success Response (`HTTP 200 OK`)
```json
{
  "success": true,
  "reply": "We can supply 500 trays (9,000 bottles) of 500ml Pure Mineral Water at ₹4.50/unit, totaling ₹40,500. Delivery to your Nacharam warehouse can be scheduled for Tuesday. I have noted your preference for hydraulic tailgate offloading.\n\nWould you like me to submit this formal quotation request for administrative confirmation?",
  "memory_used": true,
  "memory_summary": "Recalled 2 customer preferences from previous conversations (warehouse delivery constraint, preferred timing).",
  "sources": [
    "Cheers the Pure Authoritative Database Catalog",
    "Active B2B Business Rules",
    "Hindsight Persistent Memory (cheersthepure-b2b)"
  ],
  "actions": [
    {
      "type": "request_quote",
      "label": "Submit Formal Quote Request",
      "url": "/orders/request/"
    }
  ],
  "session_id": "8f3b6c42-2b6d-498c-8f4b-724128f9c731",
  "buyer_id": "DIST-00042"
}
```

### Response Fields
| Field | Type | Description |
| :--- | :--- | :--- |
| **`success`** | `boolean` | `true` if processed successfully, `false` if an error occurred. |
| **`reply`** | `string` | The AI agent's grounded, professional B2B response. |
| **`memory_used`** | `boolean` | `true` if persistent Hindsight memories were recalled and used during generation. |
| **`memory_summary`** | `string` | Human-readable summary of recalled context (empty string if none used). |
| **`sources`** | `array[string]` | Grounding sources used (e.g. Catalog, SQL Orders, Active Rules, Hindsight). |
| **`actions`** | `array[object]` | Structured action suggestions (e.g. Quote submission link, order tracking link). |
| **`session_id`** | `string (UUID)` | Unique identifier for continuing the conversation turn. |
| **`buyer_id`** | `string` | Authenticated stable buyer identity. |

---

## 4. Error Responses

| Status Code | Reason | JSON Response |
| :--- | :--- | :--- |
| **`400 Bad Request`** | Missing or empty `message` or invalid JSON syntax | `{"success": false, "error": "The 'message' field is required and cannot be empty.", "reply": ""}` |
| **`401 Unauthorized`** | User is not logged in / session expired | `{"success": false, "error": "Authentication required. Please sign in to access DispatchAI.", "reply": ""}` |
| **`403 Forbidden`** | User has a retail (B2C) account | `{"success": false, "error": "Access restricted: DispatchAI is exclusively for verified B2B wholesale buyers and distributors.", "reply": ""}` |
| **`429 Too Many Requests`** | Rate limit exceeded (>30 req/min) | `{"success": false, "error": "Rate limit exceeded (maximum 30 requests/minute). Please wait a moment before sending another message.", "reply": ""}` |
| **`500 Internal Error`** | Server error | `{"success": false, "error": "An internal error occurred while processing your request. Please try again.", "reply": "I encountered an error processing your request. Please try again shortly."}` |

---

## 5. Implementation Examples

### cURL
```bash
curl -X POST https://cheersthepure.in/api/agent/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: sessionid=YOUR_SESSION_COOKIE" \
  -d '{
    "message": "What is the bulk price for 1000 trays of 1L water bottles?"
  }'
```

### JavaScript (Fetch / Axios)
```javascript
const response = await fetch('/api/agent/chat', {
  method: 'POST',
  headers: {
    'Content-Type': 'application/json',
    'X-CSRFToken': getCsrfToken(),
  },
  body: JSON.stringify({
    message: 'Can you check the delivery status of our recurring Tuesday order?',
    session_id: activeSessionId
  })
});

const data = await response.json();
if (data.success) {
  console.log('DispatchAI:', data.reply);
  console.log('Memory Used:', data.memory_used);
} else {
  console.error('Error:', data.error);
}
```

---

## 6. Security, Privacy & Anti-Hallucination Guarantees

1. **Zero Secret Leakage**: Internal system prompts, API keys (`GROQ_API_KEY`, `HINDSIGHT_API_KEY`), model configurations, and raw database IDs are never serialized or returned in responses.
2. **IDOR Prevention**: Non-staff users cannot inject arbitrary `buyer_id` values to query or alter another distributor's memory or order history.
3. **Database Grounding**: Prices and inventory levels are deterministically resolved against live SQL tables before response generation.
4. **Rate Limiting**: Protected by Django cache sliding-window throttle (30 calls/minute per user).
