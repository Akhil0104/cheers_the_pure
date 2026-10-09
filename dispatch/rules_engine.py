"""
Business Rules Engine for DispatchAI.

Validates AI-generated responses against active BusinessRules
before they are returned to the user.

Each rule type has a specific validator function that:
- Returns (True, None)        if the response passes the rule
- Returns (False, correction) if the rule is violated, with a
  correction message to append to the response
"""

import logging
import re
from decimal import Decimal, InvalidOperation

logger = logging.getLogger(__name__)


# ── Rule Validators ───────────────────────────────────────────────────────────

def _extract_price_from_response(text: str) -> list[Decimal]:
    """Extract all ₹X or ₹X.XX price mentions from AI response text."""
    prices = []
    # Match patterns like ₹4.50, ₹500, ₹4,500
    for match in re.finditer(r'₹\s*([\d,]+(?:\.\d{1,2})?)', text):
        try:
            val = Decimal(match.group(1).replace(',', ''))
            prices.append(val)
        except InvalidOperation:
            pass
    return prices


def _extract_quantities_from_response(text: str) -> list[int]:
    """Extract explicit quantity mentions (e.g. '500 units', '200 bottles')."""
    quantities = []
    for match in re.finditer(r'\b(\d+)\s*(?:units?|bottles?|pieces?|pcs)\b', text, re.IGNORECASE):
        try:
            quantities.append(int(match.group(1)))
        except ValueError:
            pass
    return quantities


def validate_moq(response_text: str, parameters: dict) -> tuple[bool, str | None]:
    """Minimum Order Quantity check."""
    min_qty = parameters.get('min_qty', 100)
    quantities = _extract_quantities_from_response(response_text)

    # Only flag if a specific quantity is mentioned AND it's below MOQ
    for qty in quantities:
        if qty < min_qty:
            return (
                False,
                f'\n\n⚠️ Please note: Our minimum order quantity for wholesale/B2B orders is '
                f'{min_qty} units. I\'ve adjusted the quote to the minimum.'
            )
    return True, None


def validate_price_floor(response_text: str, parameters: dict) -> tuple[bool, str | None]:
    """Price floor check — no AI-suggested price should go below the floor."""
    min_price = Decimal(str(parameters.get('min_price', 3.00)))
    category_filter = parameters.get('product_category', 'all')

    prices = _extract_price_from_response(response_text)

    # Check per-unit prices (heuristic: values below ₹100 are likely per-unit)
    unit_prices = [p for p in prices if p < Decimal('100')]

    for price in unit_prices:
        if price < min_price:
            return (
                False,
                f'\n\n⚠️ Note: The minimum wholesale price is ₹{min_price}/unit. '
                f'I\'ve corrected the quote accordingly.'
            )
    return True, None


def validate_max_discount(response_text: str, parameters: dict) -> tuple[bool, str | None]:
    """Maximum discount percentage check."""
    max_pct = parameters.get('max_pct', 15)

    # Look for discount mentions like "20% off", "25 percent discount"
    for match in re.finditer(
        r'\b(\d+(?:\.\d+)?)\s*%\s*(?:off|discount|reduction|concession)\b',
        response_text,
        re.IGNORECASE,
    ):
        try:
            pct = float(match.group(1))
            if pct > max_pct:
                return (
                    False,
                    f'\n\n⚠️ Note: The maximum discount I can offer is {max_pct}%. '
                    f'I\'ve adjusted accordingly.'
                )
        except ValueError:
            pass
    return True, None


def validate_delivery_zone(response_text: str, parameters: dict) -> tuple[bool, str | None]:
    """Check if mentioned delivery locations are in allowed zones."""
    allowed_states = parameters.get('allowed_states', [])
    if not allowed_states:
        return True, None  # No restriction configured

    restricted_regions = parameters.get('restricted_regions', [])
    for region in restricted_regions:
        if region.lower() in response_text.lower():
            return (
                False,
                f'\n\n⚠️ Note: Delivery to {region} is not currently available. '
                f'Please contact cheersthepure@gmail.com for international or restricted zone orders.'
            )
    return True, None


# ── Registry ──────────────────────────────────────────────────────────────────

_VALIDATORS = {
    'moq': validate_moq,
    'price_floor': validate_price_floor,
    'max_discount_pct': validate_max_discount,
    'delivery_zone': validate_delivery_zone,
    # price_ceiling and inventory_threshold are enforced via system prompt context
    # (the AI sees inventory and is instructed not to quote out-of-stock items)
}


# ── Main Validation Entry Point ────────────────────────────────────────────────

def validate_response(
    response_text: str,
    context: dict,
) -> tuple[str, list[str]]:
    """
    Validate the AI response against all active BusinessRules.

    Args:
        response_text: Raw AI response string.
        context:       DB context dict (from context_builder.build).

    Returns:
        (final_response, rules_applied)
        - final_response:  Response text, possibly with correction appended
        - rules_applied:   List of rule names that triggered
    """
    try:
        from dispatch.models import BusinessRule
        active_rules = BusinessRule.objects.filter(is_active=True).order_by('-priority')
    except Exception as exc:
        logger.warning('Could not load BusinessRules for validation: %s', exc)
        return response_text, []

    final_text = response_text
    rules_applied = []

    for rule in active_rules:
        validator = _VALIDATORS.get(rule.rule_type)
        if not validator:
            continue  # Custom / prompt-only rules — already in system prompt

        try:
            passed, correction = validator(final_text, rule.parameters)
            if not passed and correction:
                final_text += correction
                rules_applied.append(rule.name)
                logger.info(
                    'BusinessRule "%s" (%s) triggered correction.',
                    rule.name, rule.rule_type,
                )
        except Exception as exc:
            logger.warning('Rule validation error for "%s": %s', rule.name, exc)

    return final_text, rules_applied
