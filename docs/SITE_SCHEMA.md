# SaaSsum AI Site Schema

`ai_builder.schemas.SiteSchema` is the versioned, strict Pydantic v2 contract for generated
SaaSsum AI websites. The project already requires `pydantic>=2.7,<3.0`, so no alternate
validation dependency is needed. A complete JSON document is limited to 100,000 UTF-8 bytes
in addition to per-field and per-collection limits.

## Contract

The root fields are `schema_version` (`"1.0"`), UUID `site_id`, `site_name`,
`business_type`, `brand`, `theme`, and `sections`. Theme color is one of `sky`, `cyan`,
`blue`, `emerald`, `violet`, `slate`, or `neutral`; surface is `light` or `dark`.

Sections use a discriminated `type` union: `hero`, `features`, `product_grid`, `quote_form`,
`footer`, `text_block`, or `testimonials`. These are the complete supported section types;
unknown types such as arbitrary HTML sections are rejected. Each section has a stable ID matching
`^[a-zA-Z][a-zA-Z0-9_-]{0,63}$`. A site has 1-12 sections and IDs must be unique. Unknown
properties are rejected at every model level.

Feature icons, hero actions, and quote form actions/fields are allowlisted. Features have 3-4
items; product grids have 1-12 items; quote forms have 1-6 unique fields; testimonial sections
have 1-8 items. Text has explicit maximum lengths. Image links must be HTTP(S) URLs. Footer
links must be HTTP(S) URLs or local absolute paths; protocol-relative paths are rejected.

Product items may optionally carry a `data_binding` with the exact shape
`{"source":"cheersthepure_catalog","entity":"product","key":"product_id|name|capacity","value":"..."}`.
This is only a constrained lookup request, not proof of catalog data. The server must resolve
the binding against `Product`/`Inventory` before marking an item
`data_source:"cheersthepure_database"` or attaching a price/stock value. Unknown binding
sources, entities, keys, fields, URLs, and executable values are rejected.

## Product Trust Boundary

Generated sample products use `data_source: "sample"` and must have `price: null`. A live
product uses `data_source: "cheersthepure_database"` and a `price` object with integer
`amount_minor` (paise for INR), currency, and source marker. Populate that price only by enriching the validated generated site
from trusted server-side catalog records. The marker is provenance metadata, not proof: never
trust an LLM or client to assert that it represents database data. Render real prices only after
the server has independently verified the catalog record. Integer minor units avoid binary
floating-point arithmetic.

Sample testimonials carry `content_status: "sample"`; only verified source material should be
marked `verified`. The CheersThePure example intentionally contains no testimonials, prices,
certifications, laboratory results, or purification claims. Add RO/UV messaging only after the
business has verified the process and approved the wording.

## Safety and Rendering

Validation rejects unknown fields, section types, palette values, unsafe markup-like strings,
invalid URLs, oversized documents, and overlong collections/content. The schema does not accept HTML, JavaScript,
event handlers, CSS, iframe markup, or server-side code as content. URL fields only accept
HTTP(S) links or constrained local paths where specified. Never repair malformed model output
by blindly coercing it; reject it and optionally request a fresh constrained generation.

Validation is not output encoding. Render all text as text and use the UI framework's contextual
escaping. Do not use `innerHTML`, unsafe HTML rendering, or execute generated strings. Map
allowlisted actions to application-owned behavior; never treat an action as a URL or executable
expression.

## Valid Example

The canonical validated sample is defined in `ai_builder/schema_examples.py` as
`CHEERSTHEPURE_EXAMPLE` and is kept executable so tests can validate it. Its JSON document is:

```json
{
  "schema_version": "1.0",
  "site_id": "4b47c1df-4ff9-4db5-8053-760f4e3bf431",
  "site_name": "CheersThePure",
  "business_type": "packaged drinking water",
  "brand": {"name": "CheersThePure", "logo_text": "CHEERS THE PURE"},
  "theme": {"color": "cyan", "surface": "light"},
  "sections": [
    {
      "id": "hero-main",
      "type": "hero",
      "headline": "Refreshment for every part of your day",
      "subheadline": "Packaged drinking water in convenient sizes for home, work, and business supply.",
      "cta_text": "Request a wholesale inquiry",
      "cta_action": "submit_b2b_inquiry",
      "image_url": null,
      "theme_color": "blue"
    },
    {
      "id": "features-purity",
      "type": "features",
      "title": "A dependable choice for everyday hydration",
      "subtitle": "Clear product information and practical formats for different needs.",
      "items": [
        {"icon": "droplet", "title": "Everyday hydration", "description": "A straightforward option for everyday drinking-water needs."},
        {"icon": "package-check", "title": "Useful bottle sizes", "description": "Choose compact, personal, and larger formats for your setting."},
        {"icon": "users", "title": "Business inquiries", "description": "Businesses can share their requirements through the wholesale inquiry form."}
      ]
    },
    {
      "id": "products-water",
      "type": "product_grid",
      "title": "Explore the bottle range",
      "items": [
        {"name": "Sport", "capacity": "250 ml", "description": "A compact format for a quick refreshment.", "image_url": null, "badge": "Compact", "data_source": "sample", "price": null},
        {"name": "Daily", "capacity": "500 ml", "description": "A convenient format for everyday use.", "image_url": null, "badge": null, "data_source": "sample", "price": null},
        {"name": "Premium", "capacity": "1 L", "description": "A larger bottle format for longer days.", "image_url": null, "badge": null, "data_source": "sample", "price": null},
        {"name": "Corporate", "capacity": "2 L", "description": "A high-capacity format for shared settings.", "image_url": null, "badge": "Large format", "data_source": "sample", "price": null}
      ]
    },
    {
      "id": "quote-wholesale",
      "type": "quote_form",
      "title": "Request a B2B wholesale inquiry",
      "subtitle": "Share your requirements and the team can follow up about supply options.",
      "fields": [
        {"name": "name", "label": "Name", "required": true},
        {"name": "email", "label": "Email", "required": true},
        {"name": "company", "label": "Company", "required": true},
        {"name": "capacity", "label": "Bottle capacity", "required": true},
        {"name": "quantity", "label": "Quantity", "required": true},
        {"name": "details", "label": "Details (optional)", "required": false}
      ],
      "submit_button_text": "Send inquiry",
      "action": "submit_b2b_inquiry"
    },
    {
      "id": "footer-main",
      "type": "footer",
      "company_name": "CheersThePure",
      "copyright": "Copyright 2026 CheersThePure.",
      "links": [
        {"label": "Products", "url": "/products/"},
        {"label": "Wholesale inquiry", "url": "/order/"}
      ]
    }
  ]
}
```