"""
Root level proxy for DispatchAI AI Agent Service.
Forwards to dispatch.services.dispatch_ai_service.
"""

from dispatch.services.dispatch_ai_service import (
    process_dispatch_chat,
    validate_buyer_identity,
    FALLBACK_AI_UNAVAILABLE,
    FALLBACK_GROQ_TIMEOUT,
)

__all__ = [
    'process_dispatch_chat',
    'validate_buyer_identity',
    'FALLBACK_AI_UNAVAILABLE',
    'FALLBACK_GROQ_TIMEOUT',
]
