"""
DispatchAI Core Agent — Orchestrator.

Delegates to `dispatch.services.dispatch_ai_service.process_dispatch_chat`
to execute the complete 9-step cognitive pipeline.
"""

from typing import Any, Dict
from django.contrib.auth.models import User
from dispatch.models import ConversationSession
from dispatch.services.dispatch_ai_service import (
    process_dispatch_chat,
    validate_buyer_identity,
    FALLBACK_AI_UNAVAILABLE,
    FALLBACK_GROQ_TIMEOUT,
)


def process_message(
    user: User,
    session: ConversationSession,
    user_message_text: str,
) -> Dict[str, Any]:
    """
    Process a single user message through the full 9-step DispatchAI pipeline.

    Args:
        user:              Authenticated Django User (B2B).
        session:           ConversationSession instance.
        user_message_text: Raw user message string.

    Returns:
        Dict with content, model, tokens_used, latency_ms, rules_applied, decision_type, etc.
    """
    return process_dispatch_chat(
        buyer=user,
        user_message=user_message_text,
        session=session,
    )
