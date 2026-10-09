"""
Configuration helper for DispatchAI.

Provides centralized, safe access to:
- Groq configuration (API key, default models, timeouts)
- Hindsight configuration (API key, base URL, app ID)
- Startup validation with masked secret reporting

Secrets are never exposed in logs, error messages, or serialized responses.
"""

import logging
import os
from typing import Any, Dict, List, Optional
from django.conf import settings

logger = logging.getLogger(__name__)


def mask_secret(secret: Optional[str], show_prefix: int = 4, show_suffix: int = 3) -> str:
    """
    Safely mask a secret string for logging or debugging.
    Example: 'gsk_1234567890abcdef' -> 'gsk_...def'
    """
    if not secret:
        return '[NOT SET]'
    s = str(secret).strip()
    if len(s) <= (show_prefix + show_suffix + 2):
        return '***'
    return f"{s[:show_prefix]}...{s[-show_suffix:]}"


# ── Groq Configuration ────────────────────────────────────────────────────────

def get_groq_api_key() -> str:
    """Return the raw Groq API key from settings or environment."""
    return getattr(settings, 'GROQ_API_KEY', '') or os.environ.get('GROQ_API_KEY', '').strip()


def is_groq_configured() -> bool:
    """Return True if a non-placeholder Groq API key is configured."""
    key = get_groq_api_key()
    return bool(key and not key.startswith('gsk_YOUR') and len(key) > 8)


def get_groq_config() -> Dict[str, Any]:
    """Return safe metadata about Groq configuration (no raw secrets)."""
    key = get_groq_api_key()
    return {
        'configured': is_groq_configured(),
        'api_key_masked': mask_secret(key, show_prefix=4, show_suffix=3),
        'default_model': 'llama-3.3-70b-versatile',
        'fast_model': 'llama-3.1-8b-instant',
    }


# ── Hindsight Configuration ───────────────────────────────────────────────────

def get_hindsight_api_key() -> str:
    """Return the raw Hindsight API key from settings or environment."""
    return getattr(settings, 'HINDSIGHT_API_KEY', '') or os.environ.get('HINDSIGHT_API_KEY', '').strip()


def get_hindsight_url() -> str:
    """Return the Hindsight API base URL."""
    url = getattr(settings, 'HINDSIGHT_URL', '') or os.environ.get('HINDSIGHT_URL', '')
    if not url:
        url = getattr(settings, 'HINDSIGHT_API_URL', '') or os.environ.get('HINDSIGHT_API_URL', '')
    return (url or 'https://api.hindsight.vectorize.io').rstrip('/')


def get_hindsight_app_id() -> str:
    """Return the Hindsight app ID for memory namespace."""
    return getattr(settings, 'HINDSIGHT_APP_ID', '') or os.environ.get('HINDSIGHT_APP_ID', 'cheersthepure-b2b')


def get_hindsight_bank_id() -> str:
    """Return the Hindsight memory bank name (default: cheersthepure-b2b)."""
    return (
        getattr(settings, 'HINDSIGHT_BANK_ID', '')
        or os.environ.get('HINDSIGHT_BANK_ID', '')
        or getattr(settings, 'HINDSIGHT_APP_ID', '')
        or os.environ.get('HINDSIGHT_APP_ID', '')
        or 'cheersthepure-b2b'
    )


def is_hindsight_configured() -> bool:
    """Return True if Hindsight URL and API key are configured."""
    key = get_hindsight_api_key()
    return bool(key and not key.startswith('hsk_YOUR') and len(key) > 6 and get_hindsight_url())


def get_hindsight_config() -> Dict[str, Any]:
    """Return safe metadata about Hindsight configuration (no raw secrets)."""
    key = get_hindsight_api_key()
    return {
        'configured': is_hindsight_configured(),
        'api_url': get_hindsight_url(),
        'api_key_masked': mask_secret(key, show_prefix=4, show_suffix=3),
        'app_id': get_hindsight_app_id(),
        'bank_id': get_hindsight_bank_id(),
    }


# ── Startup Validation ────────────────────────────────────────────────────────

def validate_dispatch_environment(logger_instance: Optional[logging.Logger] = None) -> Dict[str, Any]:
    """
    Validate all required and optional environment settings for DispatchAI.
    Reports status clearly while keeping all secret values masked.

    Returns:
        Dict summarizing configuration status, warnings, and missing components.
    """
    log = logger_instance or logger
    issues: List[str] = []
    status_report: Dict[str, Any] = {}

    groq_ok = is_groq_configured()
    hindsight_ok = is_hindsight_configured()
    groq_key = get_groq_api_key()
    hindsight_key = get_hindsight_api_key()

    status_report['groq'] = {
        'configured': groq_ok,
        'key_status': mask_secret(groq_key),
    }

    status_report['hindsight'] = {
        'configured': hindsight_ok,
        'url': get_hindsight_url(),
        'key_status': mask_secret(hindsight_key),
        'app_id': get_hindsight_app_id(),
    }

    if not groq_ok:
        msg = "[DispatchAI] GROQ_API_KEY is not configured. AI chat will use fallback responses."
        log.warning(msg)
        issues.append(msg)
    else:
        log.info("[DispatchAI] Groq LLM initialized successfully (key: %s)", mask_secret(groq_key))

    if not hindsight_ok:
        msg = "[DispatchAI] HINDSIGHT_API_KEY is not configured. Persistent memory recall/retain will be bypassed."
        log.info(msg)
        issues.append(msg)
    else:
        log.info(
            "[DispatchAI] Hindsight Memory initialized successfully (url: %s, key: %s, app_id: %s)",
            get_hindsight_url(),
            mask_secret(hindsight_key),
            get_hindsight_app_id(),
        )

    status_report['ready'] = groq_ok
    status_report['issues'] = issues
    return status_report
