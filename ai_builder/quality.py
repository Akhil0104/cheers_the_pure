"""Deterministic quality and safety review for validated website documents."""

import re
from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from .schemas import MAX_SITE_JSON_BYTES, SiteSchema

_CLAIM_PATTERN = re.compile(
    r"\b(certified|certification|laboratory|lab[- ]tested|guaranteed|guarantee|"
    r"100%\s*(?:pure|safe)|fastest|number one|no\.?\s*1)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class ReviewCheck:
    key: str
    status: str
    explanation: str

    def as_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "status": self.status,
            "explanation": self.explanation,
        }


def _check(key: str, status: str, explanation: str) -> ReviewCheck:
    return ReviewCheck(key, status, explanation)


def review_site(site_data: Any) -> tuple[SiteSchema | None, dict]:
    checks: list[ReviewCheck] = []
    try:
        site = SiteSchema.model_validate(site_data)
    except (ValidationError, ValueError) as error:
        checks.append(_check("schema", "blocking", "The website does not match the supported SiteSchema."))
        checks.extend(
            [
                _check("required_fields", "blocking", "Required fields cannot be evaluated until the schema is valid."),
                _check("safe_content", "blocking", "Unsafe or unsupported content was rejected by schema validation."),
            ]
        )
        return None, _review_result(checks)

    checks.append(_check("schema", "pass", "The website matches the versioned SiteSchema."))
    checks.append(_check("required_fields", "pass", "Required site, brand, theme, and section fields are present."))
    section_types = [section.type for section in site.sections]
    missing_core_sections = [section_type for section_type in ("hero", "footer") if section_type not in section_types]
    checks.append(
        _check(
            "section_completeness",
            "warning" if missing_core_sections else "pass",
            "Add the missing core section(s): " + ", ".join(missing_core_sections) + "."
            if missing_core_sections
            else "The site includes the core hero and footer sections.",
        )
    )
    checks.append(
        _check(
            "section_limits",
            "pass",
            f"The site contains {len(site.sections)} section(s) within the 1-12 section limit and payload limit.",
        )
    )
    checks.append(_check("safe_links_actions", "pass", "Links and actions use the schema allowlist and safe URL rules."))

    if "hero" in section_types:
        checks.append(_check("heading_structure", "pass", "The site has a primary hero heading."))
    else:
        checks.append(_check("heading_structure", "warning", "Add a hero section so the page has a clear primary heading."))

    has_cta = any(
        getattr(section, "cta_action", None) or getattr(section, "action", None)
        for section in site.sections
    )
    checks.append(
        _check(
            "calls_to_action",
            "pass" if has_cta else "warning",
            "At least one actionable conversion path is present."
            if has_cta
            else "Add a clear call to action for the visitor's intended next step.",
        )
    )

    image_missing_alt = False
    for section in site.sections:
        if section.type == "hero" and section.image_url:
            image_missing_alt = True
        if section.type == "product_grid":
            image_missing_alt = image_missing_alt or any(
                product.image_url is not None and not product.name.strip() for product in section.items
            )
    checks.append(
        _check(
            "image_alt_text",
            "warning" if image_missing_alt else "pass",
            "Some images do not have a dedicated alternative description; the renderer may only use a fallback."
            if image_missing_alt
            else "Images are absent or have usable text fallbacks for alternative text.",
        )
    )

    forms = [section for section in site.sections if section.type == "quote_form"]
    form_labels_valid = all(field.label.strip() for form in forms for field in form.fields)
    checks.append(
        _check(
            "form_labels",
            "pass" if form_labels_valid else "warning",
            "Form fields have visible labels." if form_labels_valid else "Add a visible label to every form field.",
        )
    )

    unsafe_binding = any(
        section.type == "product_grid"
        and any(
            product.data_source == "cheersthepure_database"
            and (product.data_binding is None or product.price is None)
            for product in section.items
        )
        for section in site.sections
    )
    checks.append(
        _check(
            "business_data_bindings",
            "blocking" if unsafe_binding else "pass",
            "Live catalog entries must include trusted server-side bindings and prices."
            if unsafe_binding
            else "Business data bindings are absent or use the required trusted binding shape.",
        )
    )

    serialized = site.model_dump(mode="json")
    text_values = _text_values(serialized)
    detectable_claim = any(_CLAIM_PATTERN.search(value) for value in text_values)
    checks.append(
        _check(
            "factual_claims",
            "warning" if detectable_claim else "pass",
            "Review detectable certification, testing, guarantee, or superlative claims before publishing."
            if detectable_claim
            else "No common unsupported factual-claim patterns were detected.",
        )
    )
    return site, _review_result(checks)


def _text_values(value: Any) -> list[str]:
    if isinstance(value, dict):
        return [item for child in value.values() for item in _text_values(child)]
    if isinstance(value, list):
        return [item for child in value for item in _text_values(child)]
    return [value] if isinstance(value, str) else []


def _review_result(checks: list[ReviewCheck]) -> dict:
    return {
        "ok": not any(check.status == "blocking" for check in checks),
        "checks": [check.as_dict() for check in checks],
    }
