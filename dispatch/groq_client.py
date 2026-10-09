"""
Groq API Client for DispatchAI.

Wraps the Groq Python SDK to provide:
- Synchronous chat completions (AJAX fallback)
- Streaming chat completions (SSE primary)
- Automatic retry on rate limits
- Model selection by task type
- Token tracking for DispatchDecision audit log
"""

import logging
import time
from typing import Generator, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# ── Model Aliases ─────────────────────────────────────────────────────────────
MODEL_FAST = 'llama-3.1-8b-instant'        # Quick FAQ, simple lookups
MODEL_SMART = 'llama-3.3-70b-versatile'    # B2B negotiation, complex reasoning
MODEL_EXTRACT = 'llama-3.1-8b-instant'     # Memory extraction (structured)

# ── Defaults ──────────────────────────────────────────────────────────────────
DEFAULT_MODEL = MODEL_SMART
DEFAULT_TEMPERATURE = 0.3        # Low: deterministic business responses
DEFAULT_MAX_TOKENS = 1024
MAX_RETRIES = 3
RETRY_DELAY_BASE = 1.0           # seconds, doubles on each retry


def _get_client():
    """Lazily import and configure the Groq client."""
    from .config import get_groq_api_key, is_groq_configured

    if not is_groq_configured():
        raise RuntimeError(
            'GROQ_API_KEY is not configured or is a placeholder.'
        )

    try:
        from groq import Groq
    except ImportError:
        raise RuntimeError(
            'groq package not installed. Run: pip install groq'
        )

    api_key = get_groq_api_key()
    return Groq(api_key=api_key)


# ── Public API ────────────────────────────────────────────────────────────────

def chat(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    stream: bool = False,
) -> dict:
    """
    Send a chat completion request to Groq (non-streaming).

    Args:
        messages:    List of {role, content} dicts. System prompt must be first.
        model:       Groq model identifier.
        temperature: Sampling temperature (0.0–1.0).
        max_tokens:  Maximum completion tokens.
        stream:      Must be False for this function.

    Returns:
        {
            "content":     str,    # Full response text
            "model":       str,    # Model used
            "tokens_used": int,    # Total tokens (prompt + completion)
            "latency_ms":  int,    # Wall-clock latency in ms
        }
    Raises:
        RuntimeError on unrecoverable errors after retries.
    """
    client = _get_client()

    for attempt in range(1, MAX_RETRIES + 1):
        start_ms = int(time.time() * 1000)
        try:
            response = client.chat.completions.create(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                stream=False,
            )
            end_ms = int(time.time() * 1000)

            content = response.choices[0].message.content or ''
            usage = response.usage

            logger.info(
                'Groq chat [%s] tokens=%d latency=%dms',
                model,
                usage.total_tokens if usage else 0,
                end_ms - start_ms,
            )

            return {
                'content': content,
                'model': model,
                'tokens_used': usage.total_tokens if usage else 0,
                'latency_ms': end_ms - start_ms,
                'finish_reason': response.choices[0].finish_reason,
            }

        except Exception as exc:
            err_str = str(exc)
            logger.warning(
                'Groq attempt %d/%d failed: %s',
                attempt, MAX_RETRIES, err_str,
            )

            # Rate limit — back off and retry
            if 'rate_limit' in err_str.lower() or '429' in err_str:
                delay = RETRY_DELAY_BASE * (2 ** (attempt - 1))
                logger.info('Rate limited. Retrying in %.1fs…', delay)
                time.sleep(delay)
                continue

            # Timeout or server error — retry once
            if attempt < MAX_RETRIES:
                time.sleep(RETRY_DELAY_BASE)
                continue

            # All retries exhausted
            raise RuntimeError(
                f'Groq API unavailable after {MAX_RETRIES} attempts: {exc}'
            ) from exc

    raise RuntimeError('Groq chat: max retries exceeded without a response.')


def chat_stream(
    messages: list[dict],
    model: str = DEFAULT_MODEL,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
) -> Generator[str, None, None]:
    """
    Stream a chat completion from Groq token by token.

    Yields:
        Token strings as they arrive from the API.

    Usage in a Django SSE view:
        for token in groq_client.chat_stream(messages):
            yield f"data: {json.dumps({'type': 'token', 'content': token})}\\n\\n"
    """
    client = _get_client()

    try:
        stream = client.chat.completions.create(
            messages=messages,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
        )
        for chunk in stream:
            delta = chunk.choices[0].delta
            if delta and delta.content:
                yield delta.content

    except Exception as exc:
        logger.error('Groq stream error: %s', exc)
        # Yield a safe error sentinel so the SSE handler can close cleanly
        yield '__GROQ_STREAM_ERROR__'


def extract_memories(conversation_text: str) -> list[str]:
    """
    Use a small fast model to extract retain-worthy memories from a conversation turn.

    Returns a list of memory strings (empty list on failure).
    """
    system = (
        'You are a memory extraction assistant. '
        'Given a conversation turn between a sales agent and a B2B distributor, '
        'extract 0-5 facts worth remembering about this buyer for future conversations. '
        'Focus on: preferences, delivery constraints, negotiation positions, business context. '
        'NEVER extract: order numbers, transaction IDs, prices already in database. '
        'Output ONLY a JSON array of strings, e.g. ["fact 1", "fact 2"]. '
        'Output an empty array [] if nothing is worth remembering.'
    )

    messages = [
        {'role': 'system', 'content': system},
        {'role': 'user', 'content': conversation_text},
    ]

    try:
        result = chat(
            messages=messages,
            model=MODEL_EXTRACT,
            temperature=0.1,
            max_tokens=256,
        )
        import json
        text = result['content'].strip()
        # Strip markdown fences if present
        if text.startswith('```'):
            lines = text.splitlines()
            text = '\n'.join(l for l in lines if not l.startswith('```')).strip()
        memories = json.loads(text)
        if isinstance(memories, list):
            return [str(m) for m in memories if m]
        return []
    except Exception as exc:
        logger.warning('Memory extraction failed: %s', exc)
        return []
