"""Prompt-to-SiteSchema generation orchestration."""

import json
from typing import Callable
from uuid import UUID

from pydantic import ValidationError

from .builder_prompts import GENERATION_SYSTEM_PROMPT
from .provider import WebsiteAIProvider
from .schemas import SiteSchema

MAX_REPAIR_ATTEMPTS = 2
SUPPORTED_SECTION_TYPES = (
    "hero",
    "features",
    "product_grid",
    "quote_form",
    "footer",
    "text_block",
    "testimonials",
)


def _validated_json_object(text: str) -> dict:
    def reject_duplicate_keys(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"The AI response contains a duplicate JSON key: {key}")
            result[key] = value
        return result

    try:
        result = json.loads(text, object_pairs_hook=reject_duplicate_keys)
    except (json.JSONDecodeError, TypeError, ValueError) as error:
        raise ValueError("The AI response was not valid JSON. Please try again.") from error
    if not isinstance(result, dict):
        raise ValueError("The AI response must be one JSON object.")
    return result


def normalize_generation_brief(data: dict) -> tuple[dict, str]:
    prompt = data.get("prompt", "")
    fields = {
        "business_description": data.get("business_description", prompt),
        "audience": data.get("audience", ""),
        "goal": data.get("goal", ""),
        "visual_direction": data.get("visual_direction", ""),
    }
    for name, value in fields.items():
        if not isinstance(value, str) or len(value.strip()) > 4000:
            raise ValueError(f"{name.replace('_', ' ').capitalize()} must be 4000 characters or fewer.")
        fields[name] = value.strip()

    if not fields["business_description"]:
        raise ValueError("Describe the business in 1-4000 characters.")

    requested_sections = data.get("requested_sections", [])
    if requested_sections is None:
        requested_sections = []
    if not isinstance(requested_sections, list) or len(requested_sections) > 7:
        raise ValueError("Choose up to 7 requested sections.")
    if any(section not in SUPPORTED_SECTION_TYPES for section in requested_sections):
        raise ValueError("Requested sections must use supported section types.")
    if len(set(requested_sections)) != len(requested_sections):
        raise ValueError("Requested sections must be unique.")

    brief = {**fields, "requested_sections": requested_sections}
    persisted_brief = json.dumps(brief, ensure_ascii=False, separators=(",", ":"))
    return brief, persisted_brief


def build_generation_messages(site_id: UUID | str, brief: dict, repair_feedback: str | None = None) -> list[dict]:
    user_content = {
        "site_id": str(site_id),
        "brief": brief,
        "constraints": {
            "trusted_catalog_data": (
                "trusted records are supplied below; preserve their values and provenance"
                if brief.get("trusted_catalog_records")
                else "not supplied; use sample products with null prices"
            ),
            "testimonials": "sample only unless verified data is supplied",
            "rendering": "plain text content only; no HTML, CSS, scripts, code, imports, or commands",
        },
    }
    if repair_feedback:
        user_content["repair_feedback"] = repair_feedback[:2000]
    return [
        {"role": "system", "content": GENERATION_SYSTEM_PROMPT},
        {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)},
    ]


def generate_validated_site(
    *,
    provider: WebsiteAIProvider,
    site_id: UUID | str,
    brief: dict,
    actor_key: str,
    max_repair_attempts: int = MAX_REPAIR_ATTEMPTS,
    on_validation_error: Callable[[str], None] | None = None,
) -> SiteSchema:
    if max_repair_attempts < 0:
        raise ValueError("max_repair_attempts cannot be negative")

    repair_feedback = None
    last_error: ValueError | ValidationError | None = None
    for attempt in range(max_repair_attempts + 1):
        completion = provider.generate_json(
            messages=build_generation_messages(site_id, brief, repair_feedback),
            actor_key=actor_key,
            max_tokens=5000,
        )
        try:
            site_data = _validated_json_object(completion.get("content", ""))
            validated_site = SiteSchema.model_validate(site_data)
            if str(validated_site.site_id) != str(site_id):
                raise ValueError("The generated site failed its identity check. Please retry.")
            return validated_site
        except (ValueError, ValidationError) as error:
            last_error = error
            repair_feedback = str(error)
            if on_validation_error:
                on_validation_error(f"generation_validation_attempt_{attempt + 1}")

    assert last_error is not None
    raise last_error
