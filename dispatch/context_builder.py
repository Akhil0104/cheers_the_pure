"""
Context Builder for DispatchAI.

Assembles the full context dict passed to the system prompt builder.
Reads ONLY from existing app/ models — never writes.
Also merges in Hindsight memories.

Returns a standardised context dict:
{
    "user":              { name, email, company_name, industry, account_type, role_display },
    "products":          [ { name, capacity, price, stock, is_featured } ],
    "order_history":     [ { order_number, date, total, status, items } ],
    "quote_history":     [ { id, product, quantity, status, date } ],
    "delivery_info":     { warehouse_city, zones, fee_structure },
    "memories":          [ hindsight memory dicts ],
    "products_unavailable":  bool,
    "memories_unavailable":  bool,
}
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User

from .services import recall_customer_memory

logger = logging.getLogger(__name__)


def build(
    user: User,
    user_message: str,
    recall_limit: int = 10,
) -> dict:
    """
    Build the full context dict for a DispatchAI inference turn.

    Args:
        user:         Authenticated Django User.
        user_message: Raw message text — used as Hindsight recall query.
        recall_limit: Max memories to recall.

    Returns:
        Context dict (see module docstring).
    """
    context = {
        'products_unavailable': False,
        'memories_unavailable': False,
    }

    # ── 1. User / Profile ─────────────────────────────────────────────────────
    try:
        from app.models import UserProfile
        profile = UserProfile.objects.select_related('user').get(user=user)
        context['user'] = {
            'buyer_id': profile.get_buyer_id(),
            'name': f'{user.first_name} {user.last_name}'.strip() or user.username,
            'email': user.email,
            'company_name': profile.company_name or '',
            'industry': profile.industry or '',
            'account_type': profile.account_type,
            'role': profile.role,
            'role_display': profile.get_role_display(),
            'phone': profile.phone or '',
            'address': profile.address or '',
            'city': profile.city or '',
            'state': profile.state or '',
            'postal_code': profile.postal_code or '',
            'gstin': profile.gstin or '',
        }
    except Exception as exc:
        logger.warning('Could not load UserProfile for user %d: %s', user.id, exc)
        context['user'] = {
            'buyer_id': f'DIST-{user.id:05d}',
            'name': user.username,
            'email': user.email,
            'company_name': '',
            'industry': '',
            'account_type': 'b2b',
            'role': 'distributor',
            'role_display': 'Distributor',
            'phone': '',
            'address': '',
            'city': '',
            'state': '',
            'postal_code': '',
            'gstin': '',
        }

    # ── 2. Product Catalog + Inventory (Authoritative Service) ────────────────
    try:
        from .services import get_product_information
        prods = get_product_information()
        context['products'] = [
            {
                'id': p['id'],
                'name': p['name'],
                'capacity': p['capacity'],
                'price': str(p['price']),
                'category': p['category'],
                'is_featured': p['is_featured'],
                'stock': p['stock_quantity'],
                'units_per_tray': p['units_per_tray'],
                'description': p['description'][:120] if p['description'] else '',
            }
            for p in prods
        ]
    except Exception as exc:
        logger.error('Could not load product catalog via service: %s', exc)
        context['products'] = []
        context['products_unavailable'] = True

    # ── 3. Order History (Authoritative Service) ──────────────────────────────
    try:
        from .services import get_customer_orders
        raw_orders = get_customer_orders(user=user, limit=10)
        context['order_history'] = [
            {
                'order_number': o['order_number'],
                'date': o['created_at'],
                'total': str(o['total_amount']),
                'status': o['status_display'],
                'payment_status': o['payment_status'],
                'items': ', '.join(f"{it['product_name']} ×{it['quantity']}" for it in o['items']),
            }
            for o in raw_orders
        ]
    except Exception as exc:
        logger.warning('Could not load order history via service for user %d: %s', user.id, exc)
        context['order_history'] = []

    # ── 4. Quote History (Authoritative Service) ──────────────────────────────
    try:
        from .services import get_quote_information
        raw_quotes = get_quote_information(user=user, limit=10)
        quote_history = []
        if isinstance(raw_quotes, list):
            for q in raw_quotes:
                quoted_price_str = f"₹{q['quoted_unit_price']}/unit" if q['quoted_unit_price'] is not None else 'Not yet quoted'
                quote_history.append({
                    'id': q['id'],
                    'product': q['product_name'],
                    'size': q['size'],
                    'quantity': q['quantity'],
                    'status': q['status_display'],
                    'preferred_delivery': q['preferred_delivery_timing'],
                    'date': q['created_at'],
                    'quoted_price': quoted_price_str,
                    'is_paid': q['is_paid'],
                })
        context['quote_history'] = quote_history
    except Exception as exc:
        logger.warning('Could not load quote history via service for user %d: %s', user.id, exc)
        context['quote_history'] = []


    # ── 5. Delivery Info ──────────────────────────────────────────────────────
    try:
        warehouse_lat = getattr(settings, 'WAREHOUSE_LAT', 17.3850)
        warehouse_lon = getattr(settings, 'WAREHOUSE_LON', 78.4867)
        tier1_rate = getattr(settings, 'DELIVERY_TIER1_RATE', 10)
        tier2_rate = getattr(settings, 'DELIVERY_TIER2_RATE', 15)
        free_km = getattr(settings, 'DELIVERY_FREE_KM', 1)
        tier1_max = getattr(settings, 'DELIVERY_TIER1_MAX_KM', 5)

        context['delivery_info'] = {
            'warehouse_city': 'Hyderabad',
            'warehouse_coords': f'{warehouse_lat}°N, {warehouse_lon}°E',
            'zones': 'India-wide (international on request)',
            'fee_structure': (
                f'Free within {free_km}km | '
                f'₹{tier1_rate}/km for {free_km}–{tier1_max}km | '
                f'₹{tier2_rate}/km beyond {tier1_max}km'
            ),
        }
    except Exception as exc:
        logger.warning('Could not load delivery config: %s', exc)
        context['delivery_info'] = {
            'warehouse_city': 'Hyderabad',
            'zones': 'India-wide',
            'fee_structure': 'Contact for delivery rates',
        }

    # ── 6. Hindsight Memories ─────────────────────────────────────────────────
    try:
        memories = recall_customer_memory(
            buyer_id=user,
            query=user_message,
            limit=recall_limit,
        )
        context['memories'] = memories
    except Exception as exc:
        logger.warning('Hindsight recall failed in context_builder: %s', exc)
        context['memories'] = []
        context['memories_unavailable'] = True

    return context


def get_active_business_rules() -> list[str]:
    """
    Load all active BusinessRule descriptions ordered by priority.
    Used to inject rules into the system prompt.
    """
    try:
        from dispatch.models import BusinessRule
        rules = (
            BusinessRule.objects
            .filter(is_active=True)
            .order_by('-priority', 'name')
            .values_list('description', flat=True)
        )
        return list(rules)
    except Exception as exc:
        logger.warning('Could not load business rules: %s', exc)
        return []
