"""
DispatchAI Deterministic Catalog, Order, Quote, and Payment Services.

Authoritative SQL database access functions:
- get_product_information(product_identifier=None)
- get_current_price(product_identifier)
- get_available_inventory(product_identifier)
- get_customer_orders(user, limit=10)
- get_quote_information(user, quote_id=None, limit=10)
- get_payment_status(user, quote_id=None, order_number=None)
"""

import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Union
from django.contrib.auth.models import User
from django.db.models import Q

logger = logging.getLogger(__name__)


# ── Product & Catalog Services ────────────────────────────────────────────────

def get_product_information(
    product_identifier: Optional[Union[int, str]] = None
) -> Union[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Retrieve real-time product information strictly from the database.

    Args:
        product_identifier: Product ID (int), product name (str), or capacity (str).
                           If None, returns all active products in the catalog.

    Returns:
        List of product dicts (if identifier is None), single product dict, or None if not found.
    """
    from app.models import Product

    def _format_product(p: Product) -> Dict[str, Any]:
        stock = None
        try:
            stock = p.inventory.quantity_in_stock
        except Exception:
            stock = None

        tray_counts = {
            '250 ml': 18,
            '500 ml': 18,
            '1000 ml': 12,
            '1 Ltr': 12,
            '2 litres': 6,
        }
        tray_units = tray_counts.get(p.capacity, 12)

        return {
            'id': p.id,
            'name': p.name,
            'capacity': p.capacity,
            'price': Decimal(str(p.price)),
            'price_display': f"₹{p.price}",
            'category': p.category.name if p.category else 'Standard',
            'stock_quantity': stock,
            'is_in_stock': (stock is not None and stock > 0),
            'units_per_tray': tray_units,
            'is_featured': p.is_featured,
            'description': p.description or '',
        }

    try:
        if product_identifier is None:
            products = Product.objects.select_related('category').prefetch_related('inventory').order_by('category__name', 'name')
            return [_format_product(p) for p in products]

        if isinstance(product_identifier, int) or (isinstance(product_identifier, str) and product_identifier.isdigit()):
            p = Product.objects.select_related('category').prefetch_related('inventory').filter(id=int(product_identifier)).first()
            return _format_product(p) if p else None

        ident_str = str(product_identifier).strip()
        p = Product.objects.select_related('category').prefetch_related('inventory').filter(
            Q(name__iexact=ident_str) | Q(capacity__iexact=ident_str) | Q(name__icontains=ident_str)
        ).first()

        return _format_product(p) if p else None

    except Exception as exc:
        logger.error('Error in get_product_information(%s): %s', product_identifier, exc)
        return [] if product_identifier is None else None


def get_current_price(product_identifier: Union[int, str]) -> Optional[Decimal]:
    """
    Retrieve the current unit price strictly from the database.
    Returns None if the product does not exist in the database.
    """
    prod = get_product_information(product_identifier)
    if prod and isinstance(prod, dict):
        return prod['price']
    return None


def get_available_inventory(product_identifier: Union[int, str]) -> Optional[int]:
    """
    Retrieve current stock level strictly from the database Inventory model.
    """
    prod = get_product_information(product_identifier)
    if prod and isinstance(prod, dict):
        return prod.get('stock_quantity')
    return None


# ── Customer Orders Service ───────────────────────────────────────────────────

def get_customer_orders(user: User, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve real-time order history for an authenticated user.
    """
    from app.models import Order

    try:
        orders_qs = (
            Order.objects
            .filter(Q(user=user) | Q(shipping_email=user.email))
            .prefetch_related('items', 'payment')
            .order_by('-created_at')[:limit]
        )

        orders = []
        for o in orders_qs:
            items = [
                {
                    'product_name': item.product_name,
                    'price': Decimal(str(item.product_price)),
                    'quantity': item.quantity,
                    'total': Decimal(str(item.get_total_price())),
                }
                for item in o.items.all()
            ]

            payment_status = 'pending'
            payment_method = o.payment_method
            try:
                if hasattr(o, 'payment') and o.payment:
                    payment_status = o.payment.status
                    payment_method = o.payment.payment_method
            except Exception:
                pass

            orders.append({
                'order_number': o.order_number,
                'created_at': o.created_at.strftime('%d %b %Y, %I:%M %p'),
                'total_amount': Decimal(str(o.total_amount)),
                'delivery_fee': Decimal(str(o.delivery_fee)),
                'status': o.status,
                'status_display': o.get_status_display(),
                'payment_method': payment_method,
                'payment_status': payment_status,
                'advance_paid': Decimal(str(o.advance_paid)),
                'balance_due': Decimal(str(o.balance_due)),
                'shipping_address': f"{o.shipping_address}, {o.shipping_city}, {o.shipping_state} {o.shipping_postal_code}".strip(", "),
                'items': items,
                'invoice_token': o.invoice_token,
            })

        return orders

    except Exception as exc:
        logger.error('Error in get_customer_orders for user %s: %s', user.id, exc)
        return []


# ── Quote Information Service ─────────────────────────────────────────────────

def get_quote_information(
    user: User,
    quote_id: Optional[int] = None,
    limit: int = 10
) -> Union[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Retrieve wholesale quote requests and official replies for an authenticated user.
    """
    from app.models import QuoteRequest

    def _format_quote(q: QuoteRequest) -> Dict[str, Any]:
        replies = []
        latest_unit_price = None
        latest_total_price = None
        delivery_estimate = None

        for r in q.replies.all():
            reply_dict = {
                'admin_name': r.admin_name,
                'message': r.message,
                'price_per_unit': Decimal(str(r.price_per_unit)) if r.price_per_unit is not None else None,
                'total_price': Decimal(str(r.total_price)) if r.total_price is not None else None,
                'estimated_delivery': r.estimated_delivery,
                'created_at': r.created_at.strftime('%d %b %Y'),
            }
            replies.append(reply_dict)
            if latest_unit_price is None and r.price_per_unit is not None:
                latest_unit_price = Decimal(str(r.price_per_unit))
                latest_total_price = Decimal(str(r.total_price)) if r.total_price is not None else None
                delivery_estimate = r.estimated_delivery

        payments = []
        is_paid = False
        for p in q.payments.all():
            payments.append({
                'transaction_id': p.transaction_id,
                'amount': Decimal(str(p.amount)),
                'status': p.status,
                'payment_method': p.payment_method,
                'created_at': p.created_at.strftime('%d %b %Y'),
            })
            if p.status == 'success':
                is_paid = True

        token = None
        try:
            if hasattr(q, 'verification_token') and q.verification_token:
                token = q.verification_token.token
        except Exception:
            pass

        return {
            'id': q.id,
            'product_name': q.product.name if q.product else q.size,
            'size': q.size,
            'quantity': q.quantity,
            'preferred_delivery_timing': q.preferred_delivery_timing or 'Standard',
            'delivery_address': q.delivery_address or '',
            'status': q.status,
            'status_display': q.get_status_display(),
            'created_at': q.created_at.strftime('%d %b %Y'),
            'quoted_unit_price': latest_unit_price,
            'quoted_total_price': latest_total_price,
            'delivery_estimate': delivery_estimate,
            'is_paid': is_paid,
            'replies': replies,
            'payments': payments,
            'tracking_token': token,
        }

    try:
        if quote_id is not None:
            q = (
                QuoteRequest.objects
                .filter(Q(user=user) | Q(email=user.email))
                .filter(id=quote_id)
                .select_related('product', 'verification_token')
                .prefetch_related('replies', 'payments')
                .first()
            )
            return _format_quote(q) if q else None

        quotes_qs = (
            QuoteRequest.objects
            .filter(Q(user=user) | Q(email=user.email))
            .select_related('product', 'verification_token')
            .prefetch_related('replies', 'payments')
            .order_by('-created_at')[:limit]
        )

        return [_format_quote(q) for q in quotes_qs]

    except Exception as exc:
        logger.error('Error in get_quote_information for user %s: %s', user.id, exc)
        return [] if quote_id is None else None


# ── Payment Status Service ────────────────────────────────────────────────────

def get_payment_status(
    user: User,
    quote_id: Optional[int] = None,
    order_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve real-time payment status for a specific quote or order.
    """
    if quote_id:
        quote = get_quote_information(user, quote_id=quote_id)
        if not quote or isinstance(quote, list):
            return {'found': False, 'error': f"Quote #{quote_id} not found for this account."}

        return {
            'found': True,
            'entity_type': 'quote',
            'quote_id': quote_id,
            'quote_status': quote['status'],
            'is_paid': quote['is_paid'],
            'quoted_total_price': quote['quoted_total_price'],
            'payments': quote['payments'],
        }

    if order_number:
        from app.models import Order
        order = Order.objects.filter(Q(user=user) | Q(shipping_email=user.email), order_number=order_number).prefetch_related('payment').first()
        if not order:
            return {'found': False, 'error': f"Order #{order_number} not found for this account."}

        payment_status = 'pending'
        txn_id = None
        amount = order.total_amount
        try:
            if hasattr(order, 'payment') and order.payment:
                payment_status = order.payment.status
                txn_id = order.payment.transaction_id
                amount = order.payment.amount
        except Exception:
            pass

        return {
            'found': True,
            'entity_type': 'order',
            'order_number': order.order_number,
            'order_status': order.status,
            'payment_status': payment_status,
            'payment_method': order.payment_method,
            'transaction_id': txn_id,
            'total_amount': Decimal(str(amount)),
            'advance_paid': Decimal(str(order.advance_paid)),
            'balance_due': Decimal(str(order.balance_due)),
        }

    all_quotes = get_quote_information(user, limit=10)
    all_orders = get_customer_orders(user, limit=10)

    return {
        'found': True,
        'recent_orders_count': len(all_orders),
        'recent_quotes_count': len(all_quotes) if isinstance(all_quotes, list) else 0,
        'orders': all_orders,
        'quotes': all_quotes,
    }
