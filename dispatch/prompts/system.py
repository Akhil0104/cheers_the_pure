"""
System prompt assembly for DispatchAI.

Builds a layered system prompt from:
1. Agent identity and role
2. Active business rules (from DB)
3. Current database context (user, products, orders, inventory)
4. Hindsight memories for this user
5. Response format guidelines
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    pass


# ── Layer 1: Identity ─────────────────────────────────────────────────────────

IDENTITY = """\
DispatchAI is the B2B Supply & Distribution Assistant for CheersthePure — a premier packaged \
water manufacturing & distribution company based in Hyderabad, Telangana, India.

Your primary mission is B2B supply chain enablement, commercial distribution assistance, \
and account management for wholesale buyers, regional beverage distributors, corporate accounts, \
hotels, and retail partners.

CORE B2B RESPONSIBILITIES:
1. Understanding distributor requests accurately and professionally.
2. Remembering customer preferences, logistics constraints, and site requirements across sessions.
3. Assisting with recurring orders, weekly/monthly delivery rhythms, and scheduled bulk replenishment.
4. Helping with delivery requirements (lead times, shipping distances from Hyderabad HQ, dispatch schedules, tailgate offloading).
5. Explaining current product information and tray packaging:
   * 250 ml: 1 tray = 18 pieces
   * 500 ml: 1 tray = 18 bottles
   * 1000 ml (1 Ltr): 1 tray = 12 bottles
   * 2 litres: 1 tray = 6 bottles
6. Assisting with quotes, wholesale pricing structures, and formal quotation submissions.
7. Using previous business context recalled from memory to provide personalized distribution service.
8. Proactively identifying conflicts between current requests and remembered constraints \
   (e.g., if a buyer requests 2:00 PM delivery but remembered warehouse restrictions state \
   "cannot receive deliveries before 4 PM", politely point out the conflict and suggest 4:00 PM).

STRICT NEGATIVE CONSTRAINTS (YOU MUST NEVER):
- Never invent discounts or custom pricing not backed by active business rules or live database catalog.
- Never invent contracts, agreements, or unauthorized commercial terms.
- Never invent payment confirmations or transaction statuses.
- Never invent inventory availability when items are out of stock.
- Never claim an order was placed unless the backend database confirms it.
- Never claim a payment succeeded unless the payment system/database confirms it.
- Never provide unsupported business commitments or guarantees.
- If information is unavailable or unconfirmed, clearly state that you need confirmation from the CheersthePure sales desk (cheersthepure@gmail.com).
- Keep the conversation strictly focused on B2B business assistance rather than generic chit-chat.
"""

# ── Layer 5: Response guidelines ──────────────────────────────────────────────

RESPONSE_GUIDELINES = """\
RESPONSE GUIDELINES & ANTI-HALLUCINATION RULES:
- Communicate as a professional distribution executive: direct, commercially grounded, and actionable.
- Strict Catalog Grounding: You must ONLY quote products, capacities, and unit prices present in CURRENT PRODUCT CATALOG above.
- Zero-Hallucination on Unlisted Products: If the user asks about an item or size NOT in CURRENT PRODUCT CATALOG (e.g., 20L jars, unlisted flavors/sizes), you MUST state clearly that Cheers the Pure does not offer this product and never invent or guess a price.
- Exact Figures: Always quote exact numbers: price in ₹ per unit and estimated total, quantity in units/trays, and delivery timelines in business days.
- When a buyer requests a quote, summarize: SKU, total volume (and equivalent trays), unit price, total estimated cost, and estimated delivery window.
- Always check inventory before confirming bulk availability. If stock is low, offer immediate split delivery or alternative SKUs.
- Constraint Conflict Resolution: If the buyer asks for terms conflicting with remembered constraints, politely highlight the remembered constraint and offer a compliant solution.
- Next Steps: If a proposed deal complies with business rules, invite the distributor to submit or confirm the formal quote: "Would you like me to note this quotation request for our distribution desk?"
- Maintain complete documentation integrity and never invent pricing, discounts, delivery dates, or payment statuses not backed by real data.
"""


# ── Prompt Builder ────────────────────────────────────────────────────────────

def build_system_prompt(
    context: dict,
    business_rules: list[str],
) -> str:
    """
    Assemble the full system prompt for a DispatchAI conversation turn.

    Args:
        context:        Output of context_builder.build() — DB + memory data.
        business_rules: List of plain-English rule strings from BusinessRule model.

    Returns:
        A complete system prompt string ready to be sent to Groq as role=system.
    """
    parts = [IDENTITY]

    # ── Business Rules ──
    if business_rules:
        rules_block = '\n'.join(f'  • {r}' for r in business_rules)
        parts.append(
            f'BUSINESS RULES YOU MUST ALWAYS FOLLOW:\n{rules_block}\n'
            'Never violate these rules even if the buyer requests it. '
            'If a request violates a rule, explain the constraint politely and offer the nearest valid alternative.'
        )

    # ── User / Account Context ──
    user_info = context.get('user', {})
    if user_info:
        parts.append(
            f'BUYER ACCOUNT:\n'
            f'  Name: {user_info.get("name", "Unknown")}\n'
            f'  Email: {user_info.get("email", "")}\n'
            f'  Company: {user_info.get("company_name", "Not specified")}\n'
            f'  Industry: {user_info.get("industry", "Not specified")}\n'
            f'  Account type: {user_info.get("account_type", "b2b").upper()} — '
            f'{user_info.get("role_display", "Distributor")}'
        )

    # ── Product Catalog ──
    products = context.get('products', [])
    if products:
        prod_lines = []
        for p in products:
            stock_note = ''
            stock = p.get('stock')
            if stock is not None:
                if stock == 0:
                    stock_note = ' [OUT OF STOCK]'
                elif stock < 50:
                    stock_note = f' [LOW STOCK: {stock} units]'
                else:
                    stock_note = f' [{stock} units in stock]'
            prod_lines.append(
                f'  • {p["name"]} ({p["capacity"]}) — ₹{p["price"]}/unit{stock_note}'
            )
        parts.append('CURRENT PRODUCT CATALOG:\n' + '\n'.join(prod_lines))

    # ── Order History ──
    orders = context.get('order_history', [])
    if orders:
        order_lines = []
        for o in orders[:5]:  # Last 5 only to keep prompt concise
            order_lines.append(
                f'  • {o.get("order_number", "N/A")} | '
                f'{o.get("date", "")} | '
                f'₹{o.get("total", "?")} | '
                f'Status: {o.get("status", "?").title()}'
            )
        parts.append('BUYER\'S RECENT ORDER HISTORY:\n' + '\n'.join(order_lines))

    # ── Quote History ──
    quotes = context.get('quote_history', [])
    if quotes:
        quote_lines = []
        for q in quotes[:5]:
            quote_lines.append(
                f'  • Quote #{q.get("id", "?")} | '
                f'{q.get("product", "?")} × {q.get("quantity", "?")} units | '
                f'Status: {q.get("status", "?").title()} | '
                f'{q.get("date", "")}'
            )
        parts.append('BUYER\'S RECENT QUOTE HISTORY:\n' + '\n'.join(quote_lines))

    # ── Delivery Info ──
    delivery = context.get('delivery_info', {})
    if delivery:
        parts.append(
            f'DELIVERY INFORMATION:\n'
            f'  Warehouse location: {delivery.get("warehouse_city", "Hyderabad")}\n'
            f'  Delivery zones: {delivery.get("zones", "India-wide")}\n'
            f'  Fee structure: {delivery.get("fee_structure", "Free ≤1km | ₹10/km (1-5km) | ₹15/km (>5km)")}'
        )

    # ── Hindsight Memories ──
    memories = context.get('memories', [])
    if memories:
        memory_lines = []
        for m in memories:
            if isinstance(m, dict):
                content = m.get('content', str(m))
                category = m.get('category', '')
                cat_tag = f' [{category}]' if category else ''
                memory_lines.append(f'  • {content}{cat_tag}')
            else:
                memory_lines.append(f'  • {m}')
        parts.append(
            'WHAT YOU KNOW ABOUT THIS BUYER (from past conversations):\n'
            + '\n'.join(memory_lines)
            + '\nUse these memories to personalise your response where relevant.'
        )
    else:
        parts.append(
            'BUYER HISTORY: No previous conversation context available. '
            'This may be a new buyer or their first conversation with DispatchAI.'
        )

    # ── Unavailability notices ──
    if context.get('products_unavailable'):
        parts.append(
            'NOTICE: Product catalog data is temporarily unavailable. '
            'Do not quote specific prices or confirm stock levels. '
            'Tell the buyer the catalog is briefly unavailable and ask them to try again in a few minutes, '
            'or direct them to cheersthepure@gmail.com.'
        )

    if context.get('memories_unavailable'):
        parts.append(
            'NOTICE: Buyer conversation history could not be retrieved this turn. '
            'Proceed without personalisation.'
        )

    # ── Response Format ──
    parts.append(RESPONSE_GUIDELINES)

    return '\n\n'.join(parts)
