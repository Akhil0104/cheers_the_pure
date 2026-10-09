"""
DispatchAI Memory Demonstration Service.

Provides a dedicated, controlled demonstration workflow to showcase
cross-session persistent memory retention and recall with Hindsight.

Demo Customer:
    Company Name: Sri Balaji Supermarket
    Buyer ID:     DIST-BALAJI-01
    Role:         B2B Distributor / Retail Supermarket
    City:         Hyderabad, Telangana

Workflow:
    SESSION 1:
        User: "We usually need delivery after 4 PM because our shop is busy before that."
        Agent: Acknowledges requirement & extracts delivery constraint.
        Action: Stores useful context in Hindsight (cheersthepure-b2b, tag: buyer:DIST-BALAJI-01).
        UI: Shows "SESSION 1: Memory created".

    ACTION:
        "Start New Session" button clicked.
        Action: Generates a fresh session ID. Does NOT erase Hindsight memory.

    SESSION 2:
        User: "I need 150 cases this time."
        Agent: Recalls previous delivery constraint from Hindsight.
        Agent: Responds confirming 150 cases and explicitly incorporating the after 4 PM delivery constraint.
        UI: Shows "SESSION 2: Memory recalled".

Technical Panel:
    - Buyer ID: DIST-BALAJI-01
    - Active Session ID
    - Memory Recalled
    - Memory Retained
    - Database Data Used
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from django.contrib.auth.models import User
from app.models import UserProfile, Product, Order
from dispatch.models import ConversationSession, ConversationMessage
from dispatch.services.dispatch_ai_service import process_dispatch_chat
from dispatch.services.hindsight_service import (
    clear_buyer_memories,
    get_buyer_memories,
    recall_customer_memory,
    retain_customer_memory,
)

logger = logging.getLogger(__name__)

DEMO_BUYER_ID = "DIST-BALAJI-01"
DEMO_USERNAME = "demo_sri_balaji"
DEMO_COMPANY = "Sri Balaji Supermarket"
DEMO_EMAIL = "balaji.supermarket@hyderabadretail.in"


def get_or_create_demo_customer() -> User:
    """
    Ensure the controlled demo customer 'Sri Balaji Supermarket' exists in the database.
    """
    user, created = User.objects.get_or_create(
        username=DEMO_USERNAME,
        defaults={
            "email": DEMO_EMAIL,
            "first_name": "Balaji",
            "last_name": "Rao",
            "is_active": True,
        }
    )
    if created:
        user.set_password("DemoPassword123!")
        user.save()

    profile, p_created = UserProfile.objects.get_or_create(
        user=user,
        defaults={
            "account_type": "b2b",
            "role": "distributor",
            "company_name": DEMO_COMPANY,
            "buyer_id": DEMO_BUYER_ID,
            "phone": "+91 98490 12345",
            "address": "Shop 4-8, Commercial Complex, KPHB Colony",
            "city": "Hyderabad",
            "state": "Telangana",
            "postal_code": "500072",
            "gstin": "36AABCS1234F1Z9",
        }
    )
    if not profile.buyer_id or profile.buyer_id != DEMO_BUYER_ID:
        profile.buyer_id = DEMO_BUYER_ID
        profile.company_name = DEMO_COMPANY
        profile.account_type = "b2b"
        profile.role = "distributor"
        profile.save()

    return user


def reset_demo_data() -> Dict[str, Any]:
    """
    Reset all conversational sessions and Hindsight memories for the demo customer.
    Allows evaluators to re-run the demonstration cleanly from scratch.
    """
    user = get_or_create_demo_customer()

    # Clear sessions and messages
    ConversationSession.objects.filter(user=user).delete()

    # Clear local persistent fallback memories
    clear_buyer_memories(DEMO_BUYER_ID)

    logger.info("[MemoryDemo] Reset demo customer data for %s (%s)", DEMO_COMPANY, DEMO_BUYER_ID)
    return {
        "success": True,
        "message": f"Demo customer '{DEMO_COMPANY}' memory and sessions reset cleanly.",
        "buyer_id": DEMO_BUYER_ID,
    }


def execute_demo_turn(
    message: str,
    session_id: Optional[str] = None,
    session_number: int = 1,
) -> Dict[str, Any]:
    """
    Execute a single conversational turn in the demonstration workflow.
    """
    user = get_or_create_demo_customer()

    # Record pre-execution memory count
    pre_memories = recall_customer_memory(buyer_id=DEMO_BUYER_ID, query=message, limit=10)

    # Execute cognitive pipeline
    result = process_dispatch_chat(
        buyer=user,
        user_message=message,
        session_id=session_id,
    )

    # Record post-execution memories
    post_memories = recall_customer_memory(buyer_id=DEMO_BUYER_ID, query="delivery timing preferences", limit=10)
    all_retained = get_buyer_memories(DEMO_BUYER_ID)

    mem_count = len(pre_memories)
    memory_used = mem_count > 0

    sources = [
        "Cheers the Pure Authoritative Database Catalog",
        "Active B2B Pricing Rules (Tier 1: 100-499 units, Tier 2: 500+ units)",
    ]
    if memory_used:
        sources.append("Hindsight Persistent Memory (cheersthepure-b2b)")

    return {
        "success": result.get("ok", True),
        "reply": result.get("content", ""),
        "session_id": result.get("session_id", ""),
        "session_number": session_number,
        "buyer_id": DEMO_BUYER_ID,
        "company_name": DEMO_COMPANY,
        "user_message": message,
        "memory_used": memory_used,
        "memory_recalled": pre_memories,
        "memory_recalled_count": mem_count,
        "memory_created": len(all_retained) > 0 and session_number == 1,
        "memory_retained": all_retained,
        "database_used": sources,
    }
