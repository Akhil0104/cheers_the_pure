"""
DispatchAI Business Workflow Tools & Safe Function Execution Layer.

Provides deterministic, safe backend tools for:
1. search_product(query, category)
2. get_current_price(product_identifier)
3. get_customer_order_history(user, limit)
4. get_quote_status(user, quote_id)
5. get_payment_status(user, quote_id, order_number)
6. create_quote_request(user, product_identifier, quantity, ...)
7. prepare_order_request(user, items, shipping_address, payment_method, ...)
8. check_delivery_preference(user)
9. summarize_customer_requirements(user, conversation_history)

STRICT SAFETY & ARCHITECTURAL RULES:
- The LLM NEVER directly modifies database records.
- All write operations (quotes, orders, discounts, contractual terms) MUST pass
  through backend validation and require explicit confirmation.
- The agent explains what action it proposes before executing sensitive changes.
- Every important action is recorded in the AgentActionLog audit trail.
"""

import json
import logging
from decimal import Decimal
from typing import Any, Dict, List, Optional, Tuple, Union

from django.contrib.auth.models import User
from django.utils import timezone

from app.models import (
    Category,
    Inventory,
    Order,
    OrderItem,
    Product,
    QuoteRequest,
    UserProfile,
)
from dispatch.models import AgentActionLog, ConversationSession
from dispatch.services.catalog_service import (
    get_available_inventory,
    get_current_price as db_get_current_price,
    get_customer_orders as db_get_customer_orders,
    get_payment_status as db_get_payment_status,
    get_product_information as db_get_product_information,
    get_quote_information as db_get_quote_information,
)
from dispatch.services.hindsight_service import (
    normalize_buyer_id,
    recall_customer_memory,
)

logger = logging.getLogger(__name__)


# ── Tool 1: Search Product Catalog ────────────────────────────────────────────

def search_product(query: str = "", category: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Search available products in the Cheers the Pure catalog strictly from SQL database.
    """
    all_products = db_get_product_information()
    if not isinstance(all_products, list):
        return []

    q_lower = (query or "").strip().lower()
    cat_lower = (category or "").strip().lower()

    filtered = []
    for p in all_products:
        p_name = p['name'].lower()
        p_cap = p['capacity'].lower()
        p_cat = p['category'].lower()

        match_query = (not q_lower) or (q_lower in p_name or q_lower in p_cap or q_lower in p_cat)
        match_cat = (not cat_lower) or (cat_lower in p_cat)

        if match_query and match_cat:
            filtered.append(p)

    return filtered


# ── Tool 2: Get Current Price ─────────────────────────────────────────────────

def get_current_price(product_identifier: Union[int, str]) -> Optional[Decimal]:
    """
    Retrieve authoritative unit price strictly from the database.
    Returns None if the product does not exist (prevents hallucination).
    """
    return db_get_current_price(product_identifier)


# ── Tool 3: Get Customer Order History ────────────────────────────────────────

def get_customer_order_history(user: User, limit: int = 10) -> List[Dict[str, Any]]:
    """
    Retrieve real-time order history for an authenticated distributor.
    """
    return db_get_customer_orders(user=user, limit=limit)


# ── Tool 4: Get Quote Status ──────────────────────────────────────────────────

def get_quote_status(user: User, quote_id: Optional[int] = None) -> Union[List[Dict[str, Any]], Optional[Dict[str, Any]]]:
    """
    Retrieve wholesale quote requests and official replies for an authenticated distributor.
    """
    return db_get_quote_information(user=user, quote_id=quote_id)


# ── Tool 5: Get Payment Status ────────────────────────────────────────────────

def get_payment_status(
    user: User,
    quote_id: Optional[int] = None,
    order_number: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve verified payment transaction status for quotes and orders.
    """
    return db_get_payment_status(user=user, quote_id=quote_id, order_number=order_number)


# ── Tool 6: Create Quote Request (Two-Phase / Safe Write) ──────────────────────

def create_quote_request(
    user: User,
    product_identifier: Union[int, str],
    quantity: int,
    preferred_delivery_timing: str = "",
    delivery_address: str = "",
    details: str = "",
    confirmed: bool = False,
    session: Optional[ConversationSession] = None,
) -> Dict[str, Any]:
    """
    Create a formal B2B wholesale quotation request with two-phase confirmation.

    If confirmed=False:
        Validates inputs, generates an Action Proposal explaining the quote details,
        and logs status 'proposed' in AgentActionLog.
    If confirmed=True:
        Executes the validated write to QuoteRequest, logs status 'executed',
        and returns the created quote record.
    """
    buyer_id_str = normalize_buyer_id(user)

    # 1. Product Validation
    prod_info = db_get_product_information(product_identifier)
    if not prod_info or not isinstance(prod_info, dict):
        return {
            "success": False,
            "error": f"Product '{product_identifier}' does not exist in our catalog. Cannot create quotation.",
            "is_proposal": False,
        }

    try:
        qty = int(quantity)
        if qty <= 0:
            raise ValueError()
    except (ValueError, TypeError):
        return {
            "success": False,
            "error": "Quantity must be a positive integer.",
            "is_proposal": False,
        }

    # MOQ Check (Wholesale MOQ standard: 100 units)
    if qty < 100:
        return {
            "success": False,
            "error": f"Minimum Order Quantity (MOQ) for wholesale quotes is 100 units. Requested quantity: {qty}.",
            "is_proposal": False,
        }

    # Fetch product instance
    p_instance = Product.objects.filter(id=prod_info['id']).first()
    if not p_instance:
        return {"success": False, "error": "Product record could not be loaded."}

    unit_price = prod_info['price']
    estimated_total = unit_price * Decimal(str(qty))
    trays = qty // prod_info['units_per_tray']

    proposal_text = (
        f"I propose submitting a formal wholesale quote request for {qty} units "
        f"({trays} trays) of {prod_info['name']} at catalog baseline ₹{unit_price}/unit "
        f"(estimated total: ₹{estimated_total:,.2f}). "
        f"Delivery: {preferred_delivery_timing or 'Standard schedule'} to {delivery_address or 'Registered address'}."
    )

    action_data = {
        "product_id": p_instance.id,
        "product_name": p_instance.name,
        "quantity": qty,
        "estimated_unit_price": str(unit_price),
        "estimated_total": str(estimated_total),
        "preferred_delivery_timing": preferred_delivery_timing,
        "delivery_address": delivery_address,
        "details": details,
    }

    # Stage 1: Action Proposal (requires user confirmation)
    if not confirmed:
        log = AgentActionLog.objects.create(
            user=user,
            buyer_id=buyer_id_str,
            session=session,
            action_type='create_quote_request',
            status='proposed',
            is_sensitive=True,
            requires_confirmation=True,
            proposal_explanation=proposal_text,
            action_data=action_data,
        )
        return {
            "success": True,
            "is_proposal": True,
            "requires_confirmation": True,
            "proposal_id": log.id,
            "explanation": proposal_text,
            "action_data": action_data,
            "message": "Quotation request proposal generated. Please confirm to submit.",
        }

    # Stage 2: Executed Write (upon explicit confirmation)
    profile = getattr(user, 'profile', None)
    company_name = profile.company_name if profile else ''
    resolved_address = delivery_address or (profile.address if profile else '')

    quote = QuoteRequest.objects.create(
        user=user,
        product=p_instance,
        size=p_instance.capacity,
        quantity=qty,
        name=f"{user.first_name} {user.last_name}".strip() or user.username,
        email=user.email,
        company=company_name,
        preferred_delivery_timing=preferred_delivery_timing,
        delivery_address=resolved_address,
        details=details,
        status='pending',
    )

    result_data = {
        "quote_id": quote.id,
        "created_at": quote.created_at.strftime("%Y-%m-%d %H:%M"),
        "status": quote.status,
    }

    AgentActionLog.objects.create(
        user=user,
        buyer_id=buyer_id_str,
        session=session,
        action_type='create_quote_request',
        status='executed',
        is_sensitive=True,
        requires_confirmation=False,
        confirmed_by_user=True,
        confirmed_at=timezone.now(),
        proposal_explanation=proposal_text,
        action_data=action_data,
        result_data=result_data,
    )

    return {
        "success": True,
        "is_proposal": False,
        "quote_id": quote.id,
        "status": quote.status,
        "message": f"Quotation request #{quote.id} successfully created and submitted for administrative review.",
        "quote": db_get_quote_information(user=user, quote_id=quote.id),
    }


# ── Tool 7: Prepare Order Request (Sensitive Write Operation) ─────────────────

def prepare_order_request(
    user: User,
    items: List[Dict[str, Any]],
    shipping_address: str,
    payment_method: str = "cod",
    delivery_fee: Decimal = Decimal('0.00'),
    confirmed: bool = False,
    session: Optional[ConversationSession] = None,
) -> Dict[str, Any]:
    """
    Prepare or place a wholesale B2B order with strict backend validation.

    SENSITIVE OPERATION:
    Placing an order creates financial liability and inventory reservations.
    Requires explicit user confirmation before writing to the database.
    """
    buyer_id_str = normalize_buyer_id(user)

    if not items or not isinstance(items, list):
        return {"success": False, "error": "Order items list is required."}

    validated_items = []
    subtotal = Decimal('0.00')

    for raw_item in items:
        prod_id = raw_item.get('product_id') or raw_item.get('id') or raw_item.get('product')
        p_info = db_get_product_information(prod_id)
        if not p_info or not isinstance(p_info, dict):
            return {"success": False, "error": f"Product '{prod_id}' not found in catalog."}

        try:
            qty = int(raw_item.get('quantity', 0))
            if qty <= 0:
                raise ValueError()
        except (ValueError, TypeError):
            return {"success": False, "error": f"Invalid quantity for product {p_info['name']}."}

        # Check stock availability
        stock = p_info.get('stock_quantity')
        if stock is not None and stock < qty:
            return {
                "success": False,
                "error": f"Insufficient stock for {p_info['name']}. Available: {stock} units, requested: {qty}.",
            }

        unit_price = p_info['price']
        line_total = unit_price * Decimal(str(qty))
        subtotal += line_total

        validated_items.append({
            "product_id": p_info['id'],
            "product_name": p_info['name'],
            "unit_price": unit_price,
            "quantity": qty,
            "line_total": line_total,
        })

    total_amount = subtotal + Decimal(str(delivery_fee))

    # Payment split calculation (COD: 30% advance, 70% on delivery)
    if payment_method == 'cod':
        advance_required = (total_amount * Decimal('0.30')).quantize(Decimal('0.01'))
        balance_due = total_amount - advance_required
    else:
        advance_required = total_amount
        balance_due = Decimal('0.00')

    profile = getattr(user, 'profile', None)
    shipping_addr = shipping_address.strip() or (profile.address if profile else "")
    if not shipping_addr:
        return {"success": False, "error": "Shipping address is required to prepare order."}

    proposal_text = (
        f"I have prepared an order request for {len(validated_items)} item(s) "
        f"totaling ₹{total_amount:,.2f} (Subtotal: ₹{subtotal:,.2f}, Delivery: ₹{delivery_fee}). "
        f"Payment terms: {payment_method.upper()} (Advance payable: ₹{advance_required:,.2f}, Balance due: ₹{balance_due:,.2f}). "
        f"Shipping destination: {shipping_addr}."
    )

    action_data = {
        "items": [
            {
                "product_id": it["product_id"],
                "product_name": it["product_name"],
                "unit_price": str(it["unit_price"]),
                "quantity": it["quantity"],
                "line_total": str(it["line_total"]),
            }
            for it in validated_items
        ],
        "subtotal": str(subtotal),
        "delivery_fee": str(delivery_fee),
        "total_amount": str(total_amount),
        "payment_method": payment_method,
        "advance_required": str(advance_required),
        "balance_due": str(balance_due),
        "shipping_address": shipping_addr,
    }

    # Stage 1: Proposal (requires explicit confirmation)
    if not confirmed:
        log = AgentActionLog.objects.create(
            user=user,
            buyer_id=buyer_id_str,
            session=session,
            action_type='prepare_order_request',
            status='proposed',
            is_sensitive=True,
            requires_confirmation=True,
            proposal_explanation=proposal_text,
            action_data=action_data,
        )
        return {
            "success": True,
            "is_proposal": True,
            "requires_confirmation": True,
            "proposal_id": log.id,
            "explanation": proposal_text,
            "action_data": action_data,
            "message": "Order request prepared. Please confirm to execute order creation.",
        }

    # Stage 2: Confirmed Execution
    order_num = Order.generate_order_number()
    order = Order.objects.create(
        user=user,
        order_number=order_num,
        shipping_name=f"{user.first_name} {user.last_name}".strip() or user.username,
        shipping_email=user.email,
        shipping_phone=profile.phone if profile else "",
        shipping_address=shipping_addr,
        shipping_city=profile.city if profile else "Hyderabad",
        shipping_state=profile.state if profile else "Telangana",
        shipping_postal_code=profile.postal_code if profile else "500001",
        total_amount=total_amount,
        delivery_fee=delivery_fee,
        payment_method=payment_method,
        advance_paid=Decimal('0.00'),  # Pending actual payment transaction
        balance_due=total_amount,
        status='pending',
    )
    order.ensure_invoice_token()
    order.save(update_fields=['invoice_token'])

    for it in validated_items:
        p_obj = Product.objects.filter(id=it['product_id']).first()
        OrderItem.objects.create(
            order=order,
            product=p_obj,
            product_name=it['product_name'],
            product_price=it['unit_price'],
            quantity=it['quantity'],
        )

    result_data = {
        "order_number": order.order_number,
        "order_id": order.id,
        "status": order.status,
        "invoice_token": order.invoice_token,
    }

    AgentActionLog.objects.create(
        user=user,
        buyer_id=buyer_id_str,
        session=session,
        action_type='prepare_order_request',
        status='executed',
        is_sensitive=True,
        requires_confirmation=False,
        confirmed_by_user=True,
        confirmed_at=timezone.now(),
        proposal_explanation=proposal_text,
        action_data=action_data,
        result_data=result_data,
    )

    return {
        "success": True,
        "is_proposal": False,
        "order_number": order.order_number,
        "total_amount": str(total_amount),
        "status": order.status,
        "message": f"Order {order.order_number} has been created and logged in the database.",
    }


# ── Tool 8: Check Delivery Preference ─────────────────────────────────────────

def check_delivery_preference(user: User) -> Dict[str, Any]:
    """
    Inspect delivery preferences and warehouse restrictions by combining
    Hindsight persistent memory with UserProfile database records.
    """
    buyer_id_str = normalize_buyer_id(user)
    memories = recall_customer_memory(buyer_id=buyer_id_str, query="delivery timing warehouse restriction schedule")

    profile = getattr(user, 'profile', None)

    return {
        "buyer_id": buyer_id_str,
        "registered_address": profile.address if profile else "",
        "city": profile.city if profile else "Hyderabad",
        "state": profile.state if profile else "Telangana",
        "gstin": profile.gstin if profile else "",
        "logistics_memories": memories,
    }


# ── Tool 9: Summarize Customer Requirements ───────────────────────────────────

def summarize_customer_requirements(
    user: User,
    conversation_history: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Assemble a comprehensive distributor operational profile summarizing past orders,
    active quotes, preferences, and delivery constraints.
    """
    buyer_id_str = normalize_buyer_id(user)
    profile = getattr(user, 'profile', None)

    orders = db_get_customer_orders(user=user, limit=5)
    quotes = db_get_quote_information(user=user, limit=5)
    memories = recall_customer_memory(buyer_id=buyer_id_str, query="all preferences restrictions", limit=10)

    return {
        "buyer_id": buyer_id_str,
        "company_name": profile.company_name if profile else "",
        "account_type": profile.account_type if profile else "b2b",
        "recent_orders_count": len(orders),
        "recent_quotes_count": len(quotes) if isinstance(quotes, list) else 0,
        "orders_summary": [
            f"{o['order_number']}: ₹{o['total_amount']} ({o['status_display']})"
            for o in orders
        ],
        "quotes_summary": [
            f"Quote #{q['id']}: {q['quantity']} units ({q['status_display']})"
            for q in (quotes if isinstance(quotes, list) else [])
        ],
        "remembered_preferences": [
            m.get('content', str(m)) for m in memories
        ],
    }
