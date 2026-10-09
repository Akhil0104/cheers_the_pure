"""
Hindsight Persistent Memory Client for DispatchAI.

Wraps the Hindsight Persistent Memory Service (`dispatch.services.hindsight_service`)
to maintain full backwards compatibility while benefiting from unified buyer
identity resolution, memory bank configuration (`cheersthepure-b2b`), and
fail-safe error handling.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from dispatch.services.hindsight_service import (
    recall_customer_memory,
    retain_customer_memory,
    search_customer_memories,
    forget_customer_memory,
    is_hindsight_service_available,
    DEFAULT_MEMORY_BANK,
)

logger = logging.getLogger(__name__)


def recall(
    user_id: Union[int, str, Any],
    query: str,
    limit: int = 10,
    bank_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Retrieve relevant memories for a user given a query string.
    Fails safely and returns [] if Hindsight is unavailable.
    """
    return recall_customer_memory(buyer_id=user_id, query=query, limit=limit, bank_id=bank_id)


def retain(
    user_id: Union[int, str, Any],
    memories: Union[str, List[Union[str, Dict[str, Any]]]],
    bank_id: Optional[str] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> List[str]:
    """
    Store new memories for a user after an AI conversation turn.
    Fails safely and returns [] if Hindsight is unavailable.
    """
    return retain_customer_memory(buyer_id=user_id, content=memories, bank_id=bank_id, metadata=metadata)


def search(
    query: str,
    filters: Optional[dict] = None,
    limit: int = 20,
    bank_id: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """
    Admin-level cross-user memory search.
    """
    return search_customer_memories(buyer_id=None, query=query, limit=limit, bank_id=bank_id)


def forget(memory_id: str, bank_id: Optional[str] = None) -> bool:
    """
    Delete a specific memory by ID.
    """
    return forget_customer_memory(memory_id=memory_id, bank_id=bank_id)
