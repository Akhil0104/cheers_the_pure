"""Invoice generation helpers for B2C orders.

Generates a cryptographically secure 64-character invoice token using
Python's `secrets` module (secrets.token_hex(32) = 64 hex chars),
which is more secure than the previous uuid4().hex (32 chars).
"""
import secrets
from django.utils import timezone


def generate_invoice_for_order(order):
    """Mark order as invoiced and return the secure 64-char invoice token.

    Uses secrets.token_hex(32) which generates 64 cryptographically secure
    hexadecimal characters — satisfying the 64-character requirement while
    ensuring each token is unpredictable and unique.
    """
    if not order.invoice_token:
        # 64-character cryptographically secure token
        order.invoice_token = secrets.token_hex(32)
    order.invoice_generated_at = timezone.now()
    order.save(update_fields=['invoice_token', 'invoice_generated_at'])
    return order.invoice_token
