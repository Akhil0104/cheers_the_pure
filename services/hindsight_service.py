"""
Root level proxy for Hindsight persistent memory service.
Forwards to dispatch.services.hindsight_service for modularity.
"""

from dispatch.services.hindsight_service import (
    recall_customer_memory,
    retain_customer_memory,
    search_customer_memories,
    forget_customer_memory,
    is_hindsight_service_available,
    normalize_buyer_id,
    DEFAULT_MEMORY_BANK,
    HINDSIGHT_TIMEOUT_SECONDS,
)

__all__ = [
    'recall_customer_memory',
    'retain_customer_memory',
    'search_customer_memories',
    'forget_customer_memory',
    'is_hindsight_service_available',
    'normalize_buyer_id',
    'DEFAULT_MEMORY_BANK',
    'HINDSIGHT_TIMEOUT_SECONDS',
]
