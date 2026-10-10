import json

from .schemas import SECTION_MODELS, SiteSchema


GENERATION_SYSTEM_PROMPT = f"""You generate complete website JSON documents for SaaSsum AI.
Return exactly one RFC 8259 JSON object and no other text or Markdown. The response must
validate against this JSON Schema:
{json.dumps(SiteSchema.model_json_schema(), ensure_ascii=False)}

Use only the seven supported section types and approved actions/icons/themes. Include a hero,
features, product_grid, quote_form, and footer. Use sample products with null prices unless
trusted catalog data is explicitly supplied in context. Never invent pricing, certifications,
laboratory results, business guarantees, or testimonials. Mark every sample testimonial as
sample. The quote form action must be submit_b2b_inquiry; never add an API destination.
Generated text is plain text, never HTML, JavaScript, CSS, or code. Respect any supplied site_id
exactly. Output only JSON."""


def build_section_refine_system_prompt(section_type: str) -> str:
    try:
        section_model = SECTION_MODELS[section_type]
    except KeyError as error:
        raise ValueError(f"Unsupported section type: {section_type}") from error
    return f"""You are editing one existing website section. Return only one valid JSON object for
the updated section, without markdown or a wrapper key. Do not output other sections. Preserve
all unrequested fields, IDs, meaning, and brand tone. Never add arbitrary fields, HTML, scripts,
CSS, URLs, or unsupported factual claims. The exact section schema is:
{json.dumps(section_model.model_json_schema(), ensure_ascii=False)}"""