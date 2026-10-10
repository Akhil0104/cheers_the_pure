"""Validated examples for the SaaSsum AI site schema."""

from copy import deepcopy
from uuid import UUID

from .schemas import SiteSchema


CHEERSTHEPURE_EXAMPLE = {
    "schema_version": "1.0",
    "site_id": "4b47c1df-4ff9-4db5-8053-760f4e3bf431",
    "site_name": "CheersThePure",
    "business_type": "packaged drinking water",
    "brand": {
        "name": "CheersThePure",
        "logo_text": "CHEERS THE PURE",
    },
    "theme": {
        "color": "cyan",
        "surface": "light",
    },
    "sections": [
        {
            "id": "hero-main",
            "type": "hero",
            "headline": "Refreshment for every part of your day",
            "subheadline": "Packaged drinking water in convenient sizes for home, work, and business supply.",
            "cta_text": "Request a wholesale inquiry",
            "cta_action": "submit_b2b_inquiry",
            "image_url": None,
            "theme_color": "blue",
        },
        {
            "id": "features-purity",
            "type": "features",
            "title": "A dependable choice for everyday hydration",
            "subtitle": "Clear product information and practical formats for different needs.",
            "items": [
                {
                    "icon": "droplet",
                    "title": "Everyday hydration",
                    "description": "A straightforward option for everyday drinking-water needs.",
                },
                {
                    "icon": "package-check",
                    "title": "Useful bottle sizes",
                    "description": "Choose compact, personal, and larger formats for your setting.",
                },
                {
                    "icon": "users",
                    "title": "Business inquiries",
                    "description": "Businesses can share their requirements through the wholesale inquiry form.",
                },
            ],
        },
        {
            "id": "products-water",
            "type": "product_grid",
            "title": "Explore the bottle range",
            "items": [
                {
                    "name": "Sport",
                    "capacity": "250 ml",
                    "description": "A compact format for a quick refreshment.",
                    "image_url": None,
                    "badge": "Compact",
                    "data_source": "sample",
                    "price": None,
                },
                {
                    "name": "Daily",
                    "capacity": "500 ml",
                    "description": "A convenient format for everyday use.",
                    "image_url": None,
                    "badge": None,
                    "data_source": "sample",
                    "price": None,
                },
                {
                    "name": "Premium",
                    "capacity": "1 L",
                    "description": "A larger bottle format for longer days.",
                    "image_url": None,
                    "badge": None,
                    "data_source": "sample",
                    "price": None,
                },
                {
                    "name": "Corporate",
                    "capacity": "2 L",
                    "description": "A high-capacity format for shared settings.",
                    "image_url": None,
                    "badge": "Large format",
                    "data_source": "sample",
                    "price": None,
                },
            ],
        },
        {
            "id": "quote-wholesale",
            "type": "quote_form",
            "title": "Request a B2B wholesale inquiry",
            "subtitle": "Share your requirements and the team can follow up about supply options.",
            "fields": [
                {"name": "name", "label": "Name", "required": True},
                {"name": "email", "label": "Email", "required": True},
                {"name": "company", "label": "Company", "required": True},
                {"name": "capacity", "label": "Bottle capacity", "required": True},
                {"name": "quantity", "label": "Quantity", "required": True},
                {"name": "details", "label": "Details (optional)", "required": False},
            ],
            "submit_button_text": "Send inquiry",
            "action": "submit_b2b_inquiry",
        },
        {
            "id": "footer-main",
            "type": "footer",
            "company_name": "CheersThePure",
            "copyright": "Copyright 2026 CheersThePure.",
            "links": [
                {"label": "Products", "url": "/products/"},
                {"label": "Wholesale inquiry", "url": "/order/"},
            ],
        },
    ],
}


def get_cheersthepure_example() -> dict:
    """Return a fresh JSON-compatible copy of the sample payload."""
    return deepcopy(CHEERSTHEPURE_EXAMPLE)


def validated_cheersthepure_example() -> SiteSchema:
    """Parse the sample through the strict schema before use."""
    return SiteSchema.model_validate(get_cheersthepure_example())


def example_site_id() -> UUID:
    """Return the sample site's stable UUID."""
    return UUID(CHEERSTHEPURE_EXAMPLE["site_id"])