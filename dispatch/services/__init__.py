"""
DispatchAI Unified Services Package.

Authoritative SQL database services:
- get_product_information
- get_current_price
- get_available_inventory
- get_customer_orders
- get_quote_information
- get_payment_status

Persistent Hindsight memory services:
- recall_customer_memory
- retain_customer_memory
- search_customer_memories
- forget_customer_memory
- is_hindsight_service_available
"""

from .catalog_service import (
    get_product_information,
    get_current_price,
    get_available_inventory,
    get_customer_orders,
    get_quote_information,
    get_payment_status,
)
from .hindsight_service import (
    recall_customer_memory,
    retain_customer_memory,
    search_customer_memories,
    forget_customer_memory,
    is_hindsight_service_available,
    normalize_buyer_id,
)

from .dispatch_ai_service import (
    process_dispatch_chat,
    validate_buyer_identity,
)

from dispatch.tools import (
    search_product,
    get_current_price as tool_get_current_price,
    get_customer_order_history,
    get_quote_status,
    get_payment_status as tool_get_payment_status,
    create_quote_request,
    prepare_order_request,
    check_delivery_preference,
    summarize_customer_requirements,
)

__all__ = [
    'get_product_information',
    'get_current_price',
    'get_available_inventory',
    'get_customer_orders',
    'get_quote_information',
    'get_payment_status',
    'recall_customer_memory',
    'retain_customer_memory',
    'search_customer_memories',
    'forget_customer_memory',
    'is_hindsight_service_available',
    'normalize_buyer_id',
    'process_dispatch_chat',
    'validate_buyer_identity',
    'search_product',
    'tool_get_current_price',
    'get_customer_order_history',
    'get_quote_status',
    'tool_get_payment_status',
    'create_quote_request',
    'prepare_order_request',
    'check_delivery_preference',
    'summarize_customer_requirements',
]
