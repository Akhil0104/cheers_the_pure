"""Email-domain routing for B2B vs B2C account types,
with optional Ollama AI enrichment for corporate (B2B) registrations.
"""

import json
import logging

logger = logging.getLogger(__name__)

# ── Public consumer email domains ───────────────────────────────────────────
PUBLIC_EMAIL_DOMAINS = frozenset({
    'gmail.com', 'googlemail.com',
    'yahoo.com', 'yahoo.co.in', 'yahoo.co.uk', 'ymail.com',
    'outlook.com', 'hotmail.com', 'live.com', 'msn.com',
    'icloud.com', 'me.com', 'mac.com',
    'aol.com', 'protonmail.com', 'proton.me',
    'mail.com', 'gmx.com', 'zoho.com',
    'rediffmail.com',
})


# ── Core parsing helpers ─────────────────────────────────────────────────────

def extract_email_domain(email: str) -> str:
    """Return the lowercased domain portion of an email address."""
    return email.strip().lower().split('@')[-1]


def is_public_email_domain(email: str) -> bool:
    """Return True if the email belongs to a known public provider."""
    domain = extract_email_domain(email)
    if domain in PUBLIC_EMAIL_DOMAINS:
        return True
    return any(domain.endswith(f'.{public}') for public in PUBLIC_EMAIL_DOMAINS)


def parse_company_name_from_email(email: str) -> str:
    """Derive a display company name from a corporate email domain."""
    domain = extract_email_domain(email)
    name_part = domain.split('.')[0]
    return name_part.replace('-', ' ').replace('_', ' ').title()


def detect_account_type(email: str) -> str:
    """Return 'b2c' for personal email providers, 'b2b' for corporate domains."""
    return 'b2c' if is_public_email_domain(email) else 'b2b'


# ── Ollama B2B enrichment ────────────────────────────────────────────────────

OLLAMA_BASE_URL = 'http://localhost:11434'
OLLAMA_MODEL    = 'llama3'  # adjust if you use a different local model

_OLLAMA_PROMPT_TEMPLATE = """You are a business intelligence assistant.
A user has registered with the corporate email domain: "{domain}"

Please infer the company details and respond ONLY with a valid JSON object (no markdown, no explanation) in this exact format:
{{
  "company_legal_name": "<Official company name>",
  "industry": "<Primary industry or sector>"
}}"""


def _query_ollama_for_domain(domain: str) -> dict:
    """
    Query the local Ollama instance to infer company metadata from an email domain.

    Returns a dict with keys 'company_legal_name' and 'industry'.
    Raises on any failure so callers can handle gracefully.
    """
    import ollama  # Optional dependency — pip install ollama

    prompt = _OLLAMA_PROMPT_TEMPLATE.format(domain=domain)

    response = ollama.chat(
        model=OLLAMA_MODEL,
        messages=[{'role': 'user', 'content': prompt}],
        options={'temperature': 0.2, 'num_predict': 120},
    )

    raw_text = response['message']['content'].strip()

    # Strip markdown fences if model returned them
    if raw_text.startswith('```'):
        lines = raw_text.splitlines()
        raw_text = '\n'.join(
            line for line in lines
            if not line.startswith('```')
        ).strip()

    parsed = json.loads(raw_text)
    return {
        'company_legal_name': str(parsed.get('company_legal_name', '')).strip(),
        'industry':           str(parsed.get('industry', '')).strip(),
    }


def enrich_b2b_profile_with_ollama(email: str, profile) -> None:
    """
    Attempt to enrich a B2B UserProfile with AI-inferred company metadata.

    - Parses the corporate email domain.
    - Queries the local Ollama instance at http://localhost:11434.
    - Saves 'company_name' and 'industry' to the profile on success.
    - Falls back gracefully (logs warning, uses domain-derived name) if
      Ollama is unreachable, not installed, or returns invalid JSON.

    Args:
        email:   The user's registration email address.
        profile: A UserProfile instance (already saved, will be updated).
    """
    domain = extract_email_domain(email)

    # Fallback values derived purely from the domain
    fallback_company = parse_company_name_from_email(email)
    fallback_industry = ''

    try:
        enriched = _query_ollama_for_domain(domain)
        company_name = enriched.get('company_legal_name') or fallback_company
        industry     = enriched.get('industry') or fallback_industry
        logger.info(
            "Ollama enriched B2B profile for domain '%s': company='%s', industry='%s'",
            domain, company_name, industry,
        )
    except ImportError:
        # ollama package not installed — silent fallback
        logger.debug("ollama package not installed; using domain-derived company name for '%s'.", domain)
        company_name = fallback_company
        industry     = fallback_industry
    except ConnectionRefusedError:
        logger.warning("Ollama server unreachable at %s — using fallback for domain '%s'.", OLLAMA_BASE_URL, domain)
        company_name = fallback_company
        industry     = fallback_industry
    except json.JSONDecodeError as exc:
        logger.warning("Ollama returned non-JSON response for domain '%s': %s", domain, exc)
        company_name = fallback_company
        industry     = fallback_industry
    except Exception as exc:  # noqa: BLE001
        logger.warning("Ollama enrichment failed for domain '%s': %s", domain, exc)
        company_name = fallback_company
        industry     = fallback_industry

    # Only update if fields are currently empty to avoid overwriting manual data
    changed = False
    if not profile.company_name and company_name:
        profile.company_name = company_name
        changed = True
    if not profile.industry and industry:
        profile.industry = industry
        changed = True

    if changed:
        profile.save(update_fields=[f for f in ('company_name', 'industry') if getattr(profile, f)])
