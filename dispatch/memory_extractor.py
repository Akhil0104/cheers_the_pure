"""
DispatchAI Contextual Memory Extractor.

Extracts high-value, long-term B2B business context from distributor conversations
for persistent retention in Hindsight.

Filters out:
- Trivial acknowledgements & chit-chat ("Okay thanks", "Hello", "Good morning", "Bye")
- Factual transactional data (order IDs, invoices, catalog prices, SQL records)

Extracts 8 core B2B Context Categories:
1. delivery_preferences      (e.g., specific gate, offloading method, pallet preference)
2. warehouse_restrictions    (e.g., "warehouse cannot receive deliveries before 4 PM")
3. preferred_delivery_time   (e.g., early morning window, 48h turnaround requirement)
4. recurring_order_patterns  (e.g., weekly 500 trays, monthly bulk replenishment)
5. negotiated_terms          (e.g., buyer proposed terms / target rate — labeled as unverified buyer request)
6. customer_preferences      (e.g., prefers 500ml bottles, interested in eco-friendly packaging)
7. communication_preferences (e.g., send dispatch updates via WhatsApp / direct email)
8. relevant_business_context (e.g., supplying a 200-room hotel chain, opening a new retail outlet)

Safety Rule:
Unverified customer statements are NEVER recorded as approved discounts or contracts.
They are tagged as buyer requests/preferences.
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from dispatch import groq_client

logger = logging.getLogger(__name__)

# Chit-chat patterns that must NEVER become long-term memories
TRIVIAL_PATTERNS = [
    r"^(?:ok|okay|k|thanks|thank you|thx|ty|great|cool|sure|yes|no|yep|nope|got it|understood|done|fine|perfect|bye|goodbye|hi|hello|hey|good morning|good evening)\.?$",
    r"^(?:sounds good|looks good|will do|alright|ok thanks|okay thanks|thank you so much|much appreciated)\.?$",
]

# High-confidence B2B heuristic matchers for offline/fallback extraction
HEURISTIC_RULES = [
    (
        r"(?:warehouse|dock|facility|godown|depot).*(?:cannot|can't|do not|don't|no)\s+receive.*(?:before|after|between)\s+([0-9\:\sapmAPM]+)",
        "warehouse_restrictions",
        "Warehouse delivery time restriction: cannot receive deliveries {}",
    ),
    (
        r"(?:deliver|delivery|ship).*(?:before|after|between|only on|by)\s+([0-9\:\sapmAPM]+|[a-zA-Z]+\s+day)",
        "preferred_delivery_time",
        "Preferred delivery schedule: {}",
    ),
    (
        r"(?:need|order|require)\s+(\d+)\s*(?:trays?|bottles?|units?|boxes?|cases?).*(?:every|each|per)\s+(?:week|month|tuesday|monday|wednesday|thursday|friday|saturday)",
        "recurring_order_patterns",
        "Recurring supply pattern: {}",
    ),
    (
        r"(?:prefer|only use|want)\s+(?:only\s+)?(250\s*ml|500\s*ml|1000\s*ml|1\s*ltr|2\s*litres?|eco-friendly)",
        "customer_preferences",
        "Customer product preference: {}",
    ),
]


def is_trivial_message(text: str) -> bool:
    """
    Check if a message is purely conversational chit-chat with zero B2B memory value.
    """
    cleaned = text.strip().lower()
    if len(cleaned) < 3:
        return True
    for pattern in TRIVIAL_PATTERNS:
        if re.match(pattern, cleaned, re.IGNORECASE):
            return True
    return False


def extract_memories_fallback(user_message: str) -> List[Dict[str, Any]]:
    """
    Rule-based deterministic memory extractor used when Groq is unavailable.
    """
    extracted = []
    text = user_message.strip()

    if is_trivial_message(text):
        return []

    # Check warehouse and timing constraints
    match_wh = re.search(r'(?:warehouse|gate|facility|site|dock|godown).*(?:cannot|can\'t|don\'t|unable to|no)\s+receive.*', text, re.IGNORECASE)
    if match_wh:
        extracted.append({
            "content": f"Warehouse delivery constraint: {match_wh.group(0).strip()}",
            "category": "warehouse_restrictions",
            "importance": "high",
        })

    # Check delivery preferences and timing windows (e.g. after 4 PM / busy hours)
    elif match_deliv_pref := re.search(r'(?:delivery|deliver|receive|shipment).*(?:after|before|between|around|only)\s+([0-9\:\sapmAPM]+)', text, re.IGNORECASE):
        extracted.append({
            "content": f"Customer delivery timing preference: {text.strip()}",
            "category": "preferred_delivery_time",
            "importance": "high",
        })
    elif any(phrase in text.lower() for phrase in ['delivery after', 'delivery before', 'shop is busy', 'store is busy', 'busy before that', 'busy after that']):
        extracted.append({
            "content": f"Customer delivery timing constraint: {text.strip()}",
            "category": "delivery_preferences",
            "importance": "high",
        })

    # Check recurring volume
    match_rec = re.search(r'(?:every|each)\s+(?:week|month|tuesday|monday|wednesday|thursday|friday|saturday|fortnight)', text, re.IGNORECASE)
    if match_rec and any(w in text.lower() for w in ['tray', 'bottle', 'unit', 'order', 'dispatch', 'cases', 'box']):
        extracted.append({
            "content": f"Recurring order schedule mentioned: {text.strip()}",
            "category": "recurring_order_patterns",
            "importance": "medium",
        })

    return extracted


def extract_contextual_memories(
    user_message: str,
    ai_response: str,
    buyer_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Intelligently extract only relevant long-term B2B context from a conversation turn.

    Filters out trivial chit-chat and transactional data.
    Tags unverified buyer claims as requests rather than authoritative commitments.

    Returns:
        List of memory dicts:
        [
            {
                "content": "Warehouse cannot receive deliveries before 4 PM",
                "category": "warehouse_restrictions",
                "importance": "high",
            },
            ...
        ]
    """
    msg_clean = user_message.strip()
    if is_trivial_message(msg_clean):
        logger.debug("[MemoryExtractor] Filtered out trivial message: '%s'", msg_clean)
        return []

    conversation_text = (
        f"Distributor / Buyer: {msg_clean}\n"
        f"DispatchAI Assistant: {ai_response.strip()}"
    )

    system_prompt = (
        "You are an expert B2B Supply Chain Memory Extractor for Cheers the Pure Water.\n"
        "Analyze the distributor-agent conversation turn and extract ONLY long-term, high-value B2B context.\n\n"
        "ALLOWED CATEGORIES:\n"
        "1. delivery_preferences (e.g., gate access, tailgate unloading)\n"
        "2. warehouse_restrictions (e.g., 'Warehouse cannot receive deliveries before 4 PM', dock restrictions)\n"
        "3. preferred_delivery_time (e.g., early morning preferred, 2-day turnaround needed)\n"
        "4. recurring_order_patterns (e.g., 'Requires 500 trays every alternate Tuesday')\n"
        "5. negotiated_terms (e.g., buyer proposed volume pricing — ALWAYS label as '[Buyer Request - Pending Formal Approval]')\n"
        "6. customer_preferences (e.g., preference for 500ml SKU or specific pallet configuration)\n"
        "7. communication_preferences (e.g., prefers dispatch alerts via WhatsApp or email)\n"
        "8. relevant_business_context (e.g., distributor supplies hotel chain in HITEC City)\n\n"
        "STRICT FILTERING RULES:\n"
        "- DO NOT extract trivial chit-chat ('ok', 'thanks', 'sounds good', 'yes', 'no').\n"
        "- DO NOT extract transactional data (order numbers, invoice tokens, payments, standard prices in SQL database).\n"
        "- NEVER record an unverified customer statement as an approved contract or company discount.\n"
        "- If nothing meets the criteria, return an empty array [].\n\n"
        "OUTPUT FORMAT:\n"
        "Return ONLY a valid JSON array of objects with keys: 'content', 'category', 'importance' (low|medium|high).\n"
        "Example:\n"
        '[\n'
        '  {"content": "Warehouse cannot receive deliveries before 4 PM", "category": "warehouse_restrictions", "importance": "high"}\n'
        ']'
    )

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": conversation_text},
    ]

    try:
        result = groq_client.chat(
            messages=messages,
            model=groq_client.MODEL_EXTRACT,
            temperature=0.1,
            max_tokens=300,
        )
        content_str = result.get("content", "").strip()

        # Clean markdown wrappers if any
        if content_str.startswith("```"):
            lines = content_str.splitlines()
            content_str = "\n".join(l for l in lines if not l.startswith("```")).strip()

        data = json.loads(content_str)
        if isinstance(data, list):
            valid_memories: List[Dict[str, Any]] = []
            for item in data:
                if isinstance(item, dict) and item.get("content"):
                    c = str(item["content"]).strip()
                    if c and not is_trivial_message(c):
                        valid_memories.append({
                            "content": c,
                            "category": item.get("category", "relevant_business_context"),
                            "importance": item.get("importance", "medium"),
                        })
                elif isinstance(item, str) and item.strip() and not is_trivial_message(item):
                    valid_memories.append({
                        "content": item.strip(),
                        "category": "relevant_business_context",
                        "importance": "medium",
                    })
            return valid_memories
        return []

    except Exception as exc:
        logger.debug("[MemoryExtractor] Groq extraction unavailable (%s); using fallback extractor.", exc)
        return extract_memories_fallback(user_message=user_message)
