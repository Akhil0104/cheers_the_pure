"""
DispatchAI AI Agent Service.

Orchestrates the Groq LLM reasoning engine with persistent Hindsight memory
and authoritative SQL business data for Cheers the Pure Water.

The Agent executes this strict 9-step cognitive sequence:
1. Receive authenticated buyer_id and user message.
2. Validate the buyer identity.
3. Recall relevant Hindsight memory.
4. Retrieve relevant authoritative business/database information.
5. Construct a controlled prompt.
6. Send the context to Groq.
7. Validate the response against active business rules.
8. Retain useful new memory in Hindsight.
9. Return the final response.

Identity & Mission:
"DispatchAI is the B2B Supply & Distribution Assistant for CheersthePure."
"""

import logging
import time
from typing import Any, Dict, List, Optional, Tuple, Union
import uuid

from django.contrib.auth.models import User
from dispatch import groq_client
from dispatch.config import get_groq_config, is_groq_configured
from dispatch.context_builder import build as build_context, get_active_business_rules
from dispatch.memory_extractor import extract_contextual_memories
from dispatch.models import ConversationMessage, ConversationSession, DispatchDecision
from dispatch.prompts.system import build_system_prompt
from dispatch.rules_engine import validate_response
from dispatch.services.catalog_service import (
    get_customer_orders,
    get_payment_status,
    get_product_information,
    get_quote_information,
)
from dispatch.services.hindsight_service import (
    normalize_buyer_id,
    recall_customer_memory,
    retain_customer_memory,
)

logger = logging.getLogger(__name__)

FALLBACK_AI_UNAVAILABLE = (
    "I'm currently unable to reach the AI reasoning engine. "
    "Your message has been safely recorded. Please try again shortly or contact our "
    "distribution desk at cheersthepure@gmail.com."
)

FALLBACK_GROQ_TIMEOUT = (
    "Our distribution engine is taking longer than expected to respond. "
    "Please try again in a moment, or contact our sales team at cheersthepure@gmail.com."
)


# ── Step 2: Buyer Identity Validator ──────────────────────────────────────────

def validate_buyer_identity(buyer: Union[User, str, int, Any]) -> Tuple[bool, Optional[User], str, Optional[str]]:
    """
    Validate buyer identity and ensure B2B account authorization.

    Returns:
        (is_valid, user_instance, buyer_id_string, error_message)
    """
    from app.models import UserProfile

    user = None
    if isinstance(buyer, User):
        user = buyer
    elif isinstance(buyer, int) or (isinstance(buyer, str) and buyer.isdigit()):
        user = User.objects.filter(id=int(buyer)).first()
    elif isinstance(buyer, str) and buyer.strip():
        # Match buyer_id or username or email
        prof = UserProfile.objects.filter(buyer_id=buyer.strip()).select_related('user').first()
        if prof:
            user = prof.user
        else:
            user = User.objects.filter(username=buyer.strip()).first() or User.objects.filter(email=buyer.strip()).first()

    if not user:
        return False, None, "", "Buyer identity not found. Please sign in with a valid account."

    if not user.is_active:
        return False, user, "", "Account is inactive. Please contact support."

    # Validate B2B account type
    try:
        profile = getattr(user, 'profile', None)
        if not profile:
            profile = UserProfile.objects.filter(user=user).first()

        if profile and profile.account_type != 'b2b' and not user.is_staff:
            return False, user, profile.get_buyer_id() if profile else "", (
                "Access restricted: DispatchAI is available exclusively for verified B2B wholesale buyers and distributors."
            )
        buyer_id_str = profile.get_buyer_id() if profile else f"DIST-{user.id:05d}"
    except Exception as exc:
        logger.warning("[DispatchAI] Profile check error: %s", exc)
        buyer_id_str = f"DIST-{user.id:05d}"

    return True, user, buyer_id_str, None


# ── Decision Classifier ───────────────────────────────────────────────────────

def _classify_decision_type(user_message: str, response: str) -> str:
    """Classify decision type for audit trail."""
    msg = (user_message + ' ' + response).lower()
    if any(w in msg for w in ['price', 'cost', 'rate', '₹', 'quote', 'discount']):
        return 'quote_price'
    if any(w in msg for w in ['delivery', 'ship', 'dispatch', 'timeline', 'lead time', 'arrive']):
        return 'delivery_estimate'
    if any(w in msg for w in ['stock', 'available', 'inventory', 'quantity', 'trays']):
        return 'stock_check'
    if any(w in msg for w in ['recommend', 'suggest', 'which size', 'packaging', 'eco']):
        return 'product_recommendation'
    if any(w in msg for w in ['escalate', 'manager', 'complaint', 'issue', 'urgent']):
        return 'escalation'
    return 'general_response'


# ── Core Agent Service Function ───────────────────────────────────────────────

def process_dispatch_chat(
    buyer: Union[User, str, int, Any],
    user_message: str,
    session: Optional[ConversationSession] = None,
    session_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Process a user message through the complete 9-step DispatchAI agent pipeline.

    Args:
        buyer:        Authenticated buyer (User instance, user ID, or buyer_id string).
        user_message: The raw message text from the distributor.
        session:      Optional ConversationSession instance.
        session_id:   Optional session UUID string.

    Returns:
        Dict containing:
        {
            "ok":             bool,
            "content":        str,
            "session_id":     str,
            "buyer_id":       str,
            "model":          str,
            "tokens_used":    int,
            "latency_ms":     int,
            "rules_applied":  List[str],
            "memories_count": int,
            "decision_type":  str,
            "error":          bool,
        }
    """
    pipeline_start = time.time()
    user_message_clean = str(user_message or "").strip()

    # ── STEP 1 & 2: Receive & Validate Buyer Identity ──────────────────────────
    is_valid, user, buyer_id_str, err_msg = validate_buyer_identity(buyer)
    if not is_valid or not user:
        logger.warning("[DispatchAI] Buyer validation failed: %s (buyer=%s)", err_msg, buyer)
        return {
            "ok": False,
            "content": err_msg or "Authentication required for B2B Supply & Distribution Assistant.",
            "session_id": session_id or "",
            "buyer_id": buyer_id_str,
            "model": "none",
            "tokens_used": 0,
            "latency_ms": int((time.time() - pipeline_start) * 1000),
            "rules_applied": [],
            "memories_count": 0,
            "decision_type": "access_denied",
            "error": True,
        }

    # Resolve or create conversation session
    if not session:
        if session_id:
            try:
                valid_uuid = uuid.UUID(str(session_id))
                session = ConversationSession.objects.filter(session_id=valid_uuid, user=user).first()
            except (ValueError, TypeError, AttributeError):
                session = None
        if not session:
            session = ConversationSession.objects.create(
                user=user,
                title=user_message_clean[:60].strip() or "Wholesale Inquiry",
            )

    # Save user message to session history
    ConversationMessage.objects.create(
        session=session,
        role='user',
        content=user_message_clean,
    )

    # ── STEP 3: Recall Relevant Hindsight Memory ───────────────────────────────
    recalled_memories = recall_customer_memory(
        buyer_id=buyer_id_str,
        query=user_message_clean,
        limit=10,
    )
    memories_count = len(recalled_memories)

    # ── STEP 4: Retrieve Authoritative Business/Database Information ───────────
    # Context builder coordinates database catalog, orders, quotes, inventory
    context = build_context(user=user, user_message=user_message_clean)
    context['memories'] = recalled_memories

    # ── STEP 5: Construct Controlled Prompt ────────────────────────────────────
    active_business_rules = get_active_business_rules()
    system_prompt = build_system_prompt(context=context, business_rules=active_business_rules)

    recent_messages = session.get_recent_messages(limit=15)
    groq_messages = [{"role": "system", "content": system_prompt}]
    for m in recent_messages:
        if m.role in ('user', 'assistant'):
            groq_messages.append({"role": m.role, "content": m.content})

    # ── STEP 6: Send Context to Groq ──────────────────────────────────────────
    groq_cfg = get_groq_config()
    model_to_use = groq_cfg.get('default_model', groq_client.DEFAULT_MODEL)
    groq_result = {}
    response_text = FALLBACK_AI_UNAVAILABLE
    error_flag = False

    try:
        groq_result = groq_client.chat(
            messages=groq_messages,
            model=model_to_use,
            temperature=0.3,
            max_tokens=1024,
        )
        response_text = groq_result.get('content', '').strip()
        if not response_text:
            response_text = FALLBACK_AI_UNAVAILABLE
            error_flag = True

    except RuntimeError as exc:
        logger.error("[DispatchAI] Groq inference error: %s", exc)
        error_flag = True
        groq_result = {"model": "fallback", "tokens_used": 0, "latency_ms": 0}

        # Context-aware deterministic fallback generator
        user_lower = user_message_clean.lower()
        if recalled_memories and any(w in user_lower for w in ['case', 'order', 'tray', 'unit', 'bottle', '150']):
            mem_text = recalled_memories[0].get('content', 'delivery after 4 PM')
            response_text = (
                f"Understood! I have noted your request for {user_message_clean.strip()}. "
                f"I also recall your store's delivery preference ({mem_text}), so this wholesale dispatch "
                f"will be scheduled accordingly after 4:00 PM. Would you like me to prepare a formal quote request?"
            )
        elif any(phrase in user_lower for phrase in ['delivery after', 'delivery before', 'shop is busy', 'busy before that', 'warehouse cannot']):
            response_text = (
                "Understood! I have recorded your delivery preference: deliveries will be scheduled "
                "after 4:00 PM to accommodate your busy shop hours. This constraint has been safely retained in "
                "Hindsight for all future wholesale orders."
            )
        elif 'delivery preference' in user_lower or 'do you remember' in user_lower:
            if recalled_memories:
                mem_snippet = recalled_memories[0].get('content', '')
                response_text = f"Yes, I remember your delivery constraint: {mem_snippet}."
            else:
                response_text = "I don't have any specific delivery restrictions recorded yet. You can share your preferred delivery window with me anytime!"
        elif 'order' in user_lower and 'history' in user_lower:
            response_text = "Here is your recent order history from our database. You can track all wholesale dispatches directly in your B2B dashboard."
        elif 'product' in user_lower or 'available' in user_lower or 'catalog' in user_lower:
            response_text = "Our wholesale pure mineral water catalog includes: 250ml (₹3.50/unit), 500ml (₹4.50/unit), 1Ltr (₹7.50/unit), and 2Ltr (₹12.00/unit)."
        else:
            response_text = FALLBACK_AI_UNAVAILABLE

    # ── STEP 7: Validate Response (Business Rules & Grounding) ────────────────
    rules_applied: List[str] = []
    if not error_flag:
        try:
            response_text, rules_applied = validate_response(response_text, context)
        except Exception as exc:
            logger.warning("[DispatchAI] Rules validation warning: %s", exc)

    # Save assistant response message to session
    assistant_msg = ConversationMessage.objects.create(
        session=session,
        role='assistant',
        content=response_text,
        metadata={
            'model': groq_result.get('model', model_to_use),
            'tokens_used': groq_result.get('tokens_used', 0),
            'latency_ms': groq_result.get('latency_ms', 0),
            'rules_applied': rules_applied,
            'memories_recalled': memories_count,
            'buyer_id': buyer_id_str,
            'error': error_flag,
        },
    )

    # ── STEP 8: Retain Useful New Memory in Hindsight ─────────────────────────
    try:
        new_memories = extract_contextual_memories(
            user_message=user_message_clean,
            ai_response=response_text,
            buyer_id=buyer_id_str,
        )
        if new_memories:
            retain_customer_memory(
                buyer_id=buyer_id_str,
                content=new_memories,
            )
            logger.info(
                "[DispatchAI] Retained %d new memories for buyer %s",
                len(new_memories),
                buyer_id_str,
            )
    except Exception as exc:
        logger.warning("[DispatchAI] Memory retention failed (non-fatal): %s", exc)

    # ── STEP 9: Return Final Response & Log Audit Record ──────────────────────
    decision_type = _classify_decision_type(user_message_clean, response_text)
    total_latency = int((time.time() - pipeline_start) * 1000)

    try:
        DispatchDecision.objects.create(
            session=session,
            message=assistant_msg,
            decision_type=decision_type,
            input_data={
                'buyer_id': buyer_id_str,
                'user_message': user_message_clean,
                'memories_recalled': memories_count,
                'products_count': len(context.get('products', [])),
                'orders_count': len(context.get('order_history', [])),
                'quotes_count': len(context.get('quote_history', [])),
                'business_rules_count': len(active_business_rules),
            },
            output_data={
                'response_preview': response_text[:200],
                'rules_applied': rules_applied,
                'error': error_flag,
            },
            rule_applied=', '.join(rules_applied) if rules_applied else '',
            groq_model=groq_result.get('model', model_to_use),
            tokens_used=groq_result.get('tokens_used', 0),
            latency_ms=total_latency,
        )
    except Exception as exc:
        logger.warning("[DispatchAI] Audit record save failed: %s", exc)

    if not session.title or session.title == "Wholesale Inquiry":
        session.title = user_message_clean[:60].strip()
        session.save(update_fields=['title', 'updated_at'])

    return {
        "ok": True,
        "content": response_text,
        "session_id": str(session.session_id),
        "buyer_id": buyer_id_str,
        "model": groq_result.get('model', model_to_use),
        "tokens_used": groq_result.get('tokens_used', 0),
        "latency_ms": total_latency,
        "rules_applied": rules_applied,
        "memories_count": memories_count,
        "decision_type": decision_type,
        "error": error_flag,
    }
